"""Local SQLite store: settings, known careers and the event log cache.

The app always works from this local copy. Cloud sync only moves events in
and out of it, so a dropped connection never blocks capturing a race.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path

from ..career.models import Event


def data_dir() -> Path:
    override = os.environ.get("GRIDLINE_HOME")
    if override:
        p = Path(override)
    elif sys.platform == "win32":
        p = Path(os.environ.get("APPDATA", Path.home())) / "Gridline"
    elif sys.platform == "darwin":
        p = Path.home() / "Library" / "Application Support" / "Gridline"
    else:
        p = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "gridline"
    p.mkdir(parents=True, exist_ok=True)
    return p


SCHEMA = """
create table if not exists settings (key text primary key, value text not null);
create table if not exists careers (
    id text primary key,
    name text not null,
    member_id text not null,
    backend text not null,          -- json: {"type": "local"} or {"type": "supabase", "url":..., "key":...}
    last_seq integer not null default 0,
    added_at real not null
);
create table if not exists events (
    uid text primary key,
    career_id text not null,
    author text not null,
    kind text not null,
    payload text not null,
    created_at real not null,
    seq integer,
    pending integer not null default 0
);
create index if not exists events_career on events(career_id, seq);
"""


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "gridline.db"
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ------------------------------------------------------------- settings
    def get(self, key: str, default=None):
        with self._lock:
            row = self.db.execute("select value from settings where key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set(self, key: str, value) -> None:
        with self._lock:
            self.db.execute("insert or replace into settings(key, value) values(?, ?)", (key, json.dumps(value)))
            self.db.commit()

    # ------------------------------------------------------------- careers
    def add_career(self, career_id: str, name: str, member_id: str, backend: dict) -> None:
        with self._lock:
            self.db.execute(
                "insert or replace into careers(id, name, member_id, backend, last_seq, added_at) "
                "values(?, ?, ?, ?, coalesce((select last_seq from careers where id=?), 0), ?)",
                (career_id, name, member_id, json.dumps(backend), career_id, time.time()),
            )
            self.db.commit()

    def careers(self) -> list[dict]:
        with self._lock:
            rows = self.db.execute("select * from careers order by added_at").fetchall()
        return [dict(r) | {"backend": json.loads(r["backend"])} for r in rows]

    def career(self, career_id: str) -> dict | None:
        for c in self.careers():
            if c["id"] == career_id:
                return c
        return None

    def rename_career(self, career_id: str, name: str) -> None:
        with self._lock:
            self.db.execute("update careers set name=? where id=?", (name, career_id))
            self.db.commit()

    def remove_career(self, career_id: str) -> None:
        with self._lock:
            self.db.execute("delete from careers where id=?", (career_id,))
            self.db.execute("delete from events where career_id=?", (career_id,))
            self.db.commit()

    def set_last_seq(self, career_id: str, seq: int) -> None:
        with self._lock:
            self.db.execute("update careers set last_seq=max(last_seq, ?) where id=?", (seq, career_id))
            self.db.commit()

    # ------------------------------------------------------------- events
    def new_event(self, career_id: str, author: str, kind: str, payload: dict, local_only: bool) -> Event:
        ev = Event(uid=str(uuid.uuid4()), career_id=career_id, author=author, kind=kind,
                   payload=payload, created_at=time.time(), pending=not local_only)
        with self._lock:
            seq = None
            if local_only:
                row = self.db.execute("select coalesce(max(seq), 0) + 1 from events where career_id=?",
                                      (career_id,)).fetchone()
                seq = row[0]
                ev.seq = seq
            self.db.execute(
                "insert into events(uid, career_id, author, kind, payload, created_at, seq, pending) "
                "values(?, ?, ?, ?, ?, ?, ?, ?)",
                (ev.uid, career_id, author, kind, json.dumps(payload), ev.created_at, seq, int(ev.pending)),
            )
            self.db.commit()
        return ev

    def merge_remote(self, career_id: str, rows: list[dict]) -> int:
        """Insert events pulled from the cloud. Returns how many were new or newly confirmed."""
        changed = 0
        with self._lock:
            for r in rows:
                payload = r["payload"] if isinstance(r["payload"], str) else json.dumps(r["payload"])
                cur = self.db.execute("select seq, pending from events where uid=?", (str(r["uid"]),)).fetchone()
                if cur is None:
                    self.db.execute(
                        "insert into events(uid, career_id, author, kind, payload, created_at, seq, pending) "
                        "values(?, ?, ?, ?, ?, ?, ?, 0)",
                        (str(r["uid"]), career_id, r["author"], r["kind"], payload, r["created_at"], r["seq"]),
                    )
                    changed += 1
                elif cur["pending"] or cur["seq"] != r["seq"]:
                    self.db.execute("update events set seq=?, pending=0 where uid=?", (r["seq"], str(r["uid"])))
                    changed += 1
            if rows:
                last = max(r["seq"] for r in rows)
                self.db.execute("update careers set last_seq=max(last_seq, ?) where id=?", (last, career_id))
            self.db.commit()
        return changed

    def known_uids(self, career_id: str) -> set[str]:
        with self._lock:
            rows = self.db.execute("select uid from events where career_id=? and pending=0", (career_id,)).fetchall()
        return {r[0] for r in rows}

    def pending(self, career_id: str) -> list[Event]:
        return [e for e in self.events(career_id) if e.pending]

    def events(self, career_id: str) -> list[Event]:
        with self._lock:
            rows = self.db.execute(
                "select * from events where career_id=? order by seq is null, seq, created_at", (career_id,)
            ).fetchall()
        return [Event(uid=r["uid"], career_id=r["career_id"], author=r["author"], kind=r["kind"],
                      payload=json.loads(r["payload"]), created_at=r["created_at"], seq=r["seq"],
                      pending=bool(r["pending"])) for r in rows]
