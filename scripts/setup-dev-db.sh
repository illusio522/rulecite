#!/usr/bin/env bash
# 개발용 DB를 준비한다.
# shared-infra의 PostgreSQL에 RuleCite 전용 계정과 데이터베이스를 만들고, 그 접속 정보로 .env를 작성한다.
# 비밀번호는 무작위로 만들어 .env에만 쓰고 화면에 출력하지 않는다.
#
# 사용: scripts/setup-dev-db.sh
# 전제: shared-infra의 postgres 서비스가 실행 중이다.
# 환경 변수: SHARED_INFRA_DIR (기본 ~/Workspace/shared-infra), DB_NAME (기본 rulecite), ENV_FILE (기본 저장소 루트의 .env)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INFRA="${SHARED_INFRA_DIR:-$HOME/Workspace/shared-infra}"
DB_NAME="${DB_NAME:-rulecite}"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

if [[ -e "$ENV_FILE" ]]; then
  echo "$ENV_FILE already exists. Remove it first to create a new database account." >&2
  exit 1
fi

password="$(openssl rand -hex 24)"

docker compose -f "$INFRA/docker-compose.yml" --project-directory "$INFRA" \
  exec -T -e RC_NAME="$DB_NAME" -e RC_PW="$password" postgres sh -c '
set -e
psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -v name="$RC_NAME" -v pw="$RC_PW" <<SQL
CREATE ROLE :"name" LOGIN PASSWORD :'"'"'pw'"'"';
CREATE DATABASE :"name" OWNER :"name";
SQL
psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$RC_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector"
'

(
  umask 077
  sed -e "s/^POSTGRES_DB=.*/POSTGRES_DB=$DB_NAME/" \
      -e "s/^POSTGRES_USER=.*/POSTGRES_USER=$DB_NAME/" \
      -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$password/" \
      "$ROOT/.env.example" > "$ENV_FILE"
)
echo "Created database role and database '$DB_NAME', and wrote $ENV_FILE"
