"""migrations/ 폴더의 SQL 파일을 이름 순서대로 한 번씩 적용한다.

실행: poetry run python -m rulecite.db.migrate
"""

from pathlib import Path

import psycopg

from rulecite.config import Settings
from rulecite.db import connect

# server/migrations (server/src/rulecite/db/migrate.py 기준 세 단계 위)
MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def apply_migrations(
    conn: psycopg.Connection, migrations_dir: Path = MIGRATIONS_DIR
) -> list[str]:
    """아직 적용하지 않은 마이그레이션을 적용하고, 새로 적용한 파일 이름을 돌려준다.

    autocommit 연결을 받아 파일마다 별도 트랜잭션으로 실행한다.
    한 파일이 실패하면 그 파일만 되돌리고 예외를 그대로 올린다.
    """
    with conn.transaction():
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version text PRIMARY KEY,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

    newly_applied = []
    for path in sorted(migrations_dir.glob("*.sql")):
        if path.name in applied:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,)
            )
        newly_applied.append(path.name)
    return newly_applied


def main() -> None:
    with connect(Settings(), autocommit=True) as conn:
        newly_applied = apply_migrations(conn)
    if newly_applied:
        print(f"Applied migrations: {', '.join(newly_applied)}")
    else:
        print("No pending migrations")


if __name__ == "__main__":
    main()
