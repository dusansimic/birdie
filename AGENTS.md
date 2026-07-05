# AGENTS.md

Guidance for AI agents and developers working on **Birdie**, a GNOME/libadwaita
GUI for the NetBird client.

## What this project is

Birdie is a **thin graphical client of the local NetBird daemon** (`netbird.service`).
The daemon exposes a single gRPC service, `DaemonService`, over a unix socket
(`unix:///var/run/netbird.sock`). The `netbird` CLI and Birdie are peer clients
of that same API — Birdie adds no networking logic of its own. If you need a
capability, it almost certainly maps to a daemon RPC; find it in
`proto/daemon.proto` before writing anything.

## Architecture (know this before editing)

```
libadwaita UI (GTK4)  →  NetbirdClient (grpc.aio)  →  unix socket  →  netbird.service
```

- **Async everywhere, no threads.** PyGObject ≥ 3.50's native asyncio
  (`gi.events.GLibEventLoopPolicy`, installed in `main.py`) makes the GLib main
  loop *be* the asyncio loop. Daemon calls are `async` and awaited directly.
  Never call `GLib.idle_add` to marshal results and never spawn threads for I/O.
- **Kick off work with `run_async`** (`src/birdie/async_utils.py`), passing
  `on_success` / `on_error` callbacks. Those callbacks run on the same loop and
  may touch widgets directly.
- **The daemon layer is the only place that touches gRPC.** All RPCs live in
  `src/birdie/daemon/client.py` as small typed `async` methods that wrap the
  generated stub and raise `DaemonError`. UI code imports `NetbirdClient`, never
  the generated `daemon_pb2*` modules directly (except for enums/message
  constructors when unavoidable).

## Project layout

- `src/birdie/main.py` — entry point; installs the asyncio policy, runs the app.
- `src/birdie/application.py` — `Adw.Application`, actions, shared `NetbirdClient`.
- `src/birdie/window.py` — top-level window, view stack, `toast()` helper.
- `src/birdie/views/` — one module per view (`status`, `networks`, `profiles`,
  `events`, plus `login_dialog`).
- `src/birdie/preferences.py` — settings editor backed by `GetConfig`/`SetConfig`.
- `src/birdie/daemon/` — `client.py` + generated `daemon_pb2*.py`.
- `proto/daemon.proto` — vendored daemon API (see "Proto" below).
- `data/` — `.desktop`, metainfo, gschema, icon. `build-aux/flatpak/` — packaging.

## Conventions

- **UI is built in Python**, not Blueprint (`blueprint-compiler` is intentionally
  not a dependency). Use libadwaita widgets: `Adw.PreferencesPage`/`Group`,
  `Adw.ActionRow`/`SwitchRow`/`ComboRow`, `Adw.ToolbarView`, `Adw.StatusPage`,
  `Adw.Dialog`/`AlertDialog`. Follow the GNOME HIG.
- **Surface daemon errors as UI**, not tracebacks: catch `DaemonError` in
  `on_error` and call `window.toast(...)`. `"not connected"` is a normal state
  (tunnel down) — render a friendly empty state, not an error.
- **Respect daemon-driven UI gates.** Hide feature-gated pages per
  `GetFeatures`; render `mDMManagedFields` inputs read-only; a `SetConfig`
  `FailedPrecondition` means the field is MDM-locked — revert and explain.
- When toggling a control that fires a daemon call, **disable it during the
  call and revert its visual state on failure** (see `networks_view.py`).
- No elevated privileges — the daemon socket is world-writable by design. Don't
  add polkit/sudo paths.
- Match the surrounding style: type hints, `from __future__ import annotations`,
  module docstrings explaining the *why*.

## Proto / generated stubs

`proto/daemon.proto` is vendored from NetBird's `client/proto/daemon.proto`
(currently **v0.73.2** — keep it matched to the daemon you target). After
changing the proto, regenerate:

```sh
just proto        # → python3 build-aux/gen-proto.py proto proto/daemon.proto src/birdie/daemon
```

The generator rewrites protoc's absolute import to a package-relative one. The
committed stubs are what the Flatpak build installs (`-Dgenerate_proto=false`).

## Build, run, verify

```sh
just run        # run from source, no install (fastest dev loop)
just build      # meson compile
just test       # desktop/metainfo/gschema validators
just flatpak    # build the Flatpak
```

**Always verify against the real daemon.** A clean startup only proves the
window builds. To prove behavior, hit the daemon: run the app and watch the
Status view populate, or probe directly, e.g.

```sh
PYTHONPATH=src python3 -c "import asyncio; from birdie.daemon.client import NetbirdClient; \
  asyncio.run((lambda: (lambda c: c.status())(NetbirdClient()))())"
```

Cross-check state changes with the CLI (`netbird status`, `netbird networks list`,
`netbird profile list`) — both are clients of the same daemon.

## Branching

- Never commit feature work directly to the default branch (`main`).
- Branch names follow **`feat/<slug>`** — a short kebab-case slug describing the
  change (e.g. `feat/stable-peer-list`, `feat/unified-header-bar`). Use other
  Conventional-Commit-style prefixes when they fit the work: `fix/<slug>`,
  `docs/<slug>`, `refactor/<slug>`.
- One branch per logically distinct change; open a pull request per branch.

## Committing changes

When the developer asks you to commit:

1. **Inspect the actual changes first** — `git status` and `git diff` (and
   `git diff --staged`). Understand what changed and why before staging anything.
2. **Group by nature, not by convenience.** If the working tree contains changes
   that are logically distinct (e.g. a bug fix vs. a new feature vs. a docs
   update vs. a refactor), they belong in **separate commits**. Stage each group
   deliberately (`git add -p` / specific paths) and commit it on its own. Do not
   lump unrelated changes into one commit.
3. **Generate every commit message with the `/caveman:caveman-commit` command.**
   Run it per commit (on that commit's staged changes) — do not hand-write
   messages or reuse one message across commits.
4. Only commit or push when explicitly asked. If on the default branch, branch
   first.
