"""Binary decoding of the packets the companion needs (UDP format 2026).

Only the packets that feed the career are decoded: session, lap data, events,
participants, car status, final classification, session history and lobby info.
Everything is little-endian and packed, so plain `struct` formats line up with
the C structs in the spec byte for byte. The size of each struct is asserted at
import time so a spec change shows up immediately instead of as garbage data.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .constants import HEADER_SIZE, PacketId

# --------------------------------------------------------------------------- formats
HEADER_FMT = struct.Struct("<HBBBBBQfIIBB")
LAP_FMT = struct.Struct("<IIHBHBHBHBfffBBBBBBBBBBBBBBBHHBfB")
PARTICIPANT_FMT = struct.Struct("<BHHHBBB32sBBHBB12s")
FINAL_FMT = struct.Struct("<BBBBBBBIdBBB8s8s8s")
HISTORY_HEAD_FMT = struct.Struct("<BBBBBBB")
HISTORY_LAP_FMT = struct.Struct("<IHBHBHBB")
HISTORY_STINT_FMT = struct.Struct("<BBB")
CAR_STATUS_FMT = struct.Struct("<BBBBBfffHHBBHBBBbfffBffffB")
SESSION_PREFIX_FMT = struct.Struct("<BbbBHBbBHHBBBBBB")
LOBBY_FMT = struct.Struct("<BHBB32sBBBHB")

assert HEADER_FMT.size == HEADER_SIZE
assert LAP_FMT.size == 57
assert PARTICIPANT_FMT.size == 60
assert FINAL_FMT.size == 46
assert HISTORY_LAP_FMT.size == 14
assert CAR_STATUS_FMT.size == 59
assert SESSION_PREFIX_FMT.size == 19
assert LOBBY_FMT.size == 43

# --- format 2025 (game setting "UDP Format: 2025"): 22 cars, 8-bit ids, no ERS harvest limit
PARTICIPANT_FMT_2025 = struct.Struct("<BBBBBBB32sBBHBB12s")
CAR_STATUS_FMT_2025 = struct.Struct("<BBBBBfffHHBBHBBBbfffBfffB")
LOBBY_FMT_2025 = struct.Struct("<BBBB32sBBBHB")
assert PARTICIPANT_FMT_2025.size == 57
assert CAR_STATUS_FMT_2025.size == 55
assert LOBBY_FMT_2025.size == 42

PACKET_SIZES = {
    PacketId.SESSION: 926,
    PacketId.LAP_DATA: 1399,
    PacketId.EVENT: 45,
    PacketId.PARTICIPANTS: 1470,
    PacketId.CAR_STATUS: 1445,
    PacketId.FINAL_CLASSIFICATION: 1134,
    PacketId.LOBBY_INFO: 1062,
    PacketId.SESSION_HISTORY: 1460,
}

PACKET_SIZES_2025 = {
    PacketId.SESSION: 753,
    PacketId.LAP_DATA: 1285,
    PacketId.EVENT: 45,
    PacketId.PARTICIPANTS: 1284,
    PacketId.CAR_STATUS: 1239,
    PacketId.FINAL_CLASSIFICATION: 1042,
    PacketId.LOBBY_INFO: 954,
    PacketId.SESSION_HISTORY: 1460,
}


class Spec:
    """Per-format layout differences. Everything else is identical between 2025 and 2026."""

    def __init__(self, cars, participant, car_status, lobby, sizes):
        self.cars, self.participant, self.car_status, self.lobby, self.sizes = cars, participant, car_status, lobby, sizes


SPECS = {
    2026: Spec(24, PARTICIPANT_FMT, CAR_STATUS_FMT, LOBBY_FMT, PACKET_SIZES),
    2025: Spec(22, PARTICIPANT_FMT_2025, CAR_STATUS_FMT_2025, LOBBY_FMT_2025, PACKET_SIZES_2025),
}
SUPPORTED_FORMATS = tuple(SPECS)

# Offsets inside the session packet body (after the header)
_SESSION_MARSHAL_BYTES = 21 * 5
SESSION_SAFETY_CAR_OFFSET = SESSION_PREFIX_FMT.size + _SESSION_MARSHAL_BYTES  # 124
SESSION_NETWORK_GAME_OFFSET = SESSION_SAFETY_CAR_OFFSET + 1                    # 125
SESSION_AI_DIFFICULTY_OFFSET = SESSION_NETWORK_GAME_OFFSET + 2 + 64 * 8 + 1    # 640
SESSION_LINK_OFFSET = SESSION_AI_DIFFICULTY_OFFSET + 1                         # 641


def _cstr(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()


# --------------------------------------------------------------------------- data classes
@dataclass(slots=True)
class Header:
    packet_format: int
    game_year: int
    major: int
    minor: int
    packet_version: int
    packet_id: int
    session_uid: int
    session_time: float
    frame: int
    overall_frame: int
    player_car_index: int
    secondary_player_car_index: int


@dataclass(slots=True)
class SessionInfo:
    weather: int
    track_temp: int
    air_temp: int
    total_laps: int
    track_length: int
    session_type: int
    track_id: int
    formula: int
    time_left: int
    duration: int
    safety_car_status: int
    network_game: bool
    ai_difficulty: int
    season_link: int
    weekend_link: int
    session_link: int


@dataclass(slots=True)
class LapEntry:
    last_lap_ms: int
    current_lap_ms: int
    delta_front_ms: int
    delta_leader_ms: int
    lap_distance: float
    position: int
    current_lap: int
    pit_status: int
    pit_stops: int
    sector: int
    lap_invalid: bool
    penalties_s: int
    warnings: int
    grid_position: int
    driver_status: int
    result_status: int


@dataclass(slots=True)
class Participant:
    ai: bool
    driver_id: int
    network_id: int
    team_id: int
    race_number: int
    nationality: int
    name: str
    public_telemetry: bool
    platform: int


@dataclass(slots=True)
class ClassificationEntry:
    position: int
    laps: int
    grid: int
    points: int
    pit_stops: int
    result_status: int
    result_reason: int
    best_lap_ms: int
    total_time_s: float
    penalties_s: int
    num_penalties: int
    stints_visual: list[int] = field(default_factory=list)
    stint_end_laps: list[int] = field(default_factory=list)


@dataclass(slots=True)
class CarStatus:
    visual_tyre: int
    tyre_age: int
    fia_flag: int
    ers_store: float


@dataclass(slots=True)
class HistoryLap:
    lap_ms: int
    s1_ms: int
    s2_ms: int
    s3_ms: int
    valid: bool


@dataclass(slots=True)
class SessionHistory:
    car_idx: int
    num_laps: int
    best_lap_num: int
    laps: list[HistoryLap]


@dataclass(slots=True)
class LobbyPlayer:
    ai: bool
    team_id: int
    name: str
    car_number: int
    ready: int


@dataclass(slots=True)
class EventPacket:
    code: str
    vehicle_idx: int | None = None
    lap_time_s: float | None = None
    reason: int | None = None
    raw: bytes = b""


@dataclass(slots=True)
class Packet:
    header: Header
    body: object


class UnsupportedFormat(Exception):
    pass


# --------------------------------------------------------------------------- decoders
def parse_header(data: bytes) -> Header:
    return Header(*HEADER_FMT.unpack_from(data, 0))


def _session(data: bytes, spec: Spec) -> SessionInfo:
    b = HEADER_SIZE
    p = SESSION_PREFIX_FMT.unpack_from(data, b)
    sc, net = struct.unpack_from("<BB", data, b + SESSION_SAFETY_CAR_OFFSET)
    ai = data[b + SESSION_AI_DIFFICULTY_OFFSET]
    s_link, w_link, x_link = struct.unpack_from("<III", data, b + SESSION_LINK_OFFSET)
    return SessionInfo(
        weather=p[0], track_temp=p[1], air_temp=p[2], total_laps=p[3], track_length=p[4],
        session_type=p[5], track_id=p[6], formula=p[7], time_left=p[8], duration=p[9],
        safety_car_status=sc, network_game=bool(net), ai_difficulty=ai,
        season_link=s_link, weekend_link=w_link, session_link=x_link,
    )


def _lap_data(data: bytes, spec: Spec) -> list[LapEntry]:
    out = []
    for i in range(spec.cars):
        v = LAP_FMT.unpack_from(data, HEADER_SIZE + i * LAP_FMT.size)
        out.append(LapEntry(
            last_lap_ms=v[0], current_lap_ms=v[1],
            delta_front_ms=v[6] + v[7] * 60000,
            delta_leader_ms=v[8] + v[9] * 60000,
            lap_distance=v[10],
            position=v[13], current_lap=v[14], pit_status=v[15], pit_stops=v[16],
            sector=v[17], lap_invalid=bool(v[18]), penalties_s=v[19], warnings=v[20],
            grid_position=v[24], driver_status=v[25], result_status=v[26],
        ))
    return out


def _participants(data: bytes, spec: Spec) -> tuple[int, list[Participant]]:
    num = data[HEADER_SIZE]
    out = []
    fmt = spec.participant
    for i in range(spec.cars):
        v = fmt.unpack_from(data, HEADER_SIZE + 1 + i * fmt.size)
        out.append(Participant(
            ai=bool(v[0]), driver_id=v[1], network_id=v[2], team_id=v[3],
            race_number=v[5], nationality=v[6], name=_cstr(v[7]),
            public_telemetry=bool(v[8]), platform=v[11],
        ))
    return num, out


def _final(data: bytes, spec: Spec) -> tuple[int, list[ClassificationEntry]]:
    num = data[HEADER_SIZE]
    out = []
    for i in range(spec.cars):
        v = FINAL_FMT.unpack_from(data, HEADER_SIZE + 1 + i * FINAL_FMT.size)
        n = min(v[11], 8)
        out.append(ClassificationEntry(
            position=v[0], laps=v[1], grid=v[2], points=v[3], pit_stops=v[4],
            result_status=v[5], result_reason=v[6], best_lap_ms=v[7], total_time_s=v[8],
            penalties_s=v[9], num_penalties=v[10],
            stints_visual=list(v[13][:n]), stint_end_laps=list(v[14][:n]),
        ))
    return num, out


def _car_status(data: bytes, spec: Spec) -> list[CarStatus]:
    out = []
    fmt = spec.car_status
    for i in range(spec.cars):
        v = fmt.unpack_from(data, HEADER_SIZE + i * fmt.size)
        out.append(CarStatus(visual_tyre=v[14], tyre_age=v[15], fia_flag=v[16], ers_store=v[19]))
    return out


def _history(data: bytes, spec: Spec) -> SessionHistory:
    h = HISTORY_HEAD_FMT.unpack_from(data, HEADER_SIZE)
    base = HEADER_SIZE + HISTORY_HEAD_FMT.size
    laps = []
    for i in range(min(h[1], 100)):
        v = HISTORY_LAP_FMT.unpack_from(data, base + i * HISTORY_LAP_FMT.size)
        laps.append(HistoryLap(
            lap_ms=v[0], s1_ms=v[1] + v[2] * 60000, s2_ms=v[3] + v[4] * 60000,
            s3_ms=v[5] + v[6] * 60000, valid=bool(v[7] & 0x01),
        ))
    return SessionHistory(car_idx=h[0], num_laps=h[1], best_lap_num=h[3], laps=laps)


def _lobby(data: bytes, spec: Spec) -> tuple[int, list[LobbyPlayer]]:
    num = data[HEADER_SIZE]
    out = []
    fmt = spec.lobby
    for i in range(spec.cars):
        v = fmt.unpack_from(data, HEADER_SIZE + 1 + i * fmt.size)
        out.append(LobbyPlayer(ai=bool(v[0]), team_id=v[1], name=_cstr(v[4]), car_number=v[5], ready=v[9]))
    return num, out


def _event(data: bytes, spec: Spec) -> EventPacket:
    code = data[HEADER_SIZE:HEADER_SIZE + 4].decode("ascii", errors="replace")
    d = data[HEADER_SIZE + 4:]
    ev = EventPacket(code=code, raw=bytes(d))
    if code == "FTLP":
        ev.vehicle_idx, ev.lap_time_s = struct.unpack_from("<Bf", d, 0)
    elif code == "RTMT":
        ev.vehicle_idx, ev.reason = struct.unpack_from("<BB", d, 0)
    elif code in ("RCWN", "TMPT", "DTSV", "SGSV"):
        ev.vehicle_idx = d[0]
    elif code == "PENA":
        ev.vehicle_idx = d[2]
        ev.reason = d[0]
    return ev


_DECODERS = {
    PacketId.SESSION: _session,
    PacketId.LAP_DATA: _lap_data,
    PacketId.EVENT: _event,
    PacketId.PARTICIPANTS: _participants,
    PacketId.CAR_STATUS: _car_status,
    PacketId.FINAL_CLASSIFICATION: _final,
    PacketId.SESSION_HISTORY: _history,
    PacketId.LOBBY_INFO: _lobby,
}


def decode(data: bytes) -> Packet | None:
    """Decode one datagram. Returns None for packets the companion ignores."""
    if len(data) < HEADER_SIZE:
        return None
    header = parse_header(data)
    spec = SPECS.get(header.packet_format)
    if spec is None:
        raise UnsupportedFormat(header.packet_format)
    fn = _DECODERS.get(header.packet_id)
    if fn is None:
        return None
    expected = spec.sizes.get(header.packet_id)
    if expected is not None and len(data) < expected:
        return None
    return Packet(header, fn(data, spec))
