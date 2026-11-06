# RuleCite

출처를 근거로 답하는 인사·노무 규정 Q&A 봇.

가상의 회사 직원이 슬랙에서 인사 규정을 물으면, 사내 규정과 법령을 찾아 출처와 함께 답하는 RAG 기반 백엔드 서비스다.
학습과 AI 백엔드 개발자 포트폴리오가 목적이며 기간은 4~6주다.

## 먼저 읽을 문서

- 과제 범위: @docs/01-project-brief.md
- 구조와 설계 결정: @docs/02-architecture.md
- 평가 기준: @docs/03-evaluation.md
- 작업 순서: @docs/04-roadmap.md
- 문서 출처 규칙: @docs/05-data-sources.md
- 가상 회사 설정: @docs/06-company-profile.md

## 작업 원칙

- 로드맵의 작업을 하나씩 진행하고, 끝나면 체크 표시를 한다.
- 구현 전에 변경 계획을 짧게 설명하고, 범위 밖 기능은 추가하지 않는다.
- 사용자는 학습 중이다. 핵심 설계 선택에는 이유와 대안을 함께 설명한다.
- RAG 핵심 로직(분할, 임베딩 호출, 검색, 프롬프트 구성)은 LangChain 같은 프레임워크 없이 직접 구현한다.
- 프론트엔드는 만들지 않는다. 사용자 접점은 슬랙 봇이고, 관리 기능은 API로 제공한다.
- 중요한 설계 결정은 `docs/adr/`에 ADR로 남긴다.
- 패키지는 `poetry add <패키지>==<버전>`처럼 정확한 버전으로 고정하고, 범위 지정(`^`, `~`, `>=`)을 쓰지 않는다. 버전을 올릴 때는 사용자 확인을 받는다.
- 패키지를 추가·삭제하면 `README.md`의 기술 스택 표를, API 엔드포인트를 추가·삭제하면 `docs/02-architecture.md`의 API 표를 같은 PR에서 고친다.

## 절대 규칙

- 답변에는 근거 문서의 출처(문서명, 조항, 시행일)를 포함한다.
- 검색 근거가 부족하면 지어내지 말고 모른다고 답한다.
- 권한 필터는 LLM 호출 전에 DB 검색 단계에서 적용한다. 프롬프트로 권한을 통제하지 않는다.
- 답변은 법률 자문이 아닌 참고 정보임을 안내한다.
- 실제 회사의 내부 문서, 개인정보, API 키를 저장소에 넣지 않는다.
- `.env`의 내용을 읽거나 출력하지 않는다. 필요한 변수는 `.env.example`을 참고한다.
- 평가 수치는 실제 측정값만 기록한다.

## 저장소 구조

- `server/`: FastAPI. 인증, 권한, 문서 관리, 인덱싱 워커, 검색, 답변 생성, 대화 기록
- `bot/`: 슬랙 봇
- `eval/`: 평가 데이터셋과 평가 스크립트
- `data/`: 공개 원문과 가상 회사 규정
- `docs/`: 설계 문서

## 명령어

- DB 실행: `docker compose -f ~/Workspace/shared-infra/docker-compose.yml --project-directory ~/Workspace/shared-infra up -d postgres`
- DB 계정과 `.env` 생성(처음 한 번): `scripts/setup-dev-db.sh`
- 이 저장소의 `docker-compose.yml`의 `db` 서비스는 shared-infra의 `postgres`와 포트가 겹치므로 실행하지 않는다.
- 세부 빌드와 테스트 명령은 각 서비스를 만들 때 이 문서에 추가한다.

`server/`의 명령은 `server/` 폴더에서 실행한다.

- 의존성 설치: `poetry env use python3.14 && poetry install`
- 마이그레이션 적용: `poetry run python -m rulecite.db.migrate`
- 문서 인덱싱: `poetry run python -m rulecite.ingestion.indexing` (`.env`의 `GEMINI_API_KEY` 필요, 무료 등급 요청 한도 때문에 수 분 걸린다)
- 서버 실행: `poetry run uvicorn rulecite.main:app --reload`
- 테스트: `poetry run pytest` (DB가 실행 중이어야 한다)
- lint: `poetry run ruff check`
- format: `poetry run ruff format`
