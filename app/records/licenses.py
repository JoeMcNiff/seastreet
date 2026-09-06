"""Parse PDF417 driver-license data and compare it with Supabase."""

import re
from dataclasses import dataclass
from datetime import date, datetime

from app.records.supabase import SupabaseError


FIELDS = {
    "DAQ": "number",
    "DBD": "issue_date",
    "DBA": "expiration_date",
    "DBB": "date_of_birth",
    "DBC": "sex",
    "DAC": "first_name",
    "DCT": "first_name",
    "DCS": "last_name",
    "DAJ": "state",
}


@dataclass(frozen=True)
class LicenseData:
    number: str
    state: str = None
    first_name: str = None
    last_name: str = None
    date_of_birth: str = None
    issue_date: str = None
    expiration_date: str = None
    sex: str = None


@dataclass(frozen=True)
class LicenseResult:
    status: str
    scan: LicenseData = None
    record: dict = None
    mismatches: tuple = ()
    error: str = None

    @property
    def message(self):
        return {
            "license_found": "DMV RECORD FOUND",
            "license_expired": "LICENSE EXPIRED",
            "license_mismatch": "DMV DATA MISMATCH",
            "license_not_found": "NO DMV RECORD FOUND",
            "invalid_barcode": "UNREADABLE DRIVER LICENSE",
            "lookup_unavailable": "DMV LOOKUP UNAVAILABLE",
        }[self.status]

    def payload(self):
        record = self.record or {}
        scan = self.scan

        def value(name):
            return record.get(name) or (getattr(scan, name) if scan else None)

        name = " ".join(filter(None, (value("first_name"), value("last_name"))))
        return {
            "status": self.status,
            "message": self.message,
            "name": name or None,
            "number": value("number"),
            "state": value("state"),
            "expiration_date": value("expiration_date"),
            "mismatches": self.mismatches,
        }


class LicenseService:
    def __init__(self, supabase=None):
        self.supabase = supabase

    def lookup(self, barcode):
        scan = parse_aamva(barcode)
        if scan is None:
            return LicenseResult("invalid_barcode")
        if self.supabase is None:
            return LicenseResult(
                "lookup_unavailable", scan, error="Supabase is not configured"
            )
        try:
            records = self.supabase.licenses_by_number(scan.number, scan.state)
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


def parse_aamva(text):
    """Extract the fields used by the demo from an AAMVA PDF417 payload."""
    if not isinstance(text, str) or "ANSI " not in text.upper():
        return None
    values = {}
    for code, name in FIELDS.items():
        if name in values:
            continue
        match = re.search(code + r"([^\r\n\x1d\x1e]+)", text, re.IGNORECASE)
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
    return LicenseData(**values)


def _date(value):
    for pattern in ("%m%d%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    return value


def _expired(value):
    try:
        return date.fromisoformat(str(value)) < date.today()
    except (TypeError, ValueError):
        return False


def _mismatches(scan, record):
    return tuple(
        name
        for name in LicenseData.__dataclass_fields__
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
    if name in ("number", "state", "first_name", "last_name"):
        return re.sub(r"[^A-Z0-9]", "", value)
    return value
