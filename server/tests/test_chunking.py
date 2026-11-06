from datetime import date
from pathlib import Path

from rulecite.ingestion.chunking import (
    MAX_CHUNK_CHARS,
    chunk_by_length,
    chunk_by_structure,
)
from rulecite.ingestion.parsing import (
    LAW,
    Block,
    ParsedDocument,
    Section,
    parse_document,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def make_document(*sections: Section) -> ParsedDocument:
    return ParsedDocument(
        title="가상법",
        doc_type=LAW,
        access_level="ALL",
        version="법률 제1호",
        effective_date=date(2026, 1, 1),
        source_path="data/public/fake.html",
        sections=sections,
    )


def filler(prefix: str, size: int) -> str:
    return prefix + "가" * (size - len(prefix))


def test_short_section_becomes_one_chunk_with_heading():
    """짧은 조문은 조 제목 줄을 앞에 붙인 조각 하나가 된다."""
    # given
    section = Section(
        path=("제1장 총칙",),
        label="제60조",
        title="연차 유급휴가",
        blocks=(
            Block(1, "제1항", "① 15일을 준다."),
            Block(1, "제2항", "② 1일을 준다."),
        ),
    )

    # when
    [chunk] = chunk_by_structure(make_document(section))

    # then
    assert chunk.citation == "가상법 제60조"
    assert chunk.heading == "제60조(연차 유급휴가)"
    assert chunk.path == ("제1장 총칙",)
    assert chunk.content == "제60조(연차 유급휴가)\n① 15일을 준다.\n② 1일을 준다."


def test_long_section_is_split_at_paragraph_boundaries():
    """긴 조문은 항 경계에서 나누고, 출처에 항 범위를 붙인다."""
    # given
    section = Section(
        path=(),
        label="제2조",
        title="휴가",
        blocks=(
            Block(1, "제1항", filler("① ", 400)),
            Block(1, "제2항", filler("② ", 400)),
            Block(1, "제3항", filler("③ ", 400)),
        ),
    )

    # when
    chunks = chunk_by_structure(make_document(section))

    # then
    assert [c.citation for c in chunks] == [
        "가상법 제2조 제1항~제2항",
        "가상법 제2조 제3항",
    ]
    assert all(c.content.startswith("제2조(휴가)\n") for c in chunks)


def test_items_stay_with_their_paragraph():
    """호는 자기가 속한 항과 같은 조각에 들어간다."""
    # given
    section = Section(
        path=(),
        label="제3조",
        title="정의",
        blocks=(
            Block(1, "제1항", filler("① ", 300)),
            Block(1, "제2항", filler("② ", 300)),
            Block(2, "제1호", filler("1. ", 300)),
            Block(1, "제3항", filler("③ ", 100)),
        ),
    )

    # when
    chunks = chunk_by_structure(make_document(section))

    # then
    assert [c.citation for c in chunks] == [
        "가상법 제3조 제1항",
        "가상법 제3조 제2항~제3항",
    ]
    assert "1. " in chunks[1].content


def test_paragraph_longer_than_limit_is_split_at_item_boundaries():
    """항 하나가 한도를 넘으면 그 항 안의 호 경계에서 나누고, 출처에 항까지 적는다."""
    # given
    section = Section(
        path=(),
        label="제4조",
        title="기간",
        blocks=(
            Block(1, "제1항", filler("① ", 100)),
            Block(2, "제1호", filler("1. ", 400)),
            Block(2, "제2호", filler("2. ", 400)),
        ),
    )

    # when
    chunks = chunk_by_structure(make_document(section))

    # then
    assert [c.citation for c in chunks] == [
        "가상법 제4조 제1항",
        "가상법 제4조 제1항제2호",
    ]


def test_item_range_in_same_paragraph_omits_repeated_paragraph():
    """같은 항 안의 호 범위는 뒤쪽 항 번호를 생략한다."""
    # given
    section = Section(
        path=(),
        label="제6조",
        title="",
        blocks=(
            Block(1, "제1항", filler("① ", 790)),
            Block(2, "제1호", filler("1. ", 300)),
            Block(2, "제2호", filler("2. ", 300)),
        ),
    )

    # when
    chunks = chunk_by_structure(make_document(section))

    # then
    assert [c.citation for c in chunks] == [
        "가상법 제6조 제1항",
        "가상법 제6조 제1항제1호~제2호",
    ]


def test_single_block_longer_than_limit_is_kept_whole():
    """더 나눌 경계가 없는 블록 하나는 길어도 자르지 않는다."""
    # given
    section = Section(
        path=(), label="제5조", title="", blocks=(Block(1, "", filler("", 1200)),)
    )

    # when
    [chunk] = chunk_by_structure(make_document(section))

    # then
    assert chunk.citation == "가상법 제5조"
    assert chunk.content == "제5조\n" + filler("", 1200)


def test_section_without_label_uses_heading_path_as_citation():
    """조 번호가 없는 일반 문서는 제목 경로를 출처로 쓰고, 나뉘면 순번을 붙인다."""
    # given
    section = Section(
        path=("휴가",),
        label="",
        title="신청 절차",
        blocks=(Block(1, "", filler("", 500)), Block(1, "", filler("", 500))),
    )

    # when
    chunks = chunk_by_structure(make_document(section))

    # then
    assert [c.citation for c in chunks] == [
        "가상법 > 휴가 > 신청 절차 (1/2)",
        "가상법 > 휴가 > 신청 절차 (2/2)",
    ]
    assert chunks[0].content.startswith("신청 절차\n")


def test_fixed_length_chunks_overlap_and_cover_whole_text():
    """고정 길이 분할은 겹치는 구간을 두고 문서 전체를 빠짐없이 덮는다."""
    # given
    section = Section(path=(), label="", title="", blocks=(Block(1, "", "가" * 1000),))

    # when
    chunks = chunk_by_length(make_document(section), size=500, overlap=100)

    # then
    assert [len(c.content) for c in chunks] == [500, 500, 200]
    assert chunks[0].content[-100:] == chunks[1].content[:100]
    assert [c.citation for c in chunks] == [
        "가상법 (조각 1)",
        "가상법 (조각 2)",
        "가상법 (조각 3)",
    ]


def test_real_documents_follow_structure_rules():
    """실제 문서 12개의 조각은 한도를 지키거나, 더 나눌 수 없는 블록 하나만 담는다."""
    # given
    paths = sorted(
        [*(REPO_ROOT / "data/public").glob("*.html")]
        + [*(REPO_ROOT / "data/company").glob("*.md")]
    )
    documents = [parse_document(path, REPO_ROOT) for path in paths]

    # when
    chunks = [chunk for d in documents for chunk in chunk_by_structure(d)]

    # then
    for chunk in chunks:
        body = chunk.content.split("\n")[1:]
        assert sum(map(len, body)) <= MAX_CHUNK_CHARS or len(body) == 1
    labor_60 = [c for c in chunks if c.citation.startswith("근로기준법 제60조")]
    assert labor_60[0].heading == "제60조(연차 유급휴가)"
