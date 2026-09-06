"""Replace existing criminal-record details with consistent synthetic data."""

import argparse

from app.records.supabase import SupabaseClient, SupabaseError


OFFENSES = (
    {
        "primary_offense": "Aggravated Assault",
        "record_status": "convicted",
        "wanted_level": 0,
        "arrest_count": 2,
        "conviction_count": 1,
        "active_warrant": False,
        "last_arrest_date": "2024-11-18",
    },
    {
        "primary_offense": "Armed Robbery",
        "record_status": "active warrant",
        "wanted_level": 4,
        "arrest_count": 3,
        "conviction_count": 1,
        "active_warrant": True,
        "last_arrest_date": "2025-09-12",
        "warrant_issue_date": "2026-02-03",
    },
    {
        "primary_offense": "Assault with a Deadly Weapon",
        "record_status": "probation",
        "wanted_level": 0,
        "arrest_count": 2,
        "conviction_count": 2,
        "active_warrant": False,
        "last_arrest_date": "2023-06-21",
    },
    {
        "primary_offense": "Kidnapping",
        "record_status": "active warrant",
        "wanted_level": 5,
        "arrest_count": 1,
        "conviction_count": 0,
        "active_warrant": True,
        "last_arrest_date": "2025-12-08",
        "warrant_issue_date": "2026-01-15",
    },
    {
        "primary_offense": "Attempted Murder",
        "record_status": "pending trial",
        "wanted_level": 0,
        "arrest_count": 2,
        "conviction_count": 0,
        "active_warrant": False,
        "last_arrest_date": "2026-03-04",
    },
    {
        "primary_offense": "Domestic Violence Assault",
        "record_status": "active warrant",
        "wanted_level": 3,
        "arrest_count": 4,
        "conviction_count": 2,
        "active_warrant": True,
        "last_arrest_date": "2025-10-27",
        "warrant_issue_date": "2026-04-19",
    },
    {
        "primary_offense": "Voluntary Manslaughter",
        "record_status": "convicted",
        "wanted_level": 0,
        "arrest_count": 1,
        "conviction_count": 1,
        "active_warrant": False,
        "last_arrest_date": "2022-07-09",
    },
    {
        "primary_offense": "Second-Degree Murder",
        "record_status": "incarcerated",
        "wanted_level": 0,
        "arrest_count": 2,
        "conviction_count": 1,
        "active_warrant": False,
        "last_arrest_date": "2021-02-14",
    },
)


def details_for(record_id):
    values = dict(OFFENSES[(int(record_id) - 1) % len(OFFENSES)])
    if values["active_warrant"]:
        values["warrant_number"] = f"MOCK-WRT-{int(record_id):06d}"
    else:
        values["warrant_number"] = None
        values["warrant_issue_date"] = None
    return values


def update_all(apply=False, client=None):
    client = client or SupabaseClient.from_environment()
    records = client.list_criminal_records()
    action = "UPDATE" if apply else "WOULD UPDATE"

    for record in records:
        record_id = record["id"]
        values = details_for(record_id)
        print(
            f"{action} {record_id}: {values['primary_offense']} "
            f"[{values['record_status']}]"
        )
        if apply:
            client.update_criminal_record(record_id, values)

    print(f"{'Updated' if apply else 'Dry run:'} {len(records)} criminal records")
    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write the displayed changes to Supabase"
    )
    args = parser.parse_args()
    try:
        update_all(args.apply)
    except (SupabaseError, ValueError) as error:
        raise SystemExit(f"Update failed: {error}")


if __name__ == "__main__":
    main()
