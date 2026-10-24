"""Fake F1 25 / 2026 Season Pack telemetry so the app can be developed without the game.

It encodes real format-2026 packets (same sizes as the spec), so the whole
pipeline — socket, decoder, tracker, career, sync — is exercised end to end.

    python -m gridline.tools.simulator --session weekend --speed 40
    python -m gridline.tools.simulator --session race --laps 12 --as-player 1

Running two copies with the same --seed and different --as-player values
mimics two PCs in the same online lobby, which is how result reconciliation
is tested.
"""
from __future__ import annotations

import argparse
import random
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Iterator

from gridline.career.grid import DEFAULT_GRID
from gridline.telemetry import constants as C
from gridline.telemetry.constants import PacketId
from gridline.telemetry.packets import (
    CAR_STATUS_FMT, FINAL_FMT, HEADER_FMT, HISTORY_HEAD_FMT, HISTORY_LAP_FMT,
    HISTORY_STINT_FMT, LAP_FMT, LOBBY_FMT, PACKET_SIZES, PARTICIPANT_FMT,
    SESSION_AI_DIFFICULTY_OFFSET, SESSION_LINK_OFFSET, SESSION_NETWORK_GAME_OFFSET,
    SESSION_PREFIX_FMT, SESSION_SAFETY_CAR_OFFSET,
)

TRACK_BASE_LAP = {0: 80.5, 2: 94.0, 13: 90.5, 3: 92.0, 29: 89.0, 30: 89.5, 6: 73.0, 5: 72.5,
                  4: 75.5, 17: 66.0, 7: 87.0, 10: 105.0, 9: 78.0, 26: 71.0, 11: 81.0,
                  42: 86.0, 20: 103.0, 12: 93.0, 15: 95.0, 19: 78.5, 16: 70.5, 31: 94.0,
                  32: 83.0, 14: 85.0}

TEAM_PACE = {k: i * 0.16 for i, k in enumerate(C.DEFAULT_TEAM_ORDER)}


@dataclass
class Car:
    idx: int
    name: str
    team_key: str
    driver_id: int
    race_number: int
    ai: bool
    skill: float
    laps: list[float] = field(default_factory=list)
    valid: list[bool] = field(default_factory=list)
    pit_lap: int = 0
    dnf_lap: int = 0


def team_id(key: str) -> int:
    return C.TEAMS_2026[key]["ids"][0]


def _header(pid: int, uid: int, t: float, frame: int, player: int) -> bytes:
    return HEADER_FMT.pack(C.PACKET_FORMAT, 25, 1, 26, 1, pid, uid, t, frame, frame, player, 255)


def _pad(data: bytes, pid: int) -> bytes:
    size = PACKET_SIZES[pid]
    return data + b"\x00" * (size - len(data))


def build_grid(local_team: str, other_team: str, local_name: str, other_name: str,
               rng: random.Random, two_players: bool = True) -> list[Car]:
    cars: list[Car] = []
    replaced = {local_team: 1, other_team: 1 if other_team != local_team else 0}
    for key, seats in DEFAULT_GRID.items():
        for seat, (did, name, num) in enumerate(seats):
            human = None
            if key == local_team and seat == replaced[local_team]:
                human = local_name
            elif two_players and key == other_team and seat == (0 if other_team == local_team else 1):
                human = other_name
            skill = rng.gauss(0, 0.18) if human is None else rng.gauss(-0.1, 0.12)
            cars.append(Car(
                idx=len(cars), name=human or name, team_key=key,
                driver_id=65535 if human else did, race_number=num if not human else 2 + len(cars),
                ai=human is None, skill=skill,
            ))
    return cars


def _session_packet(uid, t, frame, player, session_type, track_id, laps, time_left, link) -> bytes:
    body = bytearray(PACKET_SIZES[PacketId.SESSION] - C.HEADER_SIZE)
    SESSION_PREFIX_FMT.pack_into(body, 0, 0, 32, 24, laps, 5400, session_type, track_id, 0,
                                 time_left, 3600, 80, 0, 0, 255, 0, 0)
    body[SESSION_SAFETY_CAR_OFFSET] = 0
    body[SESSION_NETWORK_GAME_OFFSET] = 1
    body[SESSION_AI_DIFFICULTY_OFFSET] = 90
    struct.pack_into("<III", body, SESSION_LINK_OFFSET, 777, link, link * 10 + session_type)
    return _header(PacketId.SESSION, uid, t, frame, player) + bytes(body)


def _participants_packet(cars, uid, t, frame, player) -> bytes:
    out = bytearray(_header(PacketId.PARTICIPANTS, uid, t, frame, player))
    out.append(len(cars))
    for c in cars:
        out += PARTICIPANT_FMT.pack(int(c.ai), c.driver_id, 0 if c.ai else c.idx + 1,
                                    team_id(c.team_key), 0, c.race_number, 1,
                                    c.name.encode()[:31], 1, 1, 0, 1, 0, b"\x00" * 12)
    for _ in range(C.MAX_CARS - len(cars)):
        out += b"\x00" * PARTICIPANT_FMT.size
    return _pad(bytes(out), PacketId.PARTICIPANTS)


def _lobby_packet(cars, uid, frame, player) -> bytes:
    out = bytearray(_header(PacketId.LOBBY_INFO, uid, 0.0, frame, player))
    humans = [c for c in cars if not c.ai]
    out.append(len(humans))
    for c in humans:
        out += LOBBY_FMT.pack(0, team_id(c.team_key), 1, 1, c.name.encode()[:31], c.race_number, 1, 1, 0, 1)
    return _pad(bytes(out), PacketId.LOBBY_INFO)


def _event_packet(code: str, details: bytes, uid, t, frame, player) -> bytes:
    return _header(PacketId.EVENT, uid, t, frame, player) + code.encode() + details.ljust(12, b"\x00")


def _history_packet(car: Car, done: int, uid, t, frame, player) -> bytes:
    out = bytearray(_header(PacketId.SESSION_HISTORY, uid, t, frame, player))
    laps = car.laps[:done]
    valid_times = [(lt, i) for i, lt in enumerate(laps) if car.valid[i]]
    best = min(valid_times)[1] + 1 if valid_times else 0
    out += HISTORY_HEAD_FMT.pack(car.idx, len(laps), 1, best, best, best, best)
    for i in range(100):
        if i < len(laps):
            ms = int(laps[i] * 1000)
            s = ms // 3
            out += HISTORY_LAP_FMT.pack(ms, s % 60000, s // 60000, s % 60000, s // 60000,
                                        (ms - 2 * s) % 60000, (ms - 2 * s) // 60000,
                                        0x0F if car.valid[i] else 0x00)
        else:
            out += b"\x00" * HISTORY_LAP_FMT.size
    for i in range(8):
        out += HISTORY_STINT_FMT.pack(255 if i == 0 else 0, 18, 17) if i == 0 else b"\x00\x00\x00"
    return bytes(out)


def _car_status_packet(cars, ages, tyres, uid, t, frame, player) -> bytes:
    out = bytearray(_header(PacketId.CAR_STATUS, uid, t, frame, player))
    for c in cars:
        out += CAR_STATUS_FMT.pack(0, 0, 1, 56, 0, 10.0, 110.0, 5.0, 12000, 4000, 8, 0, 0,
                                   18, tyres[c.idx], ages[c.idx], 0, 0, 0, 3_000_000.0, 1,
                                   0, 0, 4_000_000.0, 0, 0)
    for _ in range(C.MAX_CARS - len(cars)):
        out += b"\x00" * CAR_STATUS_FMT.size
    return _pad(bytes(out), PacketId.CAR_STATUS)


def _gap_parts(ms: int) -> tuple[int, int]:
    ms = max(0, int(ms))
    return ms % 60000, ms // 60000


def simulate_session(cars: list[Car], session_type: int, track_id: int, laps: int,
                     rng: random.Random, uid: int, player: int, link: int,
                     speed: float = 30.0, tick: float = 0.25) -> Iterator[tuple[float, bytes]]:
    """Yields (real_seconds_to_wait, datagram)."""
    kind = C.session_kind(session_type)
    base = TRACK_BASE_LAP.get(track_id, 88.0)
    is_race = kind == "race"
    n_laps = laps if is_race else (8 if kind == "practice" else 4)

    for c in cars:
        c.laps, c.valid = [], []
        c.pit_lap = rng.randint(int(n_laps * 0.35), max(int(n_laps * 0.6), 2)) if is_race and n_laps > 4 else 0
        c.dnf_lap = rng.randint(2, n_laps) if is_race and rng.random() < 0.06 else 0
        for lap in range(n_laps):
            lt = base + TEAM_PACE[c.team_key] + c.skill + abs(rng.gauss(0, 0.25))
            if lap == 0 and is_race:
                lt += 4 + c.idx * 0.08
            if is_race:
                lt -= lap * 0.03  # fuel burn
            if c.pit_lap and lap + 1 == c.pit_lap:
                lt += 21.5
            if not is_race and lap % 2 == 0:
                lt += 18  # out laps / cool-down
            c.laps.append(lt)
            c.valid.append(rng.random() > 0.08)

    cum = {c.idx: [sum(c.laps[:i + 1]) for i in range(n_laps)] for c in cars}
    end_time = max(v[-1] for v in cum.values()) + 2
    grid = sorted(cars, key=lambda c: (TEAM_PACE[c.team_key] + c.skill + rng.gauss(0, 0.1)))
    grid_pos = {c.idx: i + 1 for i, c in enumerate(grid)}

    frame = 0
    t = 0.0
    yield 0.0, _lobby_packet(cars, 0, 0, player)
    hist_cursor = 0
    fastest = (10_000.0, -1)
    while t <= end_time:
        frame += 1
        # progress for each car
        prog = {}
        done_laps = {}
        for c in cars:
            cl = cum[c.idx]
            d = sum(1 for x in cl if x <= t)
            if c.dnf_lap and d >= c.dnf_lap:
                d = c.dnf_lap
            done_laps[c.idx] = d
            if d >= n_laps or (c.dnf_lap and d >= c.dnf_lap):
                frac = 0.0
            else:
                start = cl[d - 1] if d else 0.0
                frac = (t - start) / c.laps[d]
            prog[c.idx] = d + min(frac, 0.999)
        if is_race:
            order = sorted(cars, key=lambda c: (-(prog[c.idx] if not c.dnf_lap or done_laps[c.idx] < c.dnf_lap else -1),
                                                cum[c.idx][max(done_laps[c.idx] - 1, 0)]))
        else:
            def best_of(c):
                v = [lt for lt, ok in zip(c.laps[:done_laps[c.idx]], c.valid) if ok]
                return min(v) if v else 9e9
            order = sorted(cars, key=best_of)
        pos = {c.idx: i + 1 for i, c in enumerate(order)}
        leader = order[0]

        # fastest lap events
        for c in cars:
            d = done_laps[c.idx]
            if d and c.valid[d - 1] and c.laps[d - 1] < fastest[0]:
                fastest = (c.laps[d - 1], c.idx)
                yield 0.0, _event_packet("FTLP", struct.pack("<Bf", c.idx, fastest[0]), uid, t, frame, player)

        if frame % 4 == 1:
            time_left = int(max(0, (end_time - t))) if not is_race else 0
            yield 0.0, _session_packet(uid, t, frame, player, session_type, track_id, n_laps, time_left, link)
        if frame % 8 == 1:
            yield 0.0, _participants_packet(cars, uid, t, frame, player)

        lap_out = bytearray(_header(PacketId.LAP_DATA, uid, t, frame, player))
        ages, tyres = {}, {}
        for c in cars:
            d = done_laps[c.idx]
            finished = d >= n_laps
            dnf = c.dnf_lap and d >= c.dnf_lap
            status = 4 if dnf else (3 if finished else 2)
            gap = (prog[leader.idx] - prog[c.idx]) * base * 1000 if is_race else 0
            ahead = order[pos[c.idx] - 2] if pos[c.idx] > 1 else None
            interval = (prog[ahead.idx] - prog[c.idx]) * base * 1000 if (ahead and is_race) else 0
            gl, gm = _gap_parts(gap)
            il, im = _gap_parts(interval)
            pits = 1 if c.pit_lap and d >= c.pit_lap else 0
            ages[c.idx] = d - c.pit_lap if pits else d
            tyres[c.idx] = 18 if pits else 17
            last = int(c.laps[d - 1] * 1000) if d else 0
            lap_out += LAP_FMT.pack(last, 0, 0, 0, 0, 0, il, im, gl, gm, 0.0, 0.0, 0.0,
                                    pos[c.idx], min(d + 1, n_laps), 0, pits, 0, 0, 0, 0, 0, 0, 0,
                                    grid_pos[c.idx] if is_race else 0, 4, status, 0, 0, 0, 0, 0.0, 255)
        lap_out += b"\x00" * LAP_FMT.size * (C.MAX_CARS - len(cars)) + b"\xff\xff"
        yield 0.0, bytes(lap_out)
        yield 0.0, _car_status_packet(cars, ages, tyres, uid, t, frame, player)
        # cycle history packets, a few cars per tick
        for _ in range(4):
            c = cars[hist_cursor % len(cars)]
            hist_cursor += 1
            yield 0.0, _history_packet(c, done_laps[c.idx], uid, t, frame, player)

        t += tick * speed
        yield tick, b""

    # Final state: everyone has finished (or retired) — recompute order from scratch
    done_laps = {c.idx: (c.dnf_lap if c.dnf_lap else n_laps) for c in cars}
    if is_race:
        order = sorted(cars, key=lambda c: (-done_laps[c.idx], cum[c.idx][done_laps[c.idx] - 1]))
    else:
        def best_final(c):
            v = [lt for lt, ok in zip(c.laps, c.valid) if ok]
            return min(v) if v else 9e9
        order = sorted(cars, key=best_final)
    pos = {c.idx: i + 1 for i, c in enumerate(order)}

    # Make sure every car's history is complete before classification
    for c in cars:
        yield 0.0, _history_packet(c, done_laps[c.idx], uid, t, frame, player)

    yield 0.0, _event_packet("CHQF", b"", uid, t, frame, player)
    # final classification
    out = bytearray(_header(PacketId.FINAL_CLASSIFICATION, uid, t, frame, player))
    out.append(len(cars))
    pts_table = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
    for c in cars:
        d = done_laps[c.idx]
        p = pos[c.idx]
        valid_laps = [lt for lt, ok in zip(c.laps[:d], c.valid) if ok]
        best = int(min(valid_laps) * 1000) if valid_laps else 0
        dnf = bool(c.dnf_lap and d >= c.dnf_lap)
        status = 4 if dnf else 3
        pts = pts_table[p - 1] if (is_race and p <= 10 and not dnf) else 0
        pits = 1 if c.pit_lap and d >= c.pit_lap else 0
        stints = (b"\x11\x12" if pits else b"\x11").ljust(8, b"\x00")
        ends = (bytes([c.pit_lap, d]) if pits else bytes([d])).ljust(8, b"\x00")
        out += FINAL_FMT.pack(p, d, grid_pos[c.idx] if is_race else p, pts, pits, status,
                              1 if dnf else 2, best, cum[c.idx][d - 1] if d else 0.0, 0, 0,
                              1 + pits, stints, stints, ends)
    for _ in range(C.MAX_CARS - len(cars)):
        out += b"\x00" * FINAL_FMT.size
    yield 0.5, bytes(out)
    yield 0.0, _event_packet("SEND", b"", uid, t, frame, player)


def weekend(session: str) -> list[int]:
    return {"practice": [1], "quali": [9], "race": [15], "weekend": [1, 9, 15],
            "full": [1, 2, 3, 5, 6, 7, 15]}[session]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=20777)
    ap.add_argument("--session", default="weekend", choices=["practice", "quali", "race", "weekend", "full"])
    ap.add_argument("--track", type=int, default=0, help="track id (0 = Melbourne)")
    ap.add_argument("--laps", type=int, default=10)
    ap.add_argument("--speed", type=float, default=30.0, help="simulation speed multiplier")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--local-team", default="williams")
    ap.add_argument("--other-team", default="haas")
    ap.add_argument("--local-name", default="Player One")
    ap.add_argument("--other-name", default="Player Two")
    ap.add_argument("--as-player", type=int, default=0, choices=[0, 1],
                    help="which human this PC is (0 = local-name, 1 = other-name)")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rng = random.Random(args.seed)
    cars = build_grid(args.local_team, args.other_team, args.local_name, args.other_name, rng)
    humans = [c.idx for c in cars if not c.ai]
    player_idx = humans[args.as_player] if len(humans) > args.as_player else humans[0]
    link = rng.randint(1000, 9999)
    for st in weekend(args.session):
        uid = rng.getrandbits(64)
        print(f"-> {C.SESSION_TYPES[st]} at {C.track_name(args.track)}")
        for wait, data in simulate_session(cars, st, args.track, args.laps, rng, uid, player_idx, link, args.speed):
            if wait:
                time.sleep(wait)
            if data:
                sock.sendto(data, (args.host, args.port))
        time.sleep(1.5)
    print("done")


if __name__ == "__main__":
    main()
