# Birdie — task runner. Run `just` to list recipes.

# List all recipes (default).
default:
    @just --list

# Run Birdie from the source tree (no install needed).
run:
    PYTHONPATH=src python3 -c "from birdie.main import main; main()"

# Regenerate gRPC stubs from proto/daemon.proto.
proto:
    python3 build-aux/gen-proto.py proto proto/daemon.proto src/birdie/daemon

# Configure the Meson build directory.
setup:
    meson setup build

# Compile (configures build/ first if missing).
build:
    [ -d build ] || meson setup build
    meson compile -C build

# Run validators (desktop / metainfo / gschema).
test:
    [ -d build ] || meson setup build
    meson test -C build

# Install with Meson (override dir with `just install DESTDIR=/tmp/x`).
install DESTDIR="":
    [ -d build ] || meson setup build
    {{ if DESTDIR == "" { "meson install -C build" } else { "DESTDIR=" + DESTDIR + " meson install -C build" } }}

# Build the Flatpak into ./repo.
flatpak:
    flatpak run org.flatpak.Builder --force-clean --user --install-deps-from=flathub \
        --repo=repo flatpak-build build-aux/flatpak/me.dusansimic.Birdie.json

# Install the locally-built Flatpak and run it.
flatpak-run: flatpak
    flatpak remote-add --user --no-gpg-verify --if-not-exists birdie-local repo
    flatpak install --user -y --reinstall birdie-local me.dusansimic.Birdie
    flatpak run me.dusansimic.Birdie

# Remove build artifacts.
clean:
    rm -rf build build-* .flatpak-builder flatpak-build repo
