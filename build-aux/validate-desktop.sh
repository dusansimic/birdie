#!/bin/sh
# Validate desktop-entry files for pre-commit.
#
# Our source is a `.desktop.in` template (meson merges translations into the
# final `.desktop` at build time). desktop-file-validate refuses any filename
# without a literal `.desktop` suffix, so validate a temp copy that carries one.
# The template has no @VARIABLE@ placeholders, so it validates as-is.
set -eu

status=0
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

for f in "$@"; do
    cp "$f" "$tmp/entry.desktop"
    desktop-file-validate "$tmp/entry.desktop" || status=1
done

exit "$status"
