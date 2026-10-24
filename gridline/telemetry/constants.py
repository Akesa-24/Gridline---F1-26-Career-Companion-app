"""Lookup tables from the F1 25 '2026 Season Pack' UDP specification (packet format 2026)."""
from __future__ import annotations

PACKET_FORMAT = 2026
MAX_CARS = 24
HEADER_SIZE = 29

# Packet ids
class PacketId:
    MOTION = 0
    SESSION = 1
    LAP_DATA = 2
    EVENT = 3
    PARTICIPANTS = 4
    CAR_SETUPS = 5
    CAR_TELEMETRY = 6
    CAR_STATUS = 7
    FINAL_CLASSIFICATION = 8
    LOBBY_INFO = 9
    CAR_DAMAGE = 10
    SESSION_HISTORY = 11
    TYRE_SETS = 12
    MOTION_EX = 13
    TIME_TRIAL = 14
    LAP_POSITIONS = 15
    CAR_TELEMETRY_2 = 16


# The 2026 grid. Team ids 476-486 are what the game sends in format 2026.
# The same teams arrive as 220-230 if the game is set to the 2025 format
# (uint8 truncation), so both are mapped to the same canonical key.
TEAMS_2026: dict[str, dict] = {
    "mercedes":     {"name": "Mercedes",        "short": "MER", "colour": "#27F4D2", "ids": (476, 220, 0)},
    "ferrari":      {"name": "Ferrari",         "short": "FER", "colour": "#E8002D", "ids": (477, 221, 1)},
    "redbull":      {"name": "Red Bull Racing", "short": "RBR", "colour": "#3671C6", "ids": (478, 222, 2)},
    "williams":     {"name": "Williams",        "short": "WIL", "colour": "#64C4FF", "ids": (479, 223, 3)},
    "astonmartin":  {"name": "Aston Martin",    "short": "AMR", "colour": "#229971", "ids": (480, 224, 4)},
    "alpine":       {"name": "Alpine",          "short": "ALP", "colour": "#FF87BC", "ids": (481, 225, 5)},
    "rb":           {"name": "Racing Bulls",    "short": "RB",  "colour": "#6692FF", "ids": (482, 226, 6)},
    "haas":         {"name": "Haas",            "short": "HAA", "colour": "#B6BABD", "ids": (483, 227, 7)},
    "mclaren":      {"name": "McLaren",         "short": "MCL", "colour": "#FF8000", "ids": (484, 228, 8)},
    "audi":         {"name": "Audi",            "short": "AUD", "colour": "#D5001C", "ids": (485, 229, 9)},
    "cadillac":     {"name": "Cadillac",        "short": "CAD", "colour": "#C9B37E", "ids": (486, 230)},
}

TEAM_ID_TO_KEY: dict[int, str] = {}
for _key, _t in TEAMS_2026.items():
    for _id in _t["ids"]:
        TEAM_ID_TO_KEY.setdefault(_id, _key)

# Rough starting order of the grid, best first. Used only as a prior for the
# car-strength model until real results exist; the owner can edit it.
DEFAULT_TEAM_ORDER = [
    "mclaren", "mercedes", "redbull", "ferrari", "williams", "rb",
    "astonmartin", "haas", "audi", "alpine", "cadillac",
]


def team_key(team_id: int) -> str | None:
    return TEAM_ID_TO_KEY.get(team_id)


def team_name(key: str | None) -> str:
    if key and key in TEAMS_2026:
        return TEAMS_2026[key]["name"]
    return "Unknown team"


def team_colour(key: str | None) -> str:
    if key and key in TEAMS_2026:
        return TEAMS_2026[key]["colour"]
    return "#5B6B8C"


TRACKS: dict[int, dict] = {
    0:  {"name": "Melbourne",    "gp": "Australian GP",     "country": "AUS"},
    2:  {"name": "Shanghai",     "gp": "Chinese GP",        "country": "CHN"},
    3:  {"name": "Sakhir",       "gp": "Bahrain GP",        "country": "BHR"},
    4:  {"name": "Catalunya",    "gp": "Barcelona GP",      "country": "ESP"},
    5:  {"name": "Monaco",       "gp": "Monaco GP",         "country": "MON"},
    6:  {"name": "Montreal",     "gp": "Canadian GP",       "country": "CAN"},
    7:  {"name": "Silverstone",  "gp": "British GP",        "country": "GBR"},
    9:  {"name": "Hungaroring",  "gp": "Hungarian GP",      "country": "HUN"},
    10: {"name": "Spa",          "gp": "Belgian GP",        "country": "BEL"},
    11: {"name": "Monza",        "gp": "Italian GP",        "country": "ITA"},
    12: {"name": "Singapore",    "gp": "Singapore GP",      "country": "SGP"},
    13: {"name": "Suzuka",       "gp": "Japanese GP",       "country": "JPN"},
    14: {"name": "Yas Marina",   "gp": "Abu Dhabi GP",      "country": "UAE"},
    15: {"name": "Austin",       "gp": "United States GP",  "country": "USA"},
    16: {"name": "Interlagos",   "gp": "São Paulo GP",      "country": "BRA"},
    17: {"name": "Red Bull Ring","gp": "Austrian GP",       "country": "AUT"},
    19: {"name": "Mexico City",  "gp": "Mexico City GP",    "country": "MEX"},
    20: {"name": "Baku",         "gp": "Azerbaijan GP",     "country": "AZE"},
    26: {"name": "Zandvoort",    "gp": "Dutch GP",          "country": "NED"},
    27: {"name": "Imola",        "gp": "Emilia Romagna GP", "country": "ITA"},
    29: {"name": "Jeddah",       "gp": "Saudi Arabian GP",  "country": "KSA"},
    30: {"name": "Miami",        "gp": "Miami GP",          "country": "USA"},
    31: {"name": "Las Vegas",    "gp": "Las Vegas GP",      "country": "USA"},
    32: {"name": "Lusail",       "gp": "Qatar GP",          "country": "QAT"},
    39: {"name": "Silverstone Reverse", "gp": "Silverstone (Reverse)", "country": "GBR"},
    40: {"name": "Austria Reverse",     "gp": "Austria (Reverse)",     "country": "AUT"},
    41: {"name": "Zandvoort Reverse",   "gp": "Zandvoort (Reverse)",   "country": "NED"},
    42: {"name": "Madrid",       "gp": "Spanish GP",        "country": "ESP"},
}


def track_name(track_id: int | None) -> str:
    if track_id is None:
        return "—"
    return TRACKS.get(track_id, {}).get("name", f"Track {track_id}")


def track_gp(track_id: int | None) -> str:
    if track_id is None:
        return "—"
    return TRACKS.get(track_id, {}).get("gp", f"Track {track_id}")


# Session types (appendix, 2024+ numbering)
SESSION_TYPES = {
    0: "Unknown", 1: "Practice 1", 2: "Practice 2", 3: "Practice 3", 4: "Short Practice",
    5: "Qualifying 1", 6: "Qualifying 2", 7: "Qualifying 3", 8: "Short Qualifying",
    9: "One-Shot Qualifying", 10: "Sprint Shootout 1", 11: "Sprint Shootout 2",
    12: "Sprint Shootout 3", 13: "Short Sprint Shootout", 14: "One-Shot Sprint Shootout",
    15: "Race", 16: "Race 2", 17: "Race 3", 18: "Time Trial",
}

PRACTICE_TYPES = {1, 2, 3, 4}
QUALI_TYPES = {5, 6, 7, 8, 9}
QUALI_PART = {5: 1, 6: 2, 7: 3, 8: 3, 9: 3}  # how deep into qualifying this session is
RACE_TYPES = {15, 16, 17}   # on sprint weekends 15 is the sprint and 16 the Grand Prix
NETWORK_HUMAN_DRIVER_IDS = {255, 65535}
# Penalty types that are real penalties (not warnings, lap invalidations or reminders)
REAL_PENALTY_TYPES = {0, 1, 2, 4, 6}


def session_kind(session_type: int) -> str | None:
    """Map a raw session type onto the three kinds the career tracks."""
    if session_type in PRACTICE_TYPES:
        return "practice"
    if session_type in QUALI_TYPES:
        return "qualifying"
    if session_type in RACE_TYPES:
        return "race"
    return None


RESULT_STATUS = {
    0: "Invalid", 1: "Inactive", 2: "Active", 3: "Finished",
    4: "DNF", 5: "DSQ", 6: "NC", 7: "Retired",
}
CLASSIFIED_STATUSES = {2, 3}

# Visual tyre compounds
VISUAL_TYRES = {16: "S", 17: "M", 18: "H", 7: "I", 8: "W"}
TYRE_COLOURS = {"S": "#FF3B3B", "M": "#F7D23E", "H": "#E9EDF5", "I": "#3DD26A", "W": "#3B8CFF"}
