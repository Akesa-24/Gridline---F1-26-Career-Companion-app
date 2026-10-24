"""Live — timing tower fed by the UDP stream, plus lobby team picks."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ...career.identity import names_match
from ...telemetry import constants as C
from ...telemetry.session_tracker import LiveSnapshot
from ..theme import P, font
from ..widgets.common import (
    Card, Chip, Dot, EmptyState, StatBlock, TeamBadge, clear_layout, fmt_gap, fmt_lap, label,
)
from ..widgets.table import DataTable
from .base import Page

SC_TEXT = {1: ("SAFETY CAR", "warn"), 2: ("VIRTUAL SC", "warn"), 3: ("FORMATION", "accent")}


class LivePage(Page):
    title = "Live timing"

    def __init__(self, core):
        super().__init__(core)
        self.dot = Dot(P.text3, 9)
        self.state_lbl = label("Telemetry off", "muted")
        self.header.actions.addWidget(self.dot)
        self.header.actions.addWidget(self.state_lbl)
        self.last_snap_at = 0.0

        self.stack = QStackedWidget()
        self.body.addWidget(self.stack, 1)

        # ---- waiting view
        waiting = QWidget()
        wv = QVBoxLayout(waiting)
        wv.setContentsMargins(0, 0, 0, 0)
        wv.setSpacing(18)
        self.empty = EmptyState(
            "Waiting for the game",
            "Start a session in F1 25 with the 2026 Season Pack. The timing tower appears here as soon as "
            "telemetry arrives, and results are recorded when each session ends.",
            "live",
        )
        wv.addWidget(self.empty)
        setup = Card("Game telemetry settings", padding=20)
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(8)
        self.port_value = label("20777")
        rows = [("UDP Telemetry", "On"), ("UDP Broadcast Mode", "Off"), ("UDP IP Address", "127.0.0.1"),
                ("UDP Port", None), ("UDP Send Rate", "20 Hz or higher"), ("UDP Format", "2026 or 2025"),
                ("Your Telemetry", "Public (so the other PC sees your laps)"),
                ("Show online names", "On (helps match players)")]
        for i, (k, v) in enumerate(rows):
            grid.addWidget(label(k, "muted"), i, 0)
            val = self.port_value if v is None else label(v)
            val.setFont(font(10, QFont.Weight.DemiBold))
            grid.addWidget(val, i, 1)
        grid.setColumnStretch(2, 1)
        setup.add(label("Settings › Telemetry Settings in the game:", "faint"))
        setup.add(grid)
        wv.addWidget(setup)
        self.lobby_card = Card("Lobby", padding=18)
        self.lobby_box = QVBoxLayout()
        self.lobby_box.setSpacing(6)
        self.lobby_card.add(self.lobby_box)
        self.lobby_card.hide()
        wv.addWidget(self.lobby_card)
        wv.addStretch(1)
        self.stack.addWidget(waiting)

        # ---- live view
        live = QWidget()
        lv = QVBoxLayout(live)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(14)
        strip = Card(padding=18)
        sh = QHBoxLayout()
        sh.setSpacing(34)
        self.s_session = StatBlock("Session")
        self.s_track = StatBlock("Circuit")
        self.s_lap = StatBlock("Lap")
        self.s_fastest = StatBlock("Fastest lap")
        for w in (self.s_session, self.s_track, self.s_lap, self.s_fastest):
            sh.addWidget(w)
        sh.addStretch(1)
        self.sc_chip = Chip("", "warn")
        sh.addWidget(self.sc_chip, 0, Qt.AlignmentFlag.AlignVCenter)
        self.round_chip = Chip("", "accent")
        sh.addWidget(self.round_chip, 0, Qt.AlignmentFlag.AlignVCenter)
        strip.add(sh)
        lv.addWidget(strip)

        tower = Card(padding=10)
        self.table = DataTable([
            ("POS", 50), ("DRIVER", None), ("TEAM", 64), ("GAP", 96), ("INT", 90),
            ("LAST", 96), ("BEST", 96), ("TYRE", 80), ("PIT", 46),
        ], row_height=34)
        tower.add(self.table, 1)
        lv.addWidget(tower, 1)
        self.stack.addWidget(live)

        self.stale = QTimer(self)
        self.stale.timeout.connect(self._check_stale)
        self.stale.start(1000)

        core.live.connect(self.on_snapshot)
        core.lobby.connect(self.on_lobby)
        core.telemetry_state.connect(self.on_state)
        self.on_state(*core.telemetry)

    # ------------------------------------------------------------------
    def on_state(self, state: str, msg: str) -> None:
        colours = {"receiving": (P.ok, True), "listening": (P.accent, False), "error": (P.bad, False),
                   "idle": (P.text3, False)}
        c, pulse = colours.get(state, (P.text3, False))
        self.dot.set_colour(c, pulse)
        self.state_lbl.setText(msg)
        self.port_value.setText(str(self.core.udp_port))

    def _check_stale(self) -> None:
        if self.stack.currentIndex() == 1 and time.time() - self.last_snap_at > 6:
            self.stack.setCurrentIndex(0)

    def on_lobby(self, lobby: list) -> None:
        clear_layout(self.lobby_box)
        humans = [p for p in lobby if not p["ai"]]
        self.lobby_card.setVisible(bool(humans))
        st = self.core.state
        for p in humans:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(TeamBadge(p["team_key"]))
            row.addWidget(label(p["name"] or "Player"), 1)
            # warn if a known member picked a team that isn't theirs
            for m in st.members.values():
                if names_match(p["name"], m.gamertag) or names_match(p["name"], m.display_name):
                    c = st.contract_for(m.id)
                    if c and p["team_key"] and c.team_key != p["team_key"]:
                        row.addWidget(Chip(f"Contracted to {C.team_name(c.team_key)}", "warn"))
                    elif c:
                        row.addWidget(Chip("Correct seat", "ok"))
            ready = {0: ("Not ready", "muted"), 1: ("Ready", "ok"), 2: ("Spectating", "muted")}.get(p["ready"], ("", "muted"))
            row.addWidget(Chip(*ready))
            self.lobby_box.addLayout(row)

    def on_snapshot(self, snap: LiveSnapshot) -> None:
        self.last_snap_at = time.time()
        if self.stack.currentIndex() != 1:
            self.stack.setCurrentIndex(1)
        is_race = snap.session_type in C.RACE_TYPES
        self.s_session.set(C.SESSION_TYPES.get(snap.session_type, "Session"),
                           "Online" if snap.network_game else "Offline")
        self.s_track.set(C.track_name(snap.track_id), C.track_gp(snap.track_id))
        if is_race:
            self.s_lap.set(f"{min(snap.lap, snap.total_laps)} / {snap.total_laps}")
        else:
            m, s = divmod(snap.time_left, 60)
            self.s_lap.cap.setText("TIME LEFT")
            self.s_lap.set(f"{m}:{s:02d}")
        if is_race:
            self.s_lap.cap.setText("LAP")
        fl_name = next((r.name for r in snap.rows if r.idx == snap.fastest_lap_idx), "")
        self.s_fastest.set(fmt_lap(snap.fastest_lap_ms), fl_name, P.purple if snap.fastest_lap_ms else None)
        sc = SC_TEXT.get(snap.safety_car)
        self.sc_chip.setVisible(bool(sc))
        if sc:
            self.sc_chip.setText(sc[0])
            self.sc_chip.set_style(sc[1])
        st = self.core.state
        if st.created and st.season.next_round():
            r = st.season.next_round()
            self.round_chip.setText(f"Recording to round {r}")
            self.round_chip.show()
        else:
            self.round_chip.hide()

        rows, hl = [], []
        leader_best = snap.fastest_lap_ms
        for i, r in enumerate(snap.rows):
            status_txt = {4: "DNF", 5: "DSQ", 6: "NC", 7: "OUT"}.get(r.status)
            if is_race:
                gap = "Leader" if i == 0 else fmt_gap(r.gap_leader_ms)
                interval = "" if i == 0 else fmt_gap(r.interval_ms)
            else:
                gap = "" if (i == 0 or not r.best_lap_ms or not leader_best) else fmt_gap(r.best_lap_ms - leader_best)
                interval = ""
            if r.pit_status:
                interval = "IN PIT"
            if status_txt:
                gap, interval = status_txt, ""
            best_style = {"mono": True, "fg": P.purple if r.idx == snap.fastest_lap_idx else P.text}
            name_style = {"team": r.team_key, "bold": r.is_human}
            if r.is_local:
                name_style["badge"] = "YOU"
            elif r.is_human:
                name_style["badge"] = "HUMAN"
                name_style["badge_colours"] = (P.text2, P.card3)
            rows.append([
                ("", {"pos": r.position, "medal": False}),
                (r.name, name_style),
                (C.TEAMS_2026.get(r.team_key or "", {}).get("short", ""), {"fg": P.text2, "size": 9}),
                (gap, {"mono": True, "fg": P.text if i else P.text2}),
                (interval, {"mono": True, "fg": P.warn if interval == "IN PIT" else P.text2}),
                (fmt_lap(r.last_lap_ms), {"mono": True, "fg": P.text2}),
                (fmt_lap(r.best_lap_ms), best_style),
                (str(r.tyre_age) if r.tyre else "", {"tyre": r.tyre}),
                (str(r.pit_stops), {"mono": True, "align": "c", "fg": P.text2}),
            ])
            hl.append(P.accent_dim if r.is_local else (P.card2 if r.is_human else None))
        self.table.set_rows(rows, hl)

    def refresh(self, state) -> None:
        self.port_value.setText(str(self.core.udp_port))
