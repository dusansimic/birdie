#!/usr/bin/env python3
"""Generate NetBird daemon gRPC stubs for the ``birdie.daemon`` package.

Runs ``grpc_tools.protoc`` and rewrites the absolute cross-import that protoc
emits (``import daemon_pb2``) into a package-relative import so the modules
work when imported as ``birdie.daemon.*``.

Usage: gen-proto.py <proto_dir> <proto_file> <out_dir>
"""

from __future__ import annotations

import pathlib
import subprocess
import sys


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    proto_dir, proto_file, out_dir = argv[1], argv[2], argv[3]
    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"-I{proto_dir}",
            f"--python_out={out_dir}",
            f"--grpc_python_out={out_dir}",
            proto_file,
        ],
        check=False,
    )
    if result.returncode != 0:
        return result.returncode

    grpc_file = pathlib.Path(out_dir) / "daemon_pb2_grpc.py"
    text = grpc_file.read_text()
    text = text.replace(
        "import daemon_pb2 as daemon__pb2",
        "from birdie.daemon import daemon_pb2 as daemon__pb2",
    )
    grpc_file.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
