"""One-off PostgreSQL setup when psql is not on PATH."""
import asyncio
import sys

import asyncpg

APP_USER = "creativestudioai"
APP_PASSWORD = "Baguvix1@"
APP_DB = "creativestudioai"
ADMIN_USER = "postgres"
ADMIN_PASSWORD = "Baguvix1@"


async def main() -> None:
    admin = await asyncpg.connect(
        user=ADMIN_USER,
        password=ADMIN_PASSWORD,
        database="postgres",
        host="localhost",
        port=5432,
    )
    role_exists = await admin.fetchval(
        "SELECT 1 FROM pg_roles WHERE rolname = $1", APP_USER
    )
    if role_exists:
        await admin.execute(
            f"ALTER ROLE {APP_USER} WITH LOGIN PASSWORD '{APP_PASSWORD}'"
        )
        print(f"Updated password for role {APP_USER}")
    else:
        await admin.execute(
            f"CREATE ROLE {APP_USER} LOGIN PASSWORD '{APP_PASSWORD}'"
        )
        print(f"Created role {APP_USER}")

    db_exists = await admin.fetchval(
        "SELECT 1 FROM pg_database WHERE datname = $1", APP_DB
    )
    if not db_exists:
        await admin.execute(f"CREATE DATABASE {APP_DB} OWNER {APP_USER}")
        print(f"Created database {APP_DB}")
    else:
        print(f"Database {APP_DB} already exists")

    await admin.execute(f"GRANT ALL PRIVILEGES ON DATABASE {APP_DB} TO {APP_USER}")
    await admin.close()

    app = await asyncpg.connect(
        user=APP_USER,
        password=APP_PASSWORD,
        database=APP_DB,
        host="localhost",
        port=5432,
    )
    await app.close()
    print("Database setup complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        sys.exit(1)
