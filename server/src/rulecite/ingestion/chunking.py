"""공통 구조(문서 > 섹션 > 블록)를 검색 조각으로 나눈다.

- 구조 분할(chunk_by_structure): 섹션 하나를 조각 하나로 만들고,
  길면 블록 단계 경계에서 나눈다.
- 고정 길이 분할(chunk_by_length): 구조를 보지 않고 일정 길이로 자른다.
  구조가 없는 문서의 최후 수단이자, 평가에서 구조 분할과 비교하는 기준선이다.

규칙과 이유는 docs/02-architecture.md의 "분할 규칙"에 있다.
"""

import re
from dataclasses import dataclass

from rulecite.ingestion.parsing import Block, ParsedDocument, Section

MAX_CHUNK_CHARS = 800
FIXED_CHUNK_CHARS = 500
FIXED_OVERLAP_CHARS = 100
DEEPEST_BLOCK_LEVEL = 3


@dataclass(frozen=True)
class Chunk:
    source_path: str
    path: tuple[str, ...]
    heading: str
    citation: str
    content: str


def chunk_by_structure(
    document: ParsedDocument, max_chars: int = MAX_CHUNK_CHARS
) -> list[Chunk]:
    chunks = []
    for section in document.sections:
        heading = section_heading(section)
        labels = _full_labels(section.blocks)
        indexed = list(zip(section.blocks, labels, strict=True))
        groups = _split(indexed, max_chars, level=1)
        for number, group in enumerate(groups, start=1):
            citation = _section_citation(document.title, section)
            if len(groups) > 1:
                citation += " " + _group_suffix(group, number, len(groups))
            lines = [heading] if heading else []
            lines += [block.text for block, _ in group]
            chunks.append(
                Chunk(
                    source_path=document.source_path,
                    path=section.path,
                    heading=heading,
                    citation=citation,
                    content="\n".join(lines),
                )
            )
    return chunks


def chunk_by_length(
    document: ParsedDocument,
    size: int = FIXED_CHUNK_CHARS,
    overlap: int = FIXED_OVERLAP_CHARS,
) -> list[Chunk]:
    lines = []
    for section in document.sections:
        heading = section_heading(section)
        if heading:
            lines.append(heading)
        lines += [block.text for block in section.blocks]
    text = "\n".join(lines)

    chunks = []
    step = size - overlap
    for number, start in enumerate(range(0, max(len(text) - overlap, 1), step), 1):
        chunks.append(
            Chunk(
                source_path=document.source_path,
                path=(),
                heading="",
                citation=f"{document.title} (조각 {number})",
                content=text[start : start + size],
            )
        )
    return chunks


def section_heading(section: Section) -> str:
    """조각 맨 앞에 붙일 제목 줄. 예: "제60조(연차 유급휴가)", "신청 절차"."""
    if section.label:
        return f"{section.label}({section.title})" if section.title else section.label
    return section.title


def _section_citation(document_title: str, section: Section) -> str:
    if section.label:
        return f"{document_title} {section.label}"
    return " > ".join([document_title, *section.path, section.title])


def _group_suffix(group: list[tuple[Block, str]], number: int, total: int) -> str:
    """나뉜 조각의 범위. 번호가 있으면 "제1항~제3항", 없으면 "(2/3)"."""
    labels = [label for _, label in group if label]
    if not labels:
        return f"({number}/{total})"
    first, last = labels[0], labels[-1]
    # 항이 자기 호를 포함하면 항만 적는다. 예: 제1항~제1항제2호 → 제1항
    if last.startswith(first):
        return first
    # 같은 항 안의 호 범위는 뒤쪽 항 번호를 생략한다. 예: 제1항제3호~제5호
    paragraph = re.match(r"제\d+항", first)
    if paragraph is not None and last.startswith(paragraph.group()):
        last = last[paragraph.end() :]
    return f"{first}~{last}"


def _full_labels(blocks: tuple[Block, ...]) -> list[str]:
    """블록마다 상위 번호까지 붙인 라벨을 만든다.

    예: 제1항 아래 제3호 → "제1항제3호"
    """
    labels = []
    context = {1: "", 2: ""}
    for block in blocks:
        if block.level == 1:
            context = {1: block.label, 2: ""}
            labels.append(block.label)
        elif block.level == 2:
            context[2] = block.label
            labels.append(context[1] + block.label if block.label else "")
        else:
            labels.append(context[1] + context[2] + block.label if block.label else "")
    return labels


def _split(
    blocks: list[tuple[Block, str]], max_chars: int, level: int
) -> list[list[tuple[Block, str]]]:
    """블록이 max_chars를 넘으면 level 단계 경계에서 나눈다.

    상위 블록에 딸린 하위 블록은 함께 묶는다.
    한 묶음이 그래도 길면 한 단계 아래에서 다시 나눈다.
    가장 깊은 단계에서도 나눌 수 없는 블록 하나는 길어도 그대로 둔다.
    """
    if _size(blocks) <= max_chars or level > DEEPEST_BLOCK_LEVEL:
        return [blocks]

    units: list[list[tuple[Block, str]]] = []
    for item in blocks:
        if not units or item[0].level <= level:
            units.append([item])
        else:
            units[-1].append(item)
    if len(units) == 1:
        return _split(blocks, max_chars, level + 1)

    groups: list[list[tuple[Block, str]]] = []
    current: list[tuple[Block, str]] = []
    for unit in units:
        if _size(unit) > max_chars:
            if current:
                groups.append(current)
                current = []
            groups += _split(unit, max_chars, level + 1)
        elif _size(current) + _size(unit) <= max_chars:
            current += unit
        else:
            groups.append(current)
            current = list(unit)
    if current:
        groups.append(current)
    return groups


def _size(blocks: list[tuple[Block, str]]) -> int:
    return sum(len(block.text) for block, _ in blocks)
