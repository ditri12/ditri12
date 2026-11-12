"""Balance communication.

RADWAG balances (and most others) expose a simple line protocol over TCP.
The commands used here:

    SI   send the current reading immediately (stable or not)
    Z    zero the balance
    T    tare the balance

A typical reply to SI looks like one of::

    SI   -  0.000070 g
    SI ?    0.012345 g        ("?" = unstable)
    SI XS   0.012345 g        (some firmware: XS stable / XI unstable)

The sign may be sent as a separate token, which is why the parser works on
tokens rather than a fixed-width field.

Two implementations share the same interface:

* ``RadwagScale``    real balance over TCP
* ``SimulatedScale`` software balance for training / demo mode

Both run a background thread that polls the balance and publishes
``Reading`` objects to a ``queue.Queue``; the GUI drains that queue from the
Tk event loop, so no Tk call ever happens off the main thread.
"""
from __future__ import annotations

import logging
import queue
import random
import re
import socket
import threading
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

DEFAULT_IP = "10.0.0.112"
DEFAULT_PORT = 4001
DEFAULT_POLL_INTERVAL = 0.25   # seconds between SI requests
LINE_TERMINATOR = "\r\n"

_NUMBER = re.compile(r"^[+-]?\d*\.?\d+$")
_UNIT = re.compile(r"^(mg|g|kg|ct|oz|lb)$", re.IGNORECASE)
_UNSTABLE_TOKENS = {"?", "XI", "U"}
_STABLE_TOKENS = {"XS", "S"}
_COMMAND_ECHO = {"SI", "S", "SU", "SUI", "SIU", "SRU", "SR", "Z", "T"}

_TO_GRAMS = {"g": 1.0, "mg": 1e-3, "kg": 1e3}


@dataclass(frozen=True)
class Reading:
    value_g: float
    stable: bool
    unit: str
    raw: str
    timestamp: float = field(default_factory=time.time)

    def formatted(self, decimals: int = 6) -> str:
        return f"{self.value_g:+.{decimals}f}"


def parse_reading(line: str) -> Reading | None:
    """Parse one protocol line. Returns None for acknowledgements / noise."""
    raw = line.strip()
    if not raw:
        return None
    tokens = raw.split()
    stable = True
    sign = 1.0
    value: float | None = None
    unit = "g"
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        up = tok.upper()
        if value is None and up in _COMMAND_ECHO:
            pass
        elif up in _UNSTABLE_TOKENS:
            stable = False
        elif up in _STABLE_TOKENS:
            stable = True
        elif value is None and tok in ("-", "+"):
            sign = -1.0 if tok == "-" else 1.0
        elif value is None and _NUMBER.match(tok):
            value = float(tok) * sign
        elif value is not None and _UNIT.match(tok):
            unit = tok.lower()
        elif up.endswith("?") and up[:-1] in _COMMAND_ECHO:   # e.g. "SI?"
            stable = False
        i += 1
    if value is None:
        return None
    value_g = value * _TO_GRAMS.get(unit, 1.0)
    return Reading(value_g=value_g, stable=stable, unit=unit, raw=raw)


class ScaleError(RuntimeError):
    pass


class BaseScale:
    """Common polling loop. Subclasses implement _send() and _readline()."""

    name = "scale"

    def __init__(self, poll_interval: float = DEFAULT_POLL_INTERVAL) -> None:
        self.poll_interval = poll_interval
        self.readings: queue.Queue[Reading] = queue.Queue()
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()  # (kind, message)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.connected = False

    # --- public API ------------------------------------------------------
    def connect(self) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        self.stop_listening()
        self.connected = False

    def start_listening(self) -> None:
        if not self.connected:
            raise ScaleError("Not connected.")
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name=f"{self.name}-poll",
                                        daemon=True)
        self._thread.start()

    def stop_listening(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive() and \
                threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None

    @property
    def listening(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def zero(self) -> None:
        self._command("Z")

    def tare(self) -> None:
        self._command("T")

    def read_once(self, timeout: float = 2.0) -> Reading | None:
        """Request a single reading synchronously."""
        with self._lock:
            self._send("SI")
            deadline = time.time() + timeout
            while time.time() < deadline:
                line = self._readline()
                if line is None:
                    continue
                r = parse_reading(line)
                if r:
                    return r
        return None

    # --- internals -------------------------------------------------------
    def _command(self, cmd: str) -> None:
        if not self.connected:
            raise ScaleError("Not connected.")
        with self._lock:
            self._send(cmd)
            # consume the acknowledgement (e.g. "Z_A", "T_A") without blocking long
            self._readline()
        self.events.put(("info", f"{cmd} sent"))

    def _send(self, cmd: str) -> None:
        raise NotImplementedError

    def _readline(self) -> str | None:
        raise NotImplementedError

    def _loop(self) -> None:
        consecutive_errors = 0
        while not self._stop.is_set():
            try:
                reading = self.read_once(timeout=max(1.0, self.poll_interval * 4))
                if reading:
                    self.readings.put(reading)
                    consecutive_errors = 0
            except (OSError, ScaleError) as exc:
                consecutive_errors += 1
                log.warning("scale read error (%d): %s", consecutive_errors, exc)
                if consecutive_errors >= 5:
                    self.events.put(("error", f"Lost connection to the balance: {exc}"))
                    self.connected = False
                    break
            self._stop.wait(self.poll_interval)


class RadwagScale(BaseScale):
    """RADWAG balance over a TCP socket (Ethernet or serial-to-IP adapter)."""

    name = "radwag"

    def __init__(self, ip: str = DEFAULT_IP, port: int = DEFAULT_PORT,
                 poll_interval: float = DEFAULT_POLL_INTERVAL, timeout: float = 1.0) -> None:
        super().__init__(poll_interval)
        self.ip = ip
        self.port = int(port)
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buffer = b""

    def connect(self) -> None:
        self.disconnect()
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=3.0)
        except OSError as exc:
            raise ScaleError(f"Cannot connect to {self.ip}:{self.port} - {exc}") from exc
        sock.settimeout(self.timeout)
        self._sock = sock
        self._buffer = b""
        self.connected = True
        log.info("connected to balance at %s:%s", self.ip, self.port)

    def disconnect(self) -> None:
        super().disconnect()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None

    def _send(self, cmd: str) -> None:
        if not self._sock:
            raise ScaleError("Not connected.")
        self._sock.sendall((cmd + LINE_TERMINATOR).encode("ascii"))

    def _readline(self) -> str | None:
        if not self._sock:
            raise ScaleError("Not connected.")
        while b"\n" not in self._buffer:
            try:
                chunk = self._sock.recv(256)
            except socket.timeout:
                return None
            if not chunk:
                raise ScaleError("Connection closed by the balance.")
            self._buffer += chunk
        line, _, self._buffer = self._buffer.partition(b"\n")
        return line.decode("ascii", errors="replace")


class SimulatedScale(BaseScale):
    """Software balance for demo / training without hardware.

    ``target_g`` is the mass currently "on the pan"; the GUI can set it
    (e.g. from the selected test volume) and ``add_drop`` simulates a
    dispensed drop with realistic noise.
    """

    name = "simulator"

    def __init__(self, poll_interval: float = DEFAULT_POLL_INTERVAL, seed: int | None = None) -> None:
        super().__init__(poll_interval)
        self._rng = random.Random(seed)
        self.target_g = 0.0
        self._offset_g = 0.0
        self._settle_until = 0.0
        self._pending: list[str] = []

    def connect(self) -> None:
        self.connected = True

    def add_drop(self, mass_g: float, noise_pct: float = 0.12) -> None:
        noise = self._rng.gauss(0.0, mass_g * noise_pct / 100.0)
        self.target_g += mass_g + noise
        self._settle_until = time.time() + 0.8

    def _send(self, cmd: str) -> None:
        cmd = cmd.strip().upper()
        if cmd in ("Z", "T"):
            self._offset_g = self.target_g
            self._pending.append(f"{cmd}_A")
        elif cmd == "SI":
            unstable = time.time() < self._settle_until
            jitter = self._rng.gauss(0.0, 2e-6) if not unstable else self._rng.gauss(0.0, 2e-4)
            value = self.target_g - self._offset_g + jitter
            sign = "-" if value < 0 else " "
            marker = "?" if unstable else " "
            self._pending.append(f"SI {marker} {sign} {abs(value):.6f} g")

    def _readline(self) -> str | None:
        return self._pending.pop(0) if self._pending else None
