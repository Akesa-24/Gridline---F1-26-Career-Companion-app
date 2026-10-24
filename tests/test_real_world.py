"""Regression tests for things that only showed up with real game data / real users."""
import os
import random
import struct

import pytest

from gridline.career.identity import assign_driver_keys, fingerprint, names_match
from gridline.career.models import Member
from gridline.sync.supabase import BackendError, SupabaseBackend, is_secret_key, normalise_url
from gridline.telemetry import constants as C
from gridline.telemetry.packets import (
    CAR_STATUS_FMT_2025, HEADER_FMT, LOBBY_FMT_2025, PARTICIPANT_FMT_2025, decode,
)
from gridline.telemetry.session_tracker import SessionTracker
from gridline.tools.simulator import build_grid, simulate_session


def _hdr(fmt, pid, uid=99):
    return HEADER_FMT.pack(fmt, 25, 1, 26, 1, pid, uid, 1.0, 1, 1, 0, 255)


def test_format_2025_lobby_and_participants():
    d = bytearray(_hdr(2025, 9)); d.append(1)
    d += LOBBY_FMT_2025.pack(0, 223, 1, 1, "Aleksa…".encode(), 23, 1, 1, 0, 1)
    d += b"\0" * (954 - len(d))
    n, players = decode(bytes(d)).body
    assert n == 1 and C.team_key(players[0].team_id) == "williams"
    d = bytearray(_hdr(2025, 4)); d.append(22)
    for i in range(22):
        d += PARTICIPANT_FMT_2025.pack(1, i, 0, 220 + i // 2, 0, i, 1, b"X", 1, 1, 0, 1, 0, b"\0" * 12)
    assert len(decode(bytes(d)).body[1]) == 22
    d = _hdr(2025, 7) + b"".join(CAR_STATUS_FMT_2025.pack(0, 0, 1, 56, 0, 1., 1., 1., 1, 1, 8, 0, 0, 18, 17, i, 0,
                                                          0., 0., 0., 1, 0., 0., 0., 0) for i in range(22))
    assert [c.tyre_age for c in decode(d).body][:3] == [0, 1, 2]


def test_full_64bit_session_uid_survives_qt_signal():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QObject, Signal
    QCoreApplication.instance() or QCoreApplication([])
    rng = random.Random(2)
    cars = build_grid("williams", "haas", "A", "B", rng)
    tr = SessionTracker()
    got = []

    class Emitter(QObject):
        sig = Signal(object)
    em = Emitter()
    em.sig.connect(got.append)
    for _, data in simulate_session(cars, 15, 0, 3, rng, 2**64 - 7, 9, 1, speed=800):
        if data and (pkt := decode(data)):
            for kind, payload in tr.feed(pkt):
                em.sig.emit(payload)
    assert any(isinstance(p, dict) and p.get("session_uid") == str(2**64 - 7) for p in got)


def test_warnings_and_invalidated_laps_are_not_penalties():
    tr = SessionTracker()
    from gridline.telemetry.packets import EventPacket
    for ptype in (5, 10, 11, 3, 16):      # warning, lap invalidated..., reminder, retired
        tr._on_event(EventPacket("PENA", vehicle_idx=4, reason=ptype))
    assert tr.penalties.get(4, 0) == 0
    tr._on_event(EventPacket("PENA", vehicle_idx=4, reason=4))   # time penalty
    assert tr.penalties[4] == 1


def _result(team_id, driver_id):
    return {"session_type": 15, "track_id": 0, "kind": "race", "entries": [
        {"idx": 0, "position": 1, "team_id": team_id, "team_key": C.team_key(team_id), "ai": True,
         "driver_id": driver_id, "status": 3, "laps": 10, "name": "Max Verstappen"},
        {"idx": 1, "position": 2, "team_id": team_id, "team_key": C.team_key(team_id), "ai": False,
         "driver_id": 65535, "status": 3, "laps": 10, "name": "Player", "is_local": True},
        {"idx": 2, "position": 3, "team_id": 227, "team_key": "haas", "ai": False,
         "driver_id": 255, "status": 3, "laps": 10, "name": "Player"},
        {"idx": 3, "position": 4, "team_id": 227, "team_key": "haas", "ai": False,
         "driver_id": 255, "status": 3, "laps": 10, "name": "Player"},
    ]}


def test_fingerprint_and_keys_match_across_udp_formats():
    a, b = _result(478, 9), _result(222, 9)     # Red Bull as format 2026 vs 2025
    assert fingerprint(a) == fingerprint(b)
    m = {"A": Member("A", "Aleksa", "Aleksa", True)}
    assign_driver_keys(a, m, "A")
    keys = [e["driver_key"] for e in a["entries"]]
    assert keys[0] == "ai:9"
    assert keys[2] != keys[3]                   # two hidden-name strangers stay separate


def test_truncated_names_match():
    assert names_match("VeryLongGamerTagNa…", "VeryLongGamerTagName2005")
    assert not names_match("Ale", "Aleksa")
    assert names_match("aleksa_05", "Aleksa05")


def test_supabase_url_and_key_safety():
    assert normalise_url("https://supabase.com/dashboard/project/vuqghpdsnokqpswmiody") == \
        "https://vuqghpdsnokqpswmiody.supabase.co"
    assert normalise_url("https://abcdefghijklmnopqrst.supabase.co/rest/v1/") == "https://abcdefghijklmnopqrst.supabase.co"
    assert is_secret_key("sb_secret_abc")
    import base64
    import json
    claims = base64.urlsafe_b64encode(json.dumps({"role": "service_role"}).encode()).decode().rstrip("=")
    with pytest.raises(BackendError):
        SupabaseBackend("x", f"eyJhbGciOiJIUzI1NiJ9.{claims}.sig")
    assert not is_secret_key("sb_publishable_abc")


def test_sprint_weekend_keeps_gp_as_main_race(career):
    from gridline.career.engine import build_state
    career.race_round(1, types=(9, 15, 16))     # quali, sprint ('Race'), GP ('Race 2')
    st = build_state(career.events)
    assert st.season.race(1).session_type == 16
    assert st.season.sprint(1).session_type == 15
    assert st.season.next_round() == 2
    total = sum(d.points for d in st.season.drivers)
    assert total > 101          # GP + sprint points


def test_shortened_calendar_does_not_crash(career):
    from gridline.career.engine import build_state
    career.race_round(1); career.race_round(2); career.race_round(3)
    career.add("calendar_updated", "A", {"season": 1, "calendar": [0, 2]})
    st = build_state(career.events)
    assert st.season.track(3) is None
    assert st.season.next_round() is None
