import psycopg

from rulecite.config import Settings


def connect(settings: Settings, *, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        autocommit=autocommit,
    )
