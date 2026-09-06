"""Asynchronous AAMVA driver-license barcode scanning and lookup."""

import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime

import cv2
import zxingcpp

from app.records.supabase import SupabaseError


FIELDS = {
    "DAQ": "number",
    "DBD": "issue_date",
    "DBA": "expiration_date",
    "DBB": "date_of_birth",
    "DBC": "sex",
    "DAC": "first_name",
    "DCS": "last_name",
    "DAJ": "state",
}
CLAHE = cv2.createCLAHE(clipLimit=2, tileGridSize=(8, 8))


@dataclass(frozen=True)
class LicenseData:
    number: str
    issue_date: str = None
    expiration_date: str = None
    date_of_birth: str = None
    sex: str = None
    first_name: str = None
    last_name: str = None
    state: str = None
    rect: tuple = None

    @property
    def key(self):
        return self.state, self.number


@dataclass(frozen=True)
class LicenseResult:
    status: str
    scan: LicenseData
    record: dict = None
    mismatches: tuple = ()
    error: str = None


def parse_aamva(text, rect=None):
    """Extract the DMV fields used by this demo from an AAMVA payload."""
    if "ANSI " not in text:
        return None
    values = {}
    for code, name in FIELDS.items():
        match = re.search(code + r"([^\r\n\x1d\x1e]+)", text)
        if match:
            values[name] = match.group(1).strip().upper()
    if not values.get("number"):
        return None
    for name in ("issue_date", "expiration_date", "date_of_birth"):
        if name in values:
            values[name] = _date(values[name])
    values["sex"] = {"1": "M", "2": "F", "9": "X"}.get(
        values.get("sex"), values.get("sex")
    )
    return LicenseData(**values, rect=rect)


def scan_license(frame):
    scan = _decode(frame)
    if scan:
        return scan

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    enhanced = CLAHE.apply(gray)
    enhanced = cv2.resize(enhanced, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    return _decode(enhanced, scale=1.5)


def _decode(frame, scale=1):
    for barcode in zxingcpp.read_barcodes(
        frame,
        formats=zxingcpp.BarcodeFormat.PDF417,
        try_rotate=True,
        try_downscale=True,
        try_invert=True,
        text_mode=zxingcpp.TextMode.Plain,
    ):
        scan = parse_aamva(barcode.text, _rect(barcode.position, scale))
        if scan:
            return scan
    return None


def lookup_license(supabase, scan):
    if supabase is None:
        return LicenseResult("lookup_unavailable", scan, error="Supabase is not configured")
    try:
        records = supabase.licenses_by_number(scan.number)
        if not records:
            return LicenseResult("license_not_found", scan)
        compared = [(_mismatches(scan, record), record) for record in records]
        mismatches, record = min(compared, key=lambda item: len(item[0]))
        if mismatches:
            status = "license_mismatch"
        elif _expired(record.get("expiration_date")):
            status = "license_expired"
        else:
            status = "license_found"
        return LicenseResult(status, scan, record, mismatches)
    except (SupabaseError, ValueError) as error:
        return LicenseResult("lookup_unavailable", scan, error=str(error))


class LicenseScanner:
    """Scan only the newest frame on a throttled background thread."""

    def __init__(self, supabase, interval=0.2, scanner=scan_license):
        self._supabase = supabase
        self._interval = interval
        self._scanner = scanner
        self._frames = deque(maxlen=1)
        self._results = deque()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._next_scan = 0
        self._last_key = None
        self._rect = None
        self._seen_at = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, frame):
        now = time.monotonic()
        if now < self._next_scan:
            return
        self._next_scan = now + self._interval
        self._frames.append(frame)
        self._wake.set()

    def poll(self):
        try:
            return self._results.popleft()
        except IndexError:
            return None

    def visible_rect(self):
        return self._rect if time.monotonic() - self._seen_at < 1 else None

    def close(self):
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=1)

    def _run(self):
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                frame = self._frames.pop()
            except IndexError:
                continue
            scan = self._scanner(frame)
            if not scan:
                if time.monotonic() - self._seen_at > 2:
                    self._last_key = None
                continue
            self._rect, self._seen_at = scan.rect, time.monotonic()
            if scan.key == self._last_key:
                continue
            self._last_key = scan.key
            self._results.append(LicenseResult("searching", scan))
            self._results.append(lookup_license(self._supabase, scan))


def _date(value):
    for pattern in ("%m%d%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    return value


def _rect(position, scale=1):
    points = (
        position.top_left,
        position.top_right,
        position.bottom_right,
        position.bottom_left,
    )
    left, right = min(point.x for point in points), max(point.x for point in points)
    top, bottom = min(point.y for point in points), max(point.y for point in points)
    return tuple(round(value / scale) for value in (left, top, right - left, bottom - top))


def _expired(value):
    try:
        return date.fromisoformat(str(value)) < date.today()
    except (TypeError, ValueError):
        return False


def _mismatches(scan, record):
    names = tuple(FIELDS.values())
    return tuple(
        name
        for name in names
        if getattr(scan, name) is not None
        and record.get(name) is not None
        and _normalized(name, getattr(scan, name)) != _normalized(name, record[name])
    )


def _normalized(name, value):
    value = str(value).strip().upper()
    if name == "sex":
        return {"1": "M", "MALE": "M", "2": "F", "FEMALE": "F", "9": "X"}.get(
            value, value
        )
    return value
