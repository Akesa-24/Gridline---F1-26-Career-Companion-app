import copy
import os
import random
import sys
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gridline.career.identity import assign_driver_keys, fingerprint, strip_for_upload  # noqa: E402
from gridline.career.models import Event, Member  # noqa: E402
from gridline.tools.demo_career import run_session  # noqa: E402
from gridline.tools.simulator import build_grid  # noqa: E402


class Log:
    """Builds an ordered event log the way the server would."""

    def __init__(self):
        self.events: list[Event] = []

    def add(self, kind, author, payload):
        seq = len(self.events) + 1
        self.events.append(Event(str(uuid.uuid4()), "c1", author, kind, payload, time.time() + seq, seq))
        return self.events[-1]


@pytest.fixture
def grid():
    rng = random.Random(3)
    cars = build_grid("williams", "haas", "Aleksa", "Jon", rng)
    humans = [c.idx for c in cars if not c.ai]
    return rng, cars, humans


@pytest.fixture
def members():
    return {"A": Member("A", "Aleksa", "Aleksa", True), "B": Member("B", "Jon", "Jon")}


def capture(res, author, local_idx, members):
    r = copy.deepcopy(res)
    for e in r["entries"]:
        e["is_local"] = e["idx"] == local_idx
    assign_driver_keys(r, members, author)
    return {"result": strip_for_upload(r), "fingerprint": fingerprint(r)}


@pytest.fixture
def career(grid, members):
    """A log with a created career, two members and a helper to race rounds."""
    rng, cars, humans = grid
    log = Log()
    log.add("career_created", "A", {"name": "Test", "seed": 99, "config": {"calendar": [0, 2, 13, 3, 29, 30]}})
    log.add("member_joined", "A", {"member_id": "A", "display_name": "Aleksa", "gamertag": "Aleksa", "team_key": "williams", "season": 1})
    log.add("member_joined", "B", {"member_id": "B", "display_name": "Jon", "gamertag": "Jon", "team_key": "haas", "season": 1})

    def race_round(rnd, season=1, both=True, types=(9, 15)):
        for st in types:
            res = run_session(cars, st, 0, rng, humans[0], 6)
            for author, idx in (("A", humans[0]), ("B", humans[1])):
                if author == "B" and not both:
                    continue
                log.add("result_submitted", author, {"season": season, "round": rnd, **capture(res, author, idx, members)})
        return res

    log.race_round = race_round
    log.rng, log.cars, log.humans = rng, cars, humans
    return log
