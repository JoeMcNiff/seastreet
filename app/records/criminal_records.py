"""Lookup synthetic criminal records associated with a matched identity."""

from dataclasses import dataclass

from app.records.supabase import SupabaseError


@dataclass(frozen=True)
class CriminalRecordsResult:
    status: str
    records: tuple = ()
    error: str = None


class CriminalRecordsService:
    def __init__(self, supabase=None):
        self.supabase = supabase

    def lookup(self, identity_id):
        if self.supabase is None:
            return CriminalRecordsResult(
                "records_unavailable", error="Supabase is not configured"
            )
        try:
            records = self.supabase.records_for_identity(identity_id)
            status = "records_found" if records else "no_records"
            return CriminalRecordsResult(status, records)
        except (SupabaseError, ValueError) as error:
            return CriminalRecordsResult("records_unavailable", error=str(error))
