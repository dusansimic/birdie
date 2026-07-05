# Birdie

A GNOME / libadwaita desktop front-end for the [NetBird](https://github.com/netbirdio/netbird)
client. Birdie is a graphical client of the local NetBird daemon
(`netbird.service`) — the same gRPC control API the `netbird` CLI uses — so it
can do what the CLI does without leaving your desktop.

## Features (v1)

- **Connect / disconnect** with live connection state.
- **Login** via SSO device flow (browser) or a setup key.
- **Status dashboard**: local peer info, management/signal state, and a live
  peer list (IP, direct/relayed, latency).
- **Networks**: list routed networks and select / deselect them.
- **Profiles**: list, switch, add, rename, remove.
- **Preferences**: full client-settings editor backed by `GetConfig`/`SetConfig`,
  with MDM-managed fields shown read-only.
- **Events & diagnostics**: live daemon event feed, log-level control, and
  debug-bundle generation.

## Architecture

```
libadwaita UI (GTK4, async)  →  NetbirdClient (grpc.aio)  →  unix:///var/run/netbird.sock  →  netbird.service
```

The UI never blocks: PyGObject ≥ 3.50's native asyncio integration
(`gi.events.GLibEventLoopPolicy`) makes the GLib main loop *be* the asyncio
loop, so every daemon RPC and the `SubscribeEvents` stream is awaited
cooperatively — no worker threads. The daemon sets the control socket to mode
0666, so Birdie needs no elevated privileges. See `src/birdie/daemon/client.py`.

## Building (native)

```sh
meson setup build
meson compile -C build
meson test -C build          # validates desktop / metainfo / gschema
meson install -C build
```

Runtime deps: Python 3, PyGObject ≥ 3.50, GTK 4, libadwaita ≥ 1.5, `grpcio`,
`protobuf`. Build deps: Meson, `grpcio-tools` (for proto codegen),
`desktop-file-utils`, `appstream`.

Run from a dev checkout without installing:

```sh
PYTHONPATH=src python3 -c "from birdie.main import main; main()"
```

## Building (Flatpak)

```sh
flatpak run org.flatpak.Builder --force-clean --user --install-deps-from=flathub \
  --repo=repo flatpak-build build-aux/flatpak/org.birdie.Birdie.json
flatpak build-bundle repo birdie.flatpak org.birdie.Birdie   # optional
```

The Flatpak build installs pre-generated gRPC stubs (`-Dgenerate_proto=false`)
and vendors `grpcio`/`protobuf` as wheels (`build-aux/flatpak/python3-deps.json`).
The sandbox reaches the host daemon through `--filesystem=/run/netbird.sock`.

## gRPC stubs / proto sync

`proto/daemon.proto` is vendored from NetBird's `client/proto/daemon.proto`
(currently **v0.73.2**). The stubs in `src/birdie/daemon/daemon_pb2*.py` are
generated from it. Regenerate after updating the proto:

```sh
python3 build-aux/gen-proto.py proto proto/daemon.proto src/birdie/daemon
```

Re-sync the vendored proto whenever the daemon API changes upstream.
