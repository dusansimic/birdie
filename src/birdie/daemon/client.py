"""Async gRPC wrapper around the NetBird ``DaemonService``.

The NetBird daemon (systemd ``netbird.service``, running as root) exposes a
single gRPC service over a local unix socket. Access control is purely the
socket file permissions, which the daemon sets to 0666, so no privilege
escalation is needed to talk to it.

Every method here is a thin ``async`` wrapper over the generated stub and is
meant to be awaited on the GLib/asyncio loop that PyGObject installs. Callers
should catch :class:`grpc.aio.AioRpcError` (or the convenience
:class:`DaemonError`) and surface failures as toasts/banners.
"""

from __future__ import annotations

import getpass
import glob
import os
from typing import AsyncIterator, Optional, Sequence

import grpc

from birdie.daemon import daemon_pb2 as pb
from birdie.daemon import daemon_pb2_grpc as rpc

# Default control sockets for the primary (non-instance) daemon. ``/var/run``
# is normally a symlink to ``/run``; inside the Flatpak sandbox only the paths
# granted via ``--filesystem`` exist, so both spellings are probed.
DEFAULT_SOCKETS = ("/var/run/netbird.sock", "/run/netbird.sock")
# The ``netbird@<instance>.service`` template variant places its socket here.
INSTANCE_SOCKET_DIRS = ("/var/run/netbird", "/run/netbird")


class DaemonError(Exception):
    """A daemon call failed. Wraps the underlying gRPC error."""

    def __init__(self, message: str, *, code: Optional[grpc.StatusCode] = None,
                 cause: Optional[BaseException] = None):
        super().__init__(message)
        self.code = code
        self.cause = cause

    @classmethod
    def from_rpc(cls, err: "grpc.aio.AioRpcError") -> "DaemonError":
        return cls(err.details() or str(err), code=err.code(), cause=err)


def resolve_socket_address() -> str:
    """Return a ``unix://`` gRPC target for the running daemon.

    Mirrors the CLI resolver: prefer the default socket; otherwise, if a
    single instance socket exists under ``/var/run/netbird/``, use it.
    """
    for sock in DEFAULT_SOCKETS:
        if os.path.exists(sock):
            return f"unix://{sock}"

    for instance_dir in INSTANCE_SOCKET_DIRS:
        candidates = sorted(glob.glob(os.path.join(instance_dir, "*.sock")))
        if len(candidates) == 1:
            return f"unix://{candidates[0]}"
        if len(candidates) > 1:
            raise DaemonError(
                "Multiple NetBird daemon sockets found in "
                f"{instance_dir}; cannot pick one automatically."
            )
    # Fall back to the default path; the connection attempt will report the
    # more actionable "daemon not running" error.
    return f"unix://{DEFAULT_SOCKETS[0]}"


def current_username() -> str:
    """The OS login name, matching what the CLI passes for profile RPCs."""
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USER", "")


class NetbirdClient:
    """Owns the gRPC channel and exposes typed async daemon calls."""

    def __init__(self, address: Optional[str] = None):
        self._address = address or resolve_socket_address()
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[rpc.DaemonServiceStub] = None

    # -- lifecycle ---------------------------------------------------------

    async def connect(self) -> None:
        if self._channel is not None:
            return
        self._channel = grpc.aio.insecure_channel(self._address)
        self._stub = rpc.DaemonServiceStub(self._channel)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def _ensure(self) -> rpc.DaemonServiceStub:
        if self._stub is None:
            await self.connect()
        assert self._stub is not None
        return self._stub

    # -- connection lifecycle RPCs ----------------------------------------

    async def status(self, *, full: bool = True, probes: bool = False,
                     wait_for_ready: bool = False) -> pb.StatusResponse:
        stub = await self._ensure()
        try:
            return await stub.Status(pb.StatusRequest(
                getFullPeerStatus=full,
                shouldRunProbes=probes,
                waitForReady=wait_for_ready,
            ))
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def up(self, *, profile_name: Optional[str] = None) -> None:
        stub = await self._ensure()
        req = pb.UpRequest()
        if profile_name is not None:
            req.profileName = profile_name
            req.username = current_username()
        try:
            await stub.Up(req)
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def down(self) -> None:
        stub = await self._ensure()
        try:
            await stub.Down(pb.DownRequest())
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def login(self, *, setup_key: str = "", management_url: str = "",
                    hint: str = "", profile_name: Optional[str] = None,
                    hostname: str = "") -> pb.LoginResponse:
        """Prepare/validate config. Does not bring the tunnel up.

        Returns a response whose ``needsSSOLogin`` tells the caller whether an
        interactive device-flow (see :meth:`wait_sso_login`) is required.
        """
        stub = await self._ensure()
        req = pb.LoginRequest(isUnixDesktopClient=True)
        if setup_key:
            req.setupKey = setup_key
        if management_url:
            req.managementUrl = management_url
        if hint:
            req.hint = hint
        if hostname:
            req.hostname = hostname
        if profile_name is not None:
            req.profileName = profile_name
            req.username = current_username()
        try:
            return await stub.Login(req)
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def wait_sso_login(self, user_code: str, hostname: str = "") -> str:
        """Block until the user completes the browser device flow.

        This can take a long time (the daemon polls the IdP), so the caller
        should run it as a cancellable task. Returns the authenticated email.
        """
        stub = await self._ensure()
        try:
            resp = await stub.WaitSSOLogin(pb.WaitSSOLoginRequest(
                userCode=user_code, hostname=hostname))
            return resp.email
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def logout(self) -> None:
        """Disconnect and deregister the peer (CLI ``deregister``)."""
        stub = await self._ensure()
        try:
            await stub.Logout(pb.LogoutRequest())
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    # -- config ------------------------------------------------------------

    async def get_config(self) -> pb.GetConfigResponse:
        stub = await self._ensure()
        try:
            return await stub.GetConfig(pb.GetConfigRequest(
                username=current_username()))
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def set_config(self, req: pb.SetConfigRequest) -> None:
        stub = await self._ensure()
        try:
            await stub.SetConfig(req)
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def get_features(self) -> pb.GetFeaturesResponse:
        stub = await self._ensure()
        try:
            return await stub.GetFeatures(pb.GetFeaturesRequest())
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    # -- networks ----------------------------------------------------------

    async def list_networks(self) -> pb.ListNetworksResponse:
        stub = await self._ensure()
        try:
            return await stub.ListNetworks(pb.ListNetworksRequest())
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def select_networks(self, network_ids: Sequence[str], *,
                              append: bool = False, all: bool = False) -> None:
        stub = await self._ensure()
        try:
            await stub.SelectNetworks(pb.SelectNetworksRequest(
                networkIDs=list(network_ids), append=append, all=all))
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def deselect_networks(self, network_ids: Sequence[str], *,
                                all: bool = False) -> None:
        stub = await self._ensure()
        try:
            await stub.DeselectNetworks(pb.SelectNetworksRequest(
                networkIDs=list(network_ids), all=all))
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    # -- profiles ----------------------------------------------------------

    async def list_profiles(self) -> pb.ListProfilesResponse:
        stub = await self._ensure()
        try:
            return await stub.ListProfiles(pb.ListProfilesRequest(
                username=current_username()))
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def get_active_profile(self) -> pb.GetActiveProfileResponse:
        stub = await self._ensure()
        try:
            return await stub.GetActiveProfile(pb.GetActiveProfileRequest())
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def add_profile(self, name: str) -> str:
        stub = await self._ensure()
        try:
            resp = await stub.AddProfile(pb.AddProfileRequest(
                username=current_username(), profileName=name))
            return resp.id
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def rename_profile(self, handle: str, new_name: str) -> None:
        stub = await self._ensure()
        try:
            await stub.RenameProfile(pb.RenameProfileRequest(
                username=current_username(), handle=handle,
                newProfileName=new_name))
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def remove_profile(self, handle: str) -> None:
        stub = await self._ensure()
        try:
            await stub.RemoveProfile(pb.RemoveProfileRequest(
                username=current_username(), profileName=handle))
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def switch_profile(self, handle: str) -> str:
        stub = await self._ensure()
        try:
            resp = await stub.SwitchProfile(pb.SwitchProfileRequest(
                username=current_username(), profileName=handle))
            return resp.id
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    # -- diagnostics -------------------------------------------------------

    async def get_log_level(self) -> pb.GetLogLevelResponse:
        stub = await self._ensure()
        try:
            return await stub.GetLogLevel(pb.GetLogLevelRequest())
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def set_log_level(self, level: "pb.LogLevel.ValueType") -> None:
        stub = await self._ensure()
        try:
            await stub.SetLogLevel(pb.SetLogLevelRequest(level=level))
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def debug_bundle(self, *, anonymize: bool = True,
                           system_info: bool = True,
                           log_file_count: int = 0) -> pb.DebugBundleResponse:
        stub = await self._ensure()
        try:
            return await stub.DebugBundle(pb.DebugBundleRequest(
                anonymize=anonymize, systemInfo=system_info,
                logFileCount=log_file_count))
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)

    async def subscribe_events(self) -> AsyncIterator[pb.SystemEvent]:
        """Yield system events as they arrive from the daemon."""
        stub = await self._ensure()
        call = stub.SubscribeEvents(pb.SubscribeRequest())
        try:
            async for event in call:
                yield event
        except grpc.aio.AioRpcError as err:
            raise DaemonError.from_rpc(err)
