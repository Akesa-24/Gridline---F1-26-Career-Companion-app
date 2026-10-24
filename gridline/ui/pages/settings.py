"""Settings — profile, telemetry, sharing, career rules, calendar and seasons."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QSpinBox, QVBoxLayout,
)

from ...career.calendar import DEFAULT_POINTS
from ...career.engine import CareerState
from ...sync.supabase import schema_sql
from ...telemetry import constants as C
from ..theme import P
from ..widgets import icons
from ..widgets.common import Card, Chip, button, label
from .base import Page


def _form() -> QFormLayout:
    f = QFormLayout()
    f.setHorizontalSpacing(18)
    f.setVerticalSpacing(10)
    f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return f


class SettingsPage(Page):
    title = "Settings"
    new_career_requested = Signal()

    def __init__(self, core):
        super().__init__(core)
        cols = QHBoxLayout()
        cols.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(18)
        right = QVBoxLayout()
        right.setSpacing(18)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        self.body.addLayout(cols)
        self.body.addStretch(1)

        # ---- profile
        prof = Card("Your driver", padding=20)
        f = _form()
        self.name_edit = QLineEdit()
        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("Name shown in online lobbies")
        f.addRow(label("Display name", "muted"), self.name_edit)
        f.addRow(label("In-game name", "muted"), self.tag_edit)
        prof.add(f)
        prof.add(label("The in-game name lets the other player's PC recognise you in the lobby.", "faint", wrap=True))
        b = button("Save profile")
        b.clicked.connect(self._save_profile)
        prof.add_right(b)
        left.addWidget(prof)

        # ---- telemetry
        tel = Card("Telemetry", padding=20)
        f = _form()
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(core.udp_port)
        self.record = QCheckBox("Save raw packets for troubleshooting")
        self.record.setChecked(bool(core.store.get("record_packets", False)))
        f.addRow(label("UDP port", "muted"), self.port)
        f.addRow(label("", "muted"), self.record)
        tel.add(f)
        row = QHBoxLayout()
        self.tel_state = label("", "faint")
        row.addWidget(self.tel_state, 1)
        b = button("Apply")
        b.clicked.connect(self._apply_telemetry)
        row.addWidget(b)
        tel.add(row)
        left.addWidget(tel)
        core.telemetry_state.connect(lambda s, m: self.tel_state.setText(m))

        # ---- sharing
        self.share = Card("Sharing", padding=20)
        self.share_status = Chip("", "muted")
        self.share.header.addWidget(self.share_status)
        self.share_text = label("", "muted", wrap=True)
        self.share.add(self.share_text)
        self.invite = QLineEdit()
        self.invite.setReadOnly(True)
        self.invite.setProperty("mono", True)
        r = QHBoxLayout()
        r.addWidget(self.invite, 1)
        self.copy_invite = button("Copy", None, icons.icon("copy", P.text))
        self.copy_invite.clicked.connect(lambda: self._copy(self.invite.text(), "Invite code copied"))
        r.addWidget(self.copy_invite)
        self.share.add(r)
        r2 = QHBoxLayout()
        self.copy_sql = button("Copy database setup SQL", "ghost")
        self.copy_sql.clicked.connect(lambda: self._copy(schema_sql(), "Setup SQL copied — paste it into Supabase's SQL editor"))
        r2.addWidget(self.copy_sql)
        r2.addStretch(1)
        self.share.add(r2)
        left.addWidget(self.share)

        # ---- careers
        car = Card("Careers", padding=20)
        self.career_box = QComboBox()
        self.career_box.activated.connect(self._switch)
        car.add(self.career_box)
        r = QHBoxLayout()
        nb = button("New or join…", None, icons.icon("plus", P.text))
        nb.clicked.connect(self.new_career_requested)
        eb = button("Export log", "ghost")
        eb.clicked.connect(self._export)
        lb = button("Leave career", "danger")
        lb.clicked.connect(self._leave)
        r.addWidget(nb)
        r.addWidget(eb)
        r.addStretch(1)
        r.addWidget(lb)
        car.add(r)
        left.addWidget(car)
        left.addStretch(1)

        # ---- rules (owner)
        self.rules = Card("Rules", padding=20)
        self.owner_chip = Chip("OWNER ONLY", "muted")
        self.rules.header.addWidget(self.owner_chip)
        f = _form()
        self.points = QLineEdit()
        self.points.setPlaceholderText(",".join(map(str, DEFAULT_POINTS)))
        self.fl_point = QCheckBox("Extra point for fastest lap (top 10 only)")
        self.pole_point = QCheckBox("Extra point for pole position")
        self.practice = QCheckBox("Record practice sessions")
        f.addRow(label("Points for P1, P2…", "muted"), self.points)
        self.rules.add(f)
        for w in (self.fl_point, self.pole_point, self.practice):
            self.rules.add(w)
        self.save_rules = button("Save rules", "primary")
        self.save_rules.clicked.connect(self._save_rules)
        self.rules.add_right(self.save_rules)
        right.addWidget(self.rules)

        # ---- calendar (owner)
        self.cal = Card("Season calendar", padding=20)
        self.cal_list = QListWidget()
        self.cal_list.setMinimumHeight(300)
        self.cal.add(self.cal_list)
        r = QHBoxLayout()
        self.track_pick = QComboBox()
        for tid, t in sorted(C.TRACKS.items(), key=lambda kv: kv[1]["gp"]):
            self.track_pick.addItem(f"{t['gp']} — {t['name']}", tid)
        r.addWidget(self.track_pick, 1)
        self.add_round = button("Add", None, icons.icon("plus", P.text))
        self.add_round.clicked.connect(self._cal_add)
        r.addWidget(self.add_round)
        self.cal.add(r)
        r = QHBoxLayout()
        self.up_btn = button("", "ghost", icons.icon("up", P.text2))
        self.down_btn = button("", "ghost", icons.icon("down", P.text2))
        self.rm_btn = button("Remove", "ghost")
        self.up_btn.clicked.connect(lambda: self._cal_move(-1))
        self.down_btn.clicked.connect(lambda: self._cal_move(1))
        self.rm_btn.clicked.connect(self._cal_remove)
        for w in (self.up_btn, self.down_btn, self.rm_btn):
            r.addWidget(w)
        r.addStretch(1)
        self.save_cal = button("Save calendar", "primary")
        self.save_cal.clicked.connect(self._save_calendar)
        r.addWidget(self.save_cal)
        self.cal.add(r)
        self.cal.add(label("Rounds already raced are locked.", "faint"))
        right.addWidget(self.cal)

        # ---- season (owner)
        self.season_card = Card("Season", padding=20)
        self.season_text = label("", "muted", wrap=True)
        self.season_card.add(self.season_text)
        self.advance_btn = button("Start next season", "primary")
        self.advance_btn.clicked.connect(self._advance)
        self.season_card.add_right(self.advance_btn)
        right.addWidget(self.season_card)
        right.addStretch(1)

        core.sync_state.connect(self._sync_state)

    # ------------------------------------------------------------------ actions
    def _copy(self, text: str, msg: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.core.toast.emit("ok", msg)

    def _save_profile(self) -> None:
        n, t = self.name_edit.text().strip(), self.tag_edit.text().strip()
        if not n:
            return
        self.core.update_profile(n, t)
        self.core.toast.emit("ok", "Profile saved")

    def _apply_telemetry(self) -> None:
        self.core.store.set("record_packets", self.record.isChecked())
        self.core.set_udp_port(self.port.value())
        self.core.toast.emit("ok", f"Listening on UDP {self.port.value()}")

    def _switch(self, i: int) -> None:
        cid = self.career_box.itemData(i)
        if cid and (not self.core.career or cid != self.core.career["id"]):
            self.core.open_career(cid)

    def _export(self) -> None:
        if not self.core.career:
            return
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.core.state.name).strip() or "career"
        path, _ = QFileDialog.getSaveFileName(self, "Export career log", f"{safe}.json", "JSON (*.json)")
        if path:
            try:
                self.core.export_career(Path(path))
            except OSError as exc:
                self.core.toast.emit("error", f"Couldn't save the file: {exc.strerror or exc}")
                return
            self.core.toast.emit("ok", "Career log exported")

    def _leave(self) -> None:
        st = self.core.state
        extra = "" if self.core.is_local_only else "\n\nThe shared copy stays on the owner's database; you can rejoin with the invite code."
        if QMessageBox.question(self, "Leave career", f"Remove “{st.name}” from this PC?{extra}") == QMessageBox.StandardButton.Yes:
            self.core.leave_career()

    def _save_rules(self) -> None:
        txt = self.points.text().strip()
        try:
            pts = [float(x) if "." in x else int(x) for x in txt.replace(" ", "").split(",") if x] if txt else DEFAULT_POINTS
        except ValueError:
            self.core.toast.emit("error", "Points must be numbers separated by commas")
            return
        self.core.update_config({"points": pts, "fastest_lap_point": self.fl_point.isChecked(),
                                 "pole_point": self.pole_point.isChecked(), "track_practice": self.practice.isChecked()})
        self.core.toast.emit("ok", "Rules saved — standings recalculated")

    def _locked(self) -> int:
        return self.core.state.season.rounds_done() if self.core.state.created else 0

    def _cal_item(self, tid: int) -> QListWidgetItem:
        it = QListWidgetItem(f"{C.track_gp(tid)}  ·  {C.track_name(tid)}")
        it.setData(Qt.ItemDataRole.UserRole, tid)
        return it

    def _renumber(self) -> None:
        locked = self._locked()
        for i in range(self.cal_list.count()):
            it = self.cal_list.item(i)
            tid = it.data(Qt.ItemDataRole.UserRole)
            lock = "   (raced)" if i < locked else ""
            it.setText(f"{i + 1:>2}   {C.track_gp(tid)}  ·  {C.track_name(tid)}{lock}")
            if i < locked:
                it.setForeground(Qt.GlobalColor.gray)

    def _cal_add(self) -> None:
        self.cal_list.addItem(self._cal_item(self.track_pick.currentData()))
        self._renumber()

    def _cal_move(self, d: int) -> None:
        i = self.cal_list.currentRow()
        j = i + d
        if i < self._locked() or j < self._locked() or j < 0 or j >= self.cal_list.count():
            return
        it = self.cal_list.takeItem(i)
        self.cal_list.insertItem(j, it)
        self.cal_list.setCurrentRow(j)
        self._renumber()

    def _cal_remove(self) -> None:
        i = self.cal_list.currentRow()
        if i < self._locked():
            return
        self.cal_list.takeItem(i)
        self._renumber()

    def _save_calendar(self) -> None:
        cal = [self.cal_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.cal_list.count())]
        season = self.core.state.season
        used = max((r for (r, _t) in season.sessions), default=0)
        if len(cal) < max(1, self._locked(), used):
            self.core.toast.emit("error", f"Round {used} already has results — the calendar can't be shorter than that.")
            return
        self.core.update_calendar(cal)
        self.core.toast.emit("ok", f"Calendar saved — {len(cal)} rounds")

    def _advance(self) -> None:
        st = self.core.state
        season = st.season
        nxt = st.season_label(st.current_season + 1)
        if not season.complete:
            left = len(season.calendar) - season.rounds_done()
            q = f"{left} round(s) are still unraced. End {st.season_label()} now and start {nxt}?"
        else:
            q = f"Start the {nxt} season? Contracts signed for {nxt} take effect and the calendar carries over."
        if QMessageBox.question(self, "Start next season", q) == QMessageBox.StandardButton.Yes:
            self.core.advance_season()

    def _sync_state(self, state: str, detail: str) -> None:
        styles = {"online": ("SYNCED", "ok"), "offline": ("OFFLINE", "warn"), "error": ("ERROR", "bad"),
                  "schema": ("SETUP NEEDED", "bad"), "local": ("THIS PC ONLY", "muted")}
        t, s = styles.get(state, ("", "muted"))
        self.share_status.setText(t)
        self.share_status.set_style(s)

    # ------------------------------------------------------------------ refresh
    def _sync_field(self, key, value, apply) -> None:
        """Only overwrite an editable field when the saved value actually changed, so a
        background refresh never wipes what the user is in the middle of typing."""
        cache = self.__dict__.setdefault("_shown", {})
        career = self.core.career["id"] if self.core.career else None
        if cache.get((career, key), object()) != value:
            cache[(career, key)] = value
            apply(value)

    def refresh(self, st: CareerState) -> None:
        self.career_box.clear()
        for c in self.core.careers():
            self.career_box.addItem(c["name"], c["id"])
            if self.core.career and c["id"] == self.core.career["id"]:
                self.career_box.setCurrentIndex(self.career_box.count() - 1)
        if not st.created:
            return
        me = self.core.my_member()
        if me:
            self._sync_field("name", me.display_name, lambda v: self.name_edit.setText(v))
            self._sync_field("tag", me.gamertag, lambda v: self.tag_edit.setText(v))
        owner = self.core.is_owner
        self.header.set_subtitle(f"{st.name}  ·  " + ("You own this career" if owner else
                                 f"Owned by {st.members[st.owner_id].display_name if st.owner_id in st.members else 'another player'}"))

        local = self.core.is_local_only
        self.invite.setVisible(not local)
        self.copy_invite.setVisible(not local)
        self.copy_sql.setVisible(not local)
        if local:
            self.share_text.setText("This career is stored on this PC only. To race it with someone else, start a "
                                    "shared career backed by a free Supabase project.")
        else:
            url = self.core.career["backend"]["url"]
            self.share_text.setText(f"Synced through {url.replace('https://', '')}. Send this invite code to the "
                                    "other player — it contains everything their app needs to join.")
            self.invite.setText(self.core.invite_code() or "")
        self._sync_state(*self.core.sync_status)

        cfg = st.config
        self._sync_field("points", ",".join(str(x) for x in cfg.get("points", DEFAULT_POINTS)),
                         lambda v: self.points.setText(v))
        self._sync_field("fl", bool(cfg.get("fastest_lap_point")), lambda v: self.fl_point.setChecked(v))
        self._sync_field("pole", bool(cfg.get("pole_point")), lambda v: self.pole_point.setChecked(v))
        self._sync_field("practice", bool(cfg.get("track_practice", True)), lambda v: self.practice.setChecked(v))
        for w in (self.points, self.fl_point, self.pole_point, self.practice, self.save_rules,
                  self.cal_list, self.track_pick, self.add_round, self.up_btn, self.down_btn, self.rm_btn,
                  self.save_cal, self.advance_btn):
            w.setEnabled(owner)
        self.owner_chip.setVisible(not owner)

        def fill_calendar(cal):
            self.cal_list.clear()
            for tid in cal:
                self.cal_list.addItem(self._cal_item(tid))
        self._sync_field(("cal", st.current_season), tuple(st.season.calendar), fill_calendar)
        self._renumber()

        season = st.season
        done = season.rounds_done()
        self.season_text.setText(
            f"{st.season_label()}: {done} of {len(season.calendar)} rounds complete. "
            + ("Ready to move on." if season.complete else "Normally you'd start the next season after the final round.")
        )
        self.advance_btn.setText(f"Start {st.season_label(st.current_season + 1)} season")
