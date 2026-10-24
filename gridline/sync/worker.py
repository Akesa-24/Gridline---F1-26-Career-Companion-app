"""Background sync loop: push pending local events, pull new remote ones."""
from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QThread, Signal

from .store import Store
from .supabase import BackendError, SchemaMissing, SupabaseBackend

POLL_SECONDS = 4.0
IDLE_POLL_SECONDS = 15.0
OVERLAP = 50


class SyncWorker(QThread):
    changed = Signal()            # new events landed in the local store
    status = Signal(str, str)     # state (online | offline | error | schema | local), detail

    def __init__(self, store: Store, career: dict):
        super().__init__()
        self.store = store
        self.career = career
        self._wake = threading.Event()
        self._stop = False
        self.idle = False
        b = career["backend"]
        self.backend = SupabaseBackend(b["url"], b["key"]) if b.get("type") == "supabase" else None

    def poke(self) -> None:
        self._wake.set()

    def request_stop(self) -> None:
        self._stop = True
        self._wake.set()

    def stop(self) -> None:
        self.request_stop()
        self.wait(9000)

    def sync_once(self) -> int:
        cid = self.career["id"]
        pending = self.store.pending(cid)
        if pending:
            self.backend.push([e.to_row() for e in pending])
        total = 0
        career = self.store.career(cid)
        if career is None:          # removed while we were syncing
            return 0
        # Rows can commit out of seq order when both PCs upload at once; re-check the
        # last stretch by id (cheap) and fetch anything we never saw.
        last = career.get("last_seq", 0)
        if last:
            known = self.store.known_uids(cid)
            missing = [r["uid"] for r in self.backend.recent_ids(cid, max(0, last - OVERLAP))
                       if str(r["uid"]) not in known]
            if missing:
                total += self.store.merge_remote(cid, self.backend.pull_uids(cid, missing[:100]))
        while not self._stop:
            career = self.store.career(cid)
            if career is None:
                break
            rows = self.backend.pull(cid, career.get("last_seq", 0))
            total += self.store.merge_remote(cid, rows)
            if len(rows) < 500:
                break
        return total

    def run(self) -> None:
        if self.backend is None:
            self.status.emit("local", "Local career — not shared")
            return
        failures = 0
        while not self._stop:
            try:
                n = self.sync_once()
                failures = 0
                self.status.emit("online", "Synced")
                if n:
                    self.changed.emit()
            except SchemaMissing:
                self.status.emit("schema", "Database tables missing — run the setup SQL")
            except BackendError as exc:
                failures += 1
                self.status.emit("offline" if "reach" in str(exc) else "error", str(exc))
            except Exception as exc:   # never let the sync thread die silently
                failures += 1
                traceback.print_exc()
                self.status.emit("error", f"Sync error: {exc.__class__.__name__}: {exc}")
            delay = POLL_SECONDS if not self.idle else IDLE_POLL_SECONDS
            delay = min(delay * (2 ** min(failures, 3)), 60)
            self._wake.wait(delay)
            self._wake.clear()
