"""Two PCs syncing through a fake Supabase backend."""
import copy

import pytest
from PySide6.QtCore import QCoreApplication

from gridline.core import AppCore
from gridline.sync import invite
from gridline.sync.store import Store
from gridline.tools.demo_career import run_session  # noqa: F401


class FakeBackend:
    def __init__(self):
        self.rows = []
        self.careers = {}

    def check(self):
        pass

    def create_career(self, cid, name):
        self.careers[cid] = name

    def career_exists(self, cid):
        return self.careers.get(cid)

    def push(self, rows):
        known = {r["uid"] for r in self.rows}
        for r in rows:
            if r["uid"] not in known:
                self.rows.append(dict(r, seq=len(self.rows) + 1))

    def recent_ids(self, cid, after):
        return [{"seq": r["seq"], "uid": r["uid"]} for r in self.rows if r["career_id"] == cid and r["seq"] > after]

    def pull_uids(self, cid, uids):
        return [copy.deepcopy(r) for r in self.rows if r["career_id"] == cid and r["uid"] in uids]

    def pull(self, cid, after, limit=500):
        return [copy.deepcopy(r) for r in self.rows if r["career_id"] == cid and r["seq"] > after][:limit]


@pytest.fixture
def server(monkeypatch):
    QCoreApplication.instance() or QCoreApplication([])
    fake = FakeBackend()
    monkeypatch.setattr("gridline.sync.worker.SupabaseBackend", lambda url, key: fake)
    monkeypatch.setattr("gridline.core.SupabaseBackend", lambda url, key: fake)
    monkeypatch.setattr("gridline.sync.worker.SyncWorker.start", lambda self: None)
    return fake


def _core(tmp_path, name):
    return AppCore(Store(tmp_path / f"{name}.db"))


def test_two_pcs_confirm_each_other(tmp_path, server, grid):
    rng, cars, humans = grid
    a = _core(tmp_path, "a")
    a.create_career("League", "Aleksa", "Aleksa", "williams", {"type": "supabase", "url": "x", "key": "k"})
    a.sync.sync_once()
    code = a.invite_code()
    assert invite.decode(code)["career_id"] == a.career["id"]

    b = _core(tmp_path, "b")
    b.join_career(b.preview_invite(code), "Jon", "Jon", "haas")
    b.sync.sync_once()
    a.sync.sync_once()
    a.rebuild(); b.rebuild()
    assert len(a.state.members) == len(b.state.members) == 2

    for st in (9, 15):
        res = run_session(cars, st, 0, rng, humans[0], 6)
        for core, idx in ((a, humans[0]), (b, humans[1])):
            r = copy.deepcopy(res)
            r["player_idx"] = idx
            for e in r["entries"]:
                e["is_local"] = e["idx"] == idx
            core.on_session_result(r)
        a.sync.sync_once(); b.sync.sync_once(); a.sync.sync_once()
        a.rebuild(); b.rebuild()

    for core in (a, b):
        rec = core.state.season.race(1)
        assert rec is not None and rec.status == "confirmed"
        assert core.state.season.next_round() == 2
    da = [(d.key, d.points) for d in a.state.season.drivers]
    db = [(d.key, d.points) for d in b.state.season.drivers]
    assert da == db


def test_late_copy_attaches_to_same_round(tmp_path, server, grid):
    """B pulls A's race (round advanced) before B's own capture is processed."""
    rng, cars, humans = grid
    a = _core(tmp_path, "a")
    a.create_career("League", "Aleksa", "Aleksa", "williams", {"type": "supabase", "url": "x", "key": "k"})
    a.sync.sync_once()
    b = _core(tmp_path, "b")
    b.join_career(b.preview_invite(a.invite_code()), "Jon", "Jon", "haas")
    b.sync.sync_once(); a.sync.sync_once(); a.rebuild()

    res = run_session(cars, 15, 0, rng, humans[0], 6)
    ra = copy.deepcopy(res)
    for e in ra["entries"]:
        e["is_local"] = e["idx"] == humans[0]
    a.on_session_result(ra)
    a.sync.sync_once(); b.sync.sync_once(); b.rebuild()
    assert b.state.season.next_round() == 2
    rb = copy.deepcopy(res)
    for e in rb["entries"]:
        e["is_local"] = e["idx"] == humans[1]
    b.on_session_result(rb)
    b.sync.sync_once(); b.rebuild()
    assert b.state.season.race(1).status == "confirmed"
    assert b.state.season.race(2) is None


def test_rejoin_reclaims_driver_and_blocks_duplicates(tmp_path, server):
    a = _core(tmp_path, "a")
    a.create_career("League", "Aleksa", "aleksa05", "williams", {"type": "supabase", "url": "x", "key": "k"})
    a.sync.sync_once()
    code = a.invite_code()
    # joining a career that's already on this PC is refused
    info = a.preview_invite(code)
    assert info["already_here"]
    with pytest.raises(invite.InvalidInvite):
        a.join_career(info, "Aleksa", "aleksa05", "williams")
    # leave, then rejoin as yourself: same member id, still owner, no duplicate driver
    owner_id = a.me
    a.leave_career()
    info = a.preview_invite(code)
    me = a.find_existing_member(info["state"], "Aleksa", "aleksa05")
    assert me is not None and me.id == owner_id
    a.join_career(info, "Aleksa", "aleksa05", "williams", reclaim=me)
    a.sync.sync_once(); a.rebuild()
    assert a.is_owner and len(a.state.members) == 1


def test_out_of_order_commit_is_recovered(tmp_path, server):
    a = _core(tmp_path, "a")
    a.create_career("League", "Aleksa", "Aleksa", "williams", {"type": "supabase", "url": "x", "key": "k"})
    a.sync.sync_once()
    cid = a.career["id"]
    # a row with a lower seq shows up after we've already advanced past it
    hidden = dict(server.rows[-1], uid="00000000-0000-0000-0000-00000000beef", kind="member_updated",
                  payload={"member_id": a.me, "display_name": "Late", "gamertag": "x"})
    server.rows.append(dict(server.rows[-1], uid="00000000-0000-0000-0000-00000000cafe",
                            kind="noop", seq=len(server.rows) + 2, payload={}))
    a.sync.sync_once()
    server.rows.append(dict(hidden, seq=len(server.rows)))   # seq lower than last_seq
    a.sync.sync_once(); a.rebuild()
    assert any(e.uid.endswith("beef") for e in a.store.events(cid))
