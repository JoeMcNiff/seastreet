"""Verify configured Clearview and Supabase credentials."""

from app.providers.clearview import ClearviewClient
from app.records.supabase import SupabaseClient


def main():
    try:
        health = ClearviewClient.from_environment().health()
        print(f"Clearview: online={health.online}, ready={health.ready}")
        SupabaseClient.from_environment().health()
        print("Supabase: connected")
    except ValueError as error:
        raise SystemExit(f"Configuration error: {error}")


if __name__ == "__main__":
    main()
