"""Run the PostgreSQL dual-track discount cleanup once (schedule this daily)."""

from __future__ import annotations

import os
import sys

import psycopg


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required.", file=sys.stderr)
        return 1

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM purge_expired_discounts()")
            daily_deleted, expired_deleted = cursor.fetchone()
        connection.commit()

    print(f"Deleted {daily_deleted} daily specials and {expired_deleted} expired offers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
