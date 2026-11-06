from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# 저장소 루트의 .env (server/src/rulecite/config.py 기준 세 단계 위)
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_ignore_empty=True, extra="ignore"
    )

    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr

    # DB만 쓰는 명령(마이그레이션 등)은 키 없이도 실행되도록 선택 값으로 둔다.
    gemini_api_key: SecretStr | None = None
    embedding_model: str = "gemini-embedding-2"
