"""Listen for a few seconds and summarise what the game is sending.

Close Gridline first (it uses the same port), then:
    python -m gridline.tools.sniff --seconds 15
"""
from __future__ import annotations

import argparse
import socket
import struct
import time
from collections import Counter

from gridline.telemetry.packets import SPECS, decode

NAMES = {0: "Motion", 1: "Session", 2: "LapData", 3: "Event", 4: "Participants", 5: "CarSetups",
         6: "CarTelemetry", 7: "CarStatus", 8: "FinalClassification", 9: "LobbyInfo", 10: "CarDamage",
         11: "SessionHistory", 12: "TyreSets", 13: "MotionEx", 14: "TimeTrial", 15: "LapPositions",
         16: "CarTelemetry2"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=20777)
    ap.add_argument("--seconds", type=float, default=15)
    args = ap.parse_args()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", args.port))
    s.settimeout(0.5)
    counts, sizes, formats, errors = Counter(), {}, Counter(), Counter()
    last_lobby = None
    end = time.time() + args.seconds
    print(f"Listening on {args.port} for {args.seconds:.0f}s...")
    while time.time() < end:
        try:
            d, _ = s.recvfrom(4096)
        except socket.timeout:
            continue
        if len(d) < 29:
            continue
        fmt, pid = struct.unpack_from("<H", d, 0)[0], d[6]
        formats[fmt] += 1
        counts[pid] += 1
        sizes.setdefault(pid, set()).add(len(d))
        try:
            pkt = decode(d)
            if pkt and pid == 9:
                last_lobby = pkt.body
        except Exception as exc:
            errors[f"{NAMES.get(pid, pid)}: {exc.__class__.__name__}: {exc}"] += 1
    print("formats:", dict(formats))
    for pid in sorted(counts):
        spec = SPECS.get(max(formats, key=formats.get))
        exp = spec.sizes.get(pid) if spec else None
        flag = "" if exp is None or sizes[pid] == {exp} else f"   <-- spec says {exp}"
        print(f"  {pid:>2} {NAMES.get(pid, '?'):<20} x{counts[pid]:<6} sizes {sorted(sizes[pid])}{flag}")
    for e, n in errors.items():
        print("  ERROR", e, f"x{n}")
    if last_lobby:
        num, players = last_lobby
        print(f"lobby: {num} players")
        for p in players[:num]:
            print(f"   ai={p.ai} team={p.team_id} name={p.name!r} ready={p.ready}")
    if not counts:
        print("No packets received.")


if __name__ == "__main__":
    main()
