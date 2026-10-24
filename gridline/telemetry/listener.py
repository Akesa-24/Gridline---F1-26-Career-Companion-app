"""UDP listener thread. Owns the socket and the SessionTracker."""
from __future__ import annotations

import socket
import traceback
import struct
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .packets import SPECS, UnsupportedFormat, decode
from .session_tracker import SessionTracker

SNAPSHOT_INTERVAL = 0.25


class TelemetryListener(QThread):
    """Binds to the game's UDP port and emits Qt signals.

    snapshot  -> LiveSnapshot (throttled to 4 Hz)
    result    -> dict raw session result
    lobby     -> list[dict] lobby team picks
    state     -> str  one of: idle, listening, receiving, error
    message   -> str  human readable detail for the status bar
    """

    snapshot = Signal(object)
    result = Signal(object)
    lobby = Signal(object)
    session_started = Signal(object)
    state = Signal(str)
    message = Signal(str)

    def __init__(self, host: str = "0.0.0.0", port: int = 20777, record_to: Path | None = None):
        super().__init__()
        self.host = host
        self.port = port
        self.record_to = record_to
        self._running = True
        self.tracker = SessionTracker()
        self._size_warned: set[int] = set()

    def _check_size(self, data: bytes) -> None:
        """Report once per packet type if the game's packet size differs from the spec."""
        if len(data) < 29:
            return
        fmt, pid = struct.unpack_from("<H", data, 0)[0], data[6]
        spec = SPECS.get(fmt)
        expected = spec.sizes.get(pid) if spec else None
        if expected and len(data) != expected and pid not in self._size_warned:
            self._size_warned.add(pid)
            self.message.emit(f"Packet {pid} is {len(data)} bytes, spec says {expected} — please report this")

    def request_stop(self) -> None:
        self._running = False

    def stop(self) -> None:
        self.request_stop()
        self.wait(2000)

    def run(self) -> None:  # noqa: C901 - one loop, kept readable
        if not self._running:      # stop() was called before the thread got going
            return
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # No SO_REUSEADDR: on Windows it lets two programs share the port and only one
            # gets the data. Ask for exclusive use so a conflict shows up as an error instead.
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind((self.host, self.port))
            sock.settimeout(0.5)
        except OSError as exc:
            self.state.emit("error")
            self.message.emit(f"UDP port {self.port} is in use by another program "
                              f"(another telemetry app or a second Gridline?): {exc.strerror or exc}")
            return

        rec = open(self.record_to, "ab") if self.record_to else None
        self.state.emit("listening")
        self.message.emit(f"Listening on UDP {self.port}")
        receiving = False
        last_snap = 0.0
        warned_format = None
        try:
            while self._running:
                try:
                    data, _ = sock.recvfrom(4096)
                except socket.timeout:
                    if receiving and time.time() - self.tracker.last_packet_at > 3:
                        receiving = False
                        self.state.emit("listening")
                        self.message.emit("Game stream paused")
                    continue
                except OSError:
                    continue

                if rec:
                    rec.write(struct.pack("<dH", time.time(), len(data)) + data)
                self.tracker.last_packet_at = time.time()
                if not receiving:
                    receiving = True
                    self.state.emit("receiving")
                    self.message.emit("Receiving telemetry")
                self._check_size(data)
                try:
                    pkt = decode(data)
                except UnsupportedFormat as exc:
                    fmt = exc.args[0]
                    if warned_format != fmt:
                        warned_format = fmt
                        self.state.emit("error")
                        self.message.emit(
                            f"Game is sending UDP format {fmt}. Set Telemetry > UDP Format to 2026 or 2025."
                        )
                    continue
                except Exception:  # malformed datagram, keep going
                    continue
                if pkt is None:
                    continue

                try:
                    for kind, payload in self.tracker.feed(pkt):
                        if kind == "result":
                            self.result.emit(payload)
                        elif kind == "lobby":
                            self.lobby.emit(payload)
                        elif kind == "session_started":
                            self.session_started.emit(payload)

                    now = time.time()
                    if now - last_snap >= SNAPSHOT_INTERVAL:
                        last_snap = now
                        snap = self.tracker.snapshot()
                        if snap is not None:
                            self.snapshot.emit(snap)
                except Exception:  # never let one bad packet kill the listener
                    traceback.print_exc()
        finally:
            sock.close()
            if rec:
                rec.close()
            self.state.emit("idle")
