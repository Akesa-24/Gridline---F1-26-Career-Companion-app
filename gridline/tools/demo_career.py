"""Seed a local demo career with simulated rounds, to explore the app without the game.

    python -m gridline.tools.demo_career --rounds 8

It runs the real simulator → decoder → tracker pipeline for every session, so
the data looks exactly like captured telemetry.
"""
from __future__ import annotations

import argparse
import copy
import random
import uuid

from gridline.career.engine import build_state
from gridline.career.identity import assign_driver_keys, fingerprint, strip_for_upload
from gridline.career.models import Member
from gridline.sync.store import Store
from gridline.telemetry.packets import decode
from gridline.telemetry.session_tracker import SessionTracker
from gridline.tools.simulator import build_grid, simulate_session


def run_session(cars, session_type, track, rng, player_idx, laps):
    tr = SessionTracker()
    result = None
    for _, data in simulate_session(cars, session_type, track, laps, rng, rng.getrandbits(63),
                                    player_idx, 1, speed=1000, tick=0.5):
        if not data:
            continue
        pkt = decode(data)
        if pkt is None:
            continue
        for kind, payload in tr.feed(pkt):
            if kind == "result":
                result = payload
    return result


def seed(store: Store, rounds: int, name: str = "Demo League", me: str = "Aleksa", friend: str = "Jón",
         my_team: str = "williams", friend_team: str = "haas", laps: int = 12, seed_: int = 11) -> str:
    cid = str(uuid.uuid4())
    a, b = uuid.uuid4().hex[:12], uuid.uuid4().hex[:12]
    store.add_career(cid, name, a, {"type": "local"})
    store.new_event(cid, a, "career_created", {"name": name, "seed": 4242, "config": {}}, True)
    store.new_event(cid, a, "member_joined", {"member_id": a, "display_name": me, "gamertag": me,
                                              "team_key": my_team, "season": 1}, True)
    store.new_event(cid, b, "member_joined", {"member_id": b, "display_name": friend, "gamertag": friend,
                                              "team_key": friend_team, "season": 1}, True)
    rng = random.Random(seed_)
    cars = build_grid(my_team, friend_team, me, friend, rng)
    humans = [c.idx for c in cars if not c.ai]
    members = {a: Member(a, me, me, True), b: Member(b, friend, friend)}
    for rnd in range(1, rounds + 1):
        st = build_state(store.events(cid))
        track = st.season.calendar[rnd - 1]
        for c in cars:   # a little form drift between weekends
            if not c.ai:
                c.skill += rng.gauss(-0.03, 0.05)
        for stype in (1, 9, 15):
            res = run_session(cars, stype, track, rng, humans[0], laps)
            for author, local_idx in ((a, humans[0]), (b, humans[1])):
                if stype == 1 and author == b:
                    continue  # only one PC recorded practice
                r = copy.deepcopy(res)
                for e in r["entries"]:
                    e["is_local"] = e["idx"] == local_idx
                assign_driver_keys(r, members, author)
                store.new_event(cid, author, "result_submitted",
                                {"season": 1, "round": rnd, "result": strip_for_upload(r),
                                 "fingerprint": fingerprint(r)}, True)
    store.set("active_career", cid)
    return cid


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--laps", type=int, default=12)
    args = ap.parse_args()
    store = Store()
    cid = seed(store, args.rounds, laps=args.laps)
    print(f"Demo career created ({cid}). Start the app to explore it.")


if __name__ == "__main__":
    main()
