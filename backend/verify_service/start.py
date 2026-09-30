"""Wait until the restricted database account exists, then start the API."""

import os
import sys
import time


def database_ready() -> bool:
    import psycopg

    with psycopg.connect(
        host=os.environ["VERIFY_DB_HOST"],
        port=int(os.environ.get("VERIFY_DB_PORT", "5432")),
        dbname=os.environ["VERIFY_DB_NAME"],
        user=os.environ["VERIFY_DB_USER"],
        password=os.environ["VERIFY_DB_PASSWORD"],
        connect_timeout=5,
    ) as connection:
        connection.execute("SELECT 1 FROM resource_instances LIMIT 1")
    return True


def main() -> None:
    timeout = int(os.environ.get("VERIFY_START_TIMEOUT_SECONDS", "180"))
    deadline = time.monotonic() + timeout
    while True:
        try:
            database_ready()
            break
        except Exception as error:
            if time.monotonic() >= deadline:
                raise SystemExit(f"Verification service cannot connect to PostgreSQL: {error}") from error
            print(f"Waiting for verification database account: {error}", file=sys.stderr)
            time.sleep(2)
    os.execvp("uvicorn", ["uvicorn", "verify_service.api:app", "--host", "0.0.0.0", "--port", "8000"])


if __name__ == "__main__":
    main()
