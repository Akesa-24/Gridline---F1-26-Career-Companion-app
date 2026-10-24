"""Replay a raw packet capture (.gridcap) to the app, e.g. to debug a real session.

Turn on "Save raw packets for troubleshooting" in Settings › Telemetry; captures
are written to the Gridline data folder under captures/.

    python -m gridline.tools.replay path/to/session.gridcap --speed 4
"""
from __future__ import annotations

import argparse
import socket
import struct
import time


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=20777)
    ap.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier (0 = as fast as possible)")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    head = struct.Struct("<dH")
    sent = 0
    prev = None
    with open(args.capture, "rb") as f:
        while True:
            h = f.read(head.size)
            if len(h) < head.size:
                break
            ts, n = head.unpack(h)
            data = f.read(n)
            if prev is not None and args.speed > 0:
                time.sleep(max(0.0, (ts - prev) / args.speed))
            prev = ts
            sock.sendto(data, (args.host, args.port))
            sent += 1
    print(f"replayed {sent} packets")


if __name__ == "__main__":
    main()
