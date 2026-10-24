"""Career setup (create / join) and the capture review dialog."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QDialog, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit,
    QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from ..sync import invite
from ..sync.supabase import SchemaMissing, SupabaseBackend, schema_sql
from ..telemetry import constants as C
from .theme import P, font
from .widgets import icons
from .widgets.common import Card, button, label


_LIVE_WORKERS: set = set()   # keeps running workers alive even if their dialog is closed


class _Worker(QThread):
    done = Signal(object, object)   # result, error

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        _LIVE_WORKERS.add(self)
        self.finished.connect(lambda: _LIVE_WORKERS.discard(self))

    def run(self):
        try:
            self.done.emit(self.fn(), None)
        except Exception as exc:  # surfaced in the dialog
            self.done.emit(None, exc)


class TeamTile(QAbstractButton):
    def __init__(self, key: str, note: str = ""):
        super().__init__()
        self.key = key
        self.note = note
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(QSize(150, 64))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        col = QColor(C.team_colour(self.key))
        bg = QColor(P.card2 if not self.isChecked() else P.card3)
        if self.underMouse() and not self.isChecked():
            bg = QColor(P.card3)
        p.setBrush(bg)
        p.setPen(QPen(col if self.isChecked() else QColor(P.line2), 2 if self.isChecked() else 1))
        p.drawRoundedRect(r, 8, 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(r.left() + 10, r.top() + 12, 4, r.height() - 24), 2, 2)
        p.setPen(QColor(P.text))
        p.setFont(font(10.5, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + 22, r.top() + 10, r.width() - 26, 22),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, C.team_name(self.key))
        p.setPen(QColor(P.text3))
        p.setFont(font(8.5))
        p.drawText(QRectF(r.left() + 22, r.top() + 32, r.width() - 26, 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.note or C.TEAMS_2026[self.key]["short"])


class TeamPicker(QWidget):
    changed = Signal(str)

    def __init__(self, notes: dict[str, str] | None = None):
        super().__init__()
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(10)
        self.group = QButtonGroup(self)
        self.tiles: dict[str, TeamTile] = {}
        for i, key in enumerate(C.DEFAULT_TEAM_ORDER):
            t = TeamTile(key, (notes or {}).get(key, ""))
            self.group.addButton(t)
            self.tiles[key] = t
            g.addWidget(t, i // 4, i % 4)
            t.clicked.connect(lambda _=False, k=key: self.changed.emit(k))

    def set_notes(self, notes: dict[str, str]) -> None:
        for k, t in self.tiles.items():
            t.note = notes.get(k, "")
            t.update()

    def value(self) -> str | None:
        for k, t in self.tiles.items():
            if t.isChecked():
                return k
        return None


class Step(QWidget):
    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(14)
        t = label(title)
        t.setFont(font(18, QFont.Weight.Bold))
        self.v.addWidget(t)
        if subtitle:
            self.v.addWidget(label(subtitle, "muted", wrap=True))


class SetupDialog(QDialog):
    """Create or join a career. mode = 'create' | 'join'."""

    def __init__(self, core, mode: str, parent=None):
        super().__init__(parent)
        self.core = core
        self.mode = mode
        self.setWindowTitle("New career" if mode == "create" else "Join a career")
        self.setMinimumSize(720, 560)
        self.preview = None
        self.worker = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 24)
        outer.setSpacing(18)
        self.progress = label("", "section")
        outer.addWidget(self.progress)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.error = label("", wrap=True)
        self.error.setStyleSheet(f"color: {P.bad};")
        outer.addWidget(self.error)
        nav = QHBoxLayout()
        self.back = button("Back", "ghost")
        self.back.clicked.connect(self._back)
        self.next = button("Continue", "primary")
        self.next.clicked.connect(self._next)
        nav.addWidget(self.back)
        nav.addStretch(1)
        nav.addWidget(self.next)
        outer.addLayout(nav)

        self.name = QLineEdit()
        self.display = QLineEdit()
        self.tag = QLineEdit()
        self.tag.setPlaceholderText("Exactly as it appears in online lobbies")
        self.picker = TeamPicker()

        if mode == "create":
            self.steps = [self._step_career(), self._step_team(), self._step_storage(), self._step_done()]
        else:
            self.steps = [self._step_invite(), self._step_driver(), self._step_team(), self._step_joined()]
        for s in self.steps:
            self.stack.addWidget(s)
        self._update_nav()

    # ------------------------------------------------------------------ steps
    def _step_career(self) -> Step:
        s = Step("Set up the career", "You're the owner: you host the shared database, set the rules and rule on disputed results.")
        f = QFormLayout()
        f.setVerticalSpacing(12)
        f.setHorizontalSpacing(18)
        self.name.setPlaceholderText("e.g. Reykjavík Racing League")
        self.display.setPlaceholderText("How you appear in the standings")
        f.addRow(label("Career name", "muted"), self.name)
        f.addRow(label("Your name", "muted"), self.display)
        f.addRow(label("In-game name", "muted"), self.tag)
        s.v.addLayout(f)
        s.v.addWidget(label("Your in-game name is how the other player's PC recognises your car in the lobby.", "faint", wrap=True))
        s.v.addStretch(1)
        return s

    def _step_driver(self) -> Step:
        s = Step("Your driver")
        f = QFormLayout()
        f.setVerticalSpacing(12)
        f.setHorizontalSpacing(18)
        self.display.setPlaceholderText("How you appear in the standings")
        f.addRow(label("Your name", "muted"), self.display)
        f.addRow(label("In-game name", "muted"), self.tag)
        s.v.addLayout(f)
        self.join_summary = label("", "muted", wrap=True)
        s.v.addWidget(self.join_summary)
        s.v.addStretch(1)
        return s

    def _step_team(self) -> Step:
        s = Step("Pick your first team", "You'll take one of their seats in the lobby. Your rating is judged against "
                 "the car, so a back-marker is a perfectly good place to start.")
        s.v.addWidget(self.picker)
        s.v.addStretch(1)
        return s

    def _step_storage(self) -> Step:
        s = Step("Where the career lives")
        self.storage_group = QButtonGroup(self)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.opt_shared = button("Shared  ·  free Supabase project")
        self.opt_local = button("This PC only")
        for b in (self.opt_shared, self.opt_local):
            b.setCheckable(True)
            b.setMinimumHeight(44)
            self.storage_group.addButton(b)
            row.addWidget(b)
        self.opt_shared.setChecked(True)
        self.opt_shared.setStyleSheet(f"QPushButton:checked {{ border: 1px solid {P.accent}; background: {P.accent_dim}; }}")
        self.opt_local.setStyleSheet(f"QPushButton:checked {{ border: 1px solid {P.accent}; background: {P.accent_dim}; }}")
        s.v.addLayout(row)

        self.shared_box = QWidget()
        sv = QVBoxLayout(self.shared_box)
        sv.setContentsMargins(0, 4, 0, 0)
        sv.setSpacing(10)
        steps = Card(padding=16, spacing=6)
        for i, t in enumerate((
            "Create a free project at supabase.com (no card needed).",
            "Open SQL Editor → New query, paste the setup SQL and press Run.",
            "Go to Project Settings → API and copy the Project URL and the anon / publishable key.",
        ), 1):
            steps.add(label(f"{i}.  {t}", "muted", wrap=True))
        cp = button("Copy setup SQL", None, icons.icon("copy", P.text))
        cp.clicked.connect(lambda: (QGuiApplication.clipboard().setText(schema_sql()),
                                    self.core.toast.emit("ok", "Setup SQL copied")))
        steps.add_right(cp)
        sv.addWidget(steps)
        f = QFormLayout()
        f.setVerticalSpacing(10)
        f.setHorizontalSpacing(18)
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://abcdefgh.supabase.co")
        self.key = QLineEdit()
        self.key.setPlaceholderText("eyJhbGciOi…  or  sb_publishable_…")
        self.key.setProperty("mono", True)
        f.addRow(label("Project URL", "muted"), self.url)
        f.addRow(label("Public key", "muted"), self.key)
        sv.addLayout(f)
        test = QHBoxLayout()
        self.test_btn = button("Test connection")
        self.test_btn.clicked.connect(self._test)
        self.test_result = label("", "faint", wrap=True)
        test.addWidget(self.test_btn)
        test.addWidget(self.test_result, 1)
        sv.addLayout(test)
        s.v.addWidget(self.shared_box)
        self.local_note = label("Everything is saved on this PC. Good for trying the app out or racing solo; "
                                "it can't be shared later.", "muted", wrap=True)
        s.v.addWidget(self.local_note)
        self.local_note.hide()
        self.storage_group.buttonClicked.connect(self._storage_changed)
        s.v.addStretch(1)
        return s

    def _step_done(self) -> Step:
        s = Step("Career created", "Send this invite code to the other player. In Gridline they choose "
                 "“Join a career” and paste it.")
        self.code_edit = QLineEdit()
        self.code_edit.setReadOnly(True)
        self.code_edit.setProperty("mono", True)
        row = QHBoxLayout()
        row.addWidget(self.code_edit, 1)
        cp = button("Copy", None, icons.icon("copy", P.text))
        cp.clicked.connect(lambda: (QGuiApplication.clipboard().setText(self.code_edit.text()),
                                    self.core.toast.emit("ok", "Invite code copied")))
        row.addWidget(cp)
        s.v.addLayout(row)
        self.done_note = label("You can find the code again under Settings › Sharing.", "faint", wrap=True)
        s.v.addWidget(self.done_note)
        s.v.addStretch(1)
        return s

    def _step_invite(self) -> Step:
        s = Step("Join a career", "Paste the invite code the career owner sent you.")
        self.code_in = QLineEdit()
        self.code_in.setPlaceholderText("GRID-…")
        self.code_in.setProperty("mono", True)
        s.v.addWidget(self.code_in)
        self.invite_info = label("", "muted", wrap=True)
        s.v.addWidget(self.invite_info)
        s.v.addStretch(1)
        return s

    def _step_joined(self) -> Step:
        s = Step("You're in", "Results from both PCs now sync automatically. Load into the lobby with the "
                 "2026 cars and take your seat.")
        s.v.addStretch(1)
        return s

    # ------------------------------------------------------------------ logic
    def _storage_changed(self) -> None:
        shared = self.opt_shared.isChecked()
        self.shared_box.setVisible(shared)
        self.local_note.setVisible(not shared)

    def _run(self, fn, on_done) -> None:
        """Run fn off the GUI thread; on_done(result, error) is called back on the GUI thread."""
        if self.worker is not None and self.worker.isRunning():
            return                      # one network job at a time (double clicks)
        self._busy(True)
        self._on_done = on_done
        self.worker = _Worker(fn)
        self.worker.done.connect(self._worker_done)   # bound method -> queued to the GUI thread
        self.worker.start()

    def _busy(self, on: bool) -> None:
        self.next.setEnabled(not on)
        self.back.setEnabled(not on)
        if hasattr(self, "test_btn"):
            self.test_btn.setEnabled(not on)

    def _worker_done(self, res, err) -> None:
        self._busy(False)
        if not self.isVisible():        # dialog was cancelled while the request ran
            return
        self._on_done(res, err)

    def _test(self) -> None:
        url, key = self.url.text().strip(), self.key.text().strip()
        if not url or not key:
            self.test_result.setText("Fill in both fields first.")
            return
        self.test_result.setText("Checking…")

        def done(_res, err):
            if err is None:
                self.test_result.setText("Connected — tables found.")
                self.test_result.setStyleSheet(f"color: {P.ok};")
            elif isinstance(err, SchemaMissing):
                self.test_result.setText("Connected, but the tables aren't there yet. Run the setup SQL, then test again.")
                self.test_result.setStyleSheet(f"color: {P.warn};")
            else:
                self.test_result.setText(str(err))
                self.test_result.setStyleSheet(f"color: {P.bad};")
        self._run(lambda: SupabaseBackend(url, key).check(), done)

    def _update_nav(self) -> None:
        i = self.stack.currentIndex()
        n = len(self.steps)
        self.progress.setText(f"STEP {min(i + 1, n - 1)} OF {n - 1}" if i < n - 1 else "DONE")
        self.back.setVisible(0 < i < n - 1)
        if i == n - 1:
            self.next.setText("Open career")
        elif i == n - 2:
            self.next.setText("Create career" if self.mode == "create" else "Join career")
        elif self.mode == "join" and i == 0:
            self.next.setText("Check code")
        else:
            self.next.setText("Continue")
        self.error.setText("")

    def _back(self) -> None:
        self.stack.setCurrentIndex(max(0, self.stack.currentIndex() - 1))
        self._update_nav()

    def _advance(self) -> None:
        self.stack.setCurrentIndex(self.stack.currentIndex() + 1)
        self._update_nav()

    def _fail(self, msg: str) -> None:
        self.error.setText(msg)

    def _next(self) -> None:
        i = self.stack.currentIndex()
        if i == len(self.steps) - 1:
            self.accept()
            return
        if self.mode == "create":
            self._next_create(i)
        else:
            self._next_join(i)

    def _next_create(self, i: int) -> None:
        if i == 0:
            if not self.name.text().strip() or not self.display.text().strip():
                return self._fail("Give the career and yourself a name.")
            self._advance()
        elif i == 1:
            if not self.picker.value():
                return self._fail("Pick a team.")
            self._advance()
        elif i == 2:
            shared = self.opt_shared.isChecked()
            backend = {"type": "local"}
            if shared:
                url, key = self.url.text().strip(), self.key.text().strip()
                if not url or not key:
                    return self._fail("Enter the Supabase project URL and public key.")
                backend = {"type": "supabase", "url": url, "key": key}

            name = self.name.text().strip()

            def create():   # network only — runs on the worker thread
                return self.core.prepare_remote_career(backend, name)

            def done(career_id, err):
                if err is not None:
                    if isinstance(err, SchemaMissing):
                        return self._fail("The database tables are missing. Run the setup SQL in Supabase first.")
                    return self._fail(str(err))
                try:
                    self.core.create_career(name, self.display.text().strip(), self.tag.text().strip(),
                                            self.picker.value(), backend, career_id=career_id)
                except Exception as exc:
                    return self._fail(str(exc))
                code = self.core.invite_code()
                self.code_edit.setText(code or "")
                self.code_edit.setVisible(bool(code))
                if not code:
                    self.done_note.setText("This career is stored on this PC only, so there's no invite code.")
                self._advance()
            self._run(create, done)

    def _next_join(self, i: int) -> None:
        if i == 0:
            code = self.code_in.text().strip()
            try:
                invite.decode(code)
            except invite.InvalidInvite as exc:
                return self._fail(str(exc))
            self.invite_info.setText("Checking…")

            def done(res, err):
                if err is not None:
                    self.invite_info.setText("")
                    if isinstance(err, SchemaMissing):
                        return self._fail("The owner's database isn't set up yet.")
                    return self._fail(str(err))
                if res.get("already_here"):
                    return self._fail("This career is already on this PC — switch to it in Settings › Careers.")
                self.preview = res
                st = res["state"]
                names = ", ".join(m.display_name for m in st.members.values()) or "nobody yet"
                self.join_summary.setText(f"Joining “{st.name or res['name']}” — season {st.season_label() if st.created else ''}, "
                                          f"drivers: {names}.")
                taken = {}
                for m in st.members.values():
                    c = st.contract_for(m.id)
                    if c:
                        taken[c.team_key] = f"{m.display_name}'s team"
                self.picker.set_notes(taken)
                self._advance()
            self._run(lambda: self.core.preview_invite(code), done)
        elif i == 1:
            if not self.display.text().strip():
                return self._fail("Enter your name.")
            existing = self.core.find_existing_member(self.preview["state"], self.display.text().strip(),
                                                      self.tag.text().strip())
            if existing is not None:
                ans = QMessageBox.question(
                    self, "Already in this career",
                    f"“{existing.display_name}” is already a driver in this career. Is that you?\n\n"
                    "Yes — continue as that driver (keeps results, contracts and owner rights).\n"
                    "No — join as a new driver.")
                if ans == QMessageBox.StandardButton.Yes:
                    return self._finish_join(existing)
            self._advance()
        elif i == 2:
            if not self.picker.value():
                return self._fail("Pick a team.")
            self._finish_join(None)

    def _finish_join(self, reclaim) -> None:
        try:
            self.core.join_career(self.preview, self.display.text().strip(), self.tag.text().strip(),
                                  self.picker.value() or "williams", reclaim=reclaim)
        except Exception as exc:
            return self._fail(str(exc))
        self.stack.setCurrentIndex(len(self.steps) - 1)
        self._update_nav()


class CaptureReviewDialog(QDialog):
    def __init__(self, core, cap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Check this result")
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 22)
        v.setSpacing(12)
        res = cap.result
        t = label(f"{res['session_name']} at {C.track_name(res['track_id'])}")
        t.setFont(font(15, QFont.Weight.Bold))
        v.addWidget(t)
        mine = next((e for e in res["entries"] if e.get("driver_key") == f"p:{core.me}"), None)
        if mine:
            v.addWidget(label(f"You finished P{mine['position']} in the {C.team_name(mine.get('team_key'))}.", "muted"))
        for w in cap.warnings:
            box = Card(padding=12)
            box.add(label(w, wrap=True))
            v.addWidget(box)
        v.addWidget(label(f"Count it towards round {cap.round} of season {core.state.season_label(cap.season)}?",
                          "muted", wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        no = button("Don't count it", "ghost")
        yes = button("Count it", "primary")
        no.clicked.connect(self.reject)
        yes.clicked.connect(self.accept)
        row.addWidget(no)
        row.addWidget(yes)
        v.addLayout(row)
