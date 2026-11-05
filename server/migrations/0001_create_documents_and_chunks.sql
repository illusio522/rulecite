-- 문서와 검색 조각 테이블을 만든다.
-- pgvector 확장은 DB 준비 단계에서 관리자 계정으로 설치한다. 이미 있으면 아무것도 하지 않는다.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    doc_type text NOT NULL CHECK (doc_type IN ('LAW', 'COMPANY_RULE')),
    access_level text NOT NULL CHECK (access_level IN ('ALL', 'HR_ONLY')),
    version text NOT NULL,
    effective_date date NOT NULL,
    source_path text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    -- 조각의 (document_id, access_level) 외래 키가 참조할 수 있도록 둔다.
    UNIQUE (id, access_level)
);

CREATE TABLE chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL,
    path text NOT NULL,
    content text NOT NULL,
    embedding vector(1536) NOT NULL,
    -- 검색 쿼리에서 조인 없이 권한 조건을 걸기 위해 문서의 접근 등급을 복사해 둔다.
    access_level text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    -- 복사한 접근 등급이 문서와 어긋나지 않도록 함께 참조한다.
    FOREIGN KEY (document_id, access_level)
        REFERENCES documents (id, access_level)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

CREATE INDEX chunks_document_id_idx ON chunks (document_id);
