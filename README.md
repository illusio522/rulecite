# RuleCite

출처를 근거로 답하는 인사·노무 규정 Q&A 봇

공개 법령과 가상 회사 규정을 근거로, 슬랙에서 인사 규정 질문에 출처와 함께 답하는 RAG 서비스입니다.

> 현재 착수 단계입니다. 구현이 진행되면 구조도, 평가 결과, 실행 방법을 이 문서에 채웁니다.

## 시작하기

필요한 도구: Git, Docker, Python 3.14, Poetry, Claude Code

개발 DB는 `~/Workspace/shared-infra`의 PostgreSQL을 씁니다. 처음이면 shared-infra README대로 그 저장소의 `.env`를 먼저 만듭니다.

```bash
# 공용 PostgreSQL 실행
docker compose -f ~/Workspace/shared-infra/docker-compose.yml --project-directory ~/Workspace/shared-infra up -d postgres

# RuleCite 전용 DB 계정과 .env 생성 (처음 한 번)
scripts/setup-dev-db.sh

# 서버 의존성 설치와 마이그레이션
cd server
poetry env use python3.14 && poetry install
poetry run python -m rulecite.db.migrate
cd ..

claude
```

Claude Code가 열리면 다음을 입력합니다.

```text
/next-task
```

로드맵에서 다음 작업을 골라 계획을 제시하고, 승인하면 구현을 진행합니다.

## 기술 스택

버전은 `server/pyproject.toml`과 `server/poetry.lock`에 고정되어 있습니다. 이 표에는 각 항목을 쓰는 이유만 적습니다.

| 구분 | 이름 | 용도 |
|---|---|---|
| 언어 | Python 3.14 | 서버 전체 |
| 패키지 관리 | Poetry | 의존성 설치와 버전 고정 |
| 웹 프레임워크 | `fastapi` | HTTP API와 요청·응답 검증 |
| 서버 실행 | `uvicorn` | FastAPI 앱을 띄우는 ASGI 서버 |
| DB | PostgreSQL 17 + pgvector | 서비스 데이터와 벡터 저장. shared-infra의 `pgvector/pgvector:pg17` 이미지 |
| DB 드라이버 | `psycopg[binary]` | PostgreSQL 접속과 SQL 실행. ORM 없이 SQL을 직접 쓴다 |
| 설정 | `pydantic-settings` | `.env`와 환경 변수를 타입이 있는 설정으로 읽기 |
| HTML 파싱 | `beautifulsoup4` | 국가법령정보센터 법령 HTML에서 조문 추출 |
| 테스트 (개발용) | `pytest` | 테스트 실행 |
| 테스트 (개발용) | `httpx2` | FastAPI `TestClient`가 요청을 보낼 때 쓰는 HTTP 클라이언트 |
| lint·format (개발용) | `ruff` | 코드 검사와 정렬 |

LLM과 임베딩 모델은 [ADR 0002](docs/adr/0002-llm-and-embedding-models.md)에 있습니다.

## 포함된 명령

| 명령 | 역할 |
|---|---|
| `/next-task` | 로드맵의 다음 작업 진행 |
| `/evaluate` | 평가 실행 후 결과 기록 |

## 안내

이 프로젝트의 답변은 학습용 참고 정보이며 법률 자문이 아닙니다. 회사명과 사내 규정은 가상입니다.
