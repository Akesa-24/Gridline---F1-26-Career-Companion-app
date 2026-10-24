import random

from gridline.telemetry import constants as C
from gridline.telemetry.packets import PACKET_SIZES, decode
from gridline.telemetry.session_tracker import SessionTracker
from gridline.tools.simulator import build_grid, simulate_session


def _packets(session_type, laps=5):
    rng = random.Random(1)
    cars = build_grid("williams", "haas", "Aleksa", "Jon", rng)
    return cars, [d for _, d in simulate_session(cars, session_type, 7, laps, rng, 12345, 9, 1, speed=500) if d]


def test_simulated_packets_match_spec_sizes():
    _, packets = _packets(15)
    seen = set()
    for data in packets:
        pkt = decode(data)
        if pkt is None:
            continue
        pid = pkt.header.packet_id
        seen.add(pid)
        assert pkt.header.packet_format == 2026
        if pid in PACKET_SIZES:
            assert len(data) == PACKET_SIZES[pid], C.PacketId.__dict__
    assert {C.PacketId.SESSION, C.PacketId.LAP_DATA, C.PacketId.PARTICIPANTS,
            C.PacketId.FINAL_CLASSIFICATION, C.PacketId.EVENT, C.PacketId.SESSION_HISTORY} <= seen


def test_tracker_emits_race_result_once():
    cars, packets = _packets(15)
    tr = SessionTracker()
    results = []
    for data in packets:
        pkt = decode(data)
        if pkt:
            results += [p for k, p in tr.feed(pkt) if k == "result"]
    assert len(results) == 1
    res = results[0]
    assert res["kind"] == "race" and res["track_id"] == 7
    assert len(res["entries"]) == 22
    assert [e["position"] for e in res["entries"]] == list(range(1, 23))
    humans = [e for e in res["entries"] if not e["ai"]]
    assert len(humans) == 2 and sum(e["is_local"] for e in humans) == 1
    assert res["fastest_lap"]["best_lap_ms"] == min(e["best_lap_ms"] for e in res["entries"] if e["best_lap_ms"])
    assert all(e["team_key"] in C.TEAMS_2026 for e in res["entries"])


def test_team_ids_cover_both_formats():
    assert C.team_key(476) == C.team_key(220) == "mercedes"
    assert C.team_key(486) == C.team_key(230) == "cadillac"


def test_wrong_format_raises():
    from gridline.telemetry.packets import HEADER_FMT, UnsupportedFormat
    data = HEADER_FMT.pack(2024, 24, 1, 0, 1, 1, 1, 0.0, 0, 0, 0, 255) + b"\0" * 900
    try:
        decode(data)
    except UnsupportedFormat as exc:
        assert exc.args[0] == 2024
    else:
        raise AssertionError("expected UnsupportedFormat")
