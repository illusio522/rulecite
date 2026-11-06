"""원본 문서를 형식과 무관한 공통 구조(문서 > 섹션 > 블록)로 바꾼다.

- 법령: 국가법령정보센터 본문 HTML (data/public/*.html)
- 회사 규정과 일반 문서: front matter가 있는 Markdown (data/company/*.md)

새 형식을 지원하려면 같은 공통 구조를 돌려주는 파서만 추가한다.
처리 규칙과 이유는 docs/02-architecture.md의 "문서 파싱 규칙"에 있다.
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup, Tag

LAW = "LAW"
COMPANY_RULE = "COMPANY_RULE"
ACCESS_LEVELS = {"ALL", "HR_ONLY"}

# 법령 장·절 제목의 단위와 깊이. 큰 단위가 나오면 그 아래 단위 경로를 비운다.
HEADING_LEVELS = {"편": 0, "장": 1, "절": 2, "관": 3}
HEADING_PATTERN = re.compile(r"^제\d+(?:의\d+)?(편|장|절|관)\b")
ARTICLE_LABEL_PATTERN = re.compile(r"^(제\d+조(?:의\d+)?)\s*(?:\(\s*(.*?)\s*\))?$")
LAW_HEADER_PATTERN = re.compile(
    r"\[시행\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\]\s*"
    r"\[((?:법률|대통령령|총리령|[가-힣]+부령)\s*제\d+호)"
)
CIRCLED_NUMBERS = (
    [chr(c) for c in range(0x2460, 0x2474)]  # ①-⑳
    + [chr(c) for c in range(0x3251, 0x3260)]  # ㉑-㉟
    + [chr(c) for c in range(0x32B1, 0x32C0)]  # ㊱-㊿
)
ITEM_PATTERN = re.compile(r"^(\d+)(?:의(\d+))?\.\s")
SUB_ITEM_PATTERN = re.compile(r"^([가-하])\.\s")
# "③ 삭제", "2. 삭제", "가. 삭제"처럼 내용 없이 삭제 표시만 남은 줄
DELETED_LINE_PATTERN = re.compile(
    r"^(?:[①-⓿㉑-㉟㊱-㊿]|\d+(?:의\d+)?\.|[가-힣]\.)?\s*삭제$"
)


@dataclass(frozen=True)
class Block:
    """섹션 본문의 한 줄.

    level 1은 항이나 문단, 2는 호나 목록 항목, 3은 목이나 하위 목록 항목이다.
    label은 출처에 쓰는 번호다(예: "제1항", "제3호", "가목").
    번호가 없으면 빈 문자열이다.
    """

    level: int
    label: str
    text: str


@dataclass(frozen=True)
class Section:
    """조각의 기본 단위. 법령에서는 조, 일반 문서에서는 가장 작은 제목 아래 내용이다.

    path는 상위 제목 경로(예: 장·절), label은 조 번호(일반 문서는 빈 문자열)다.
    """

    path: tuple[str, ...]
    label: str
    title: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    doc_type: str
    access_level: str
    version: str
    effective_date: date
    source_path: str
    sections: tuple[Section, ...]


def parse_document(path: Path, root: Path) -> ParsedDocument:
    """파일 확장자에 맞는 파서로 문서를 읽는다. source_path는 root 기준 경로다."""
    source_path = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        return parse_law_html(text, source_path)
    if path.suffix == ".md":
        return parse_markdown(text, source_path)
    raise ValueError(f"Unsupported document type: {source_path}")


def classify_line(text: str) -> Block:
    """줄 앞의 번호로 블록 단계와 출처 라벨을 정한다."""
    if text and text[0] in CIRCLED_NUMBERS:
        return Block(1, f"제{CIRCLED_NUMBERS.index(text[0]) + 1}항", text)
    item = ITEM_PATTERN.match(text)
    if item is not None:
        number, branch = item.groups()
        return Block(2, f"제{number}호" + (f"의{branch}" if branch else ""), text)
    sub_item = SUB_ITEM_PATTERN.match(text)
    if sub_item is not None:
        return Block(3, f"{sub_item.group(1)}목", text)
    return Block(1, "", text)


def parse_law_html(html: str, source_path: str) -> ParsedDocument:
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.select_one("#conTop h2")
    header_tag = soup.select_one("#conTop .ct_sub")
    if title_tag is None or header_tag is None:
        raise ValueError(f"Law title or header not found: {source_path}")
    # h2 안의 <span>(약칭)은 제목에서 뺀다.
    title = _normalize(
        "".join(t for t in title_tag.find_all(string=True, recursive=False))
    )
    header = LAW_HEADER_PATTERN.search(_normalize(header_tag.get_text()))
    if header is None:
        raise ValueError(f"Law effective date or number not found: {source_path}")
    year, month, day, version = header.groups()

    # 부칙 영역(#arDivArea)은 과거 개정의 경과 규정이라 제외한다.
    addenda = soup.select_one("#arDivArea")
    if addenda is not None:
        addenda.decompose()

    sections = []
    path: list[tuple[int, str]] = []
    for group in soup.select("div.pgroup"):
        heading = group.select_one("p.gtit")
        if heading is not None:
            path = _push_law_heading(path, _normalize(heading.get_text()))
            continue
        content = group.select_one("div.lawcon")
        if content is None or content.select_one('input[id^="delJo"]') is not None:
            continue
        section = _parse_law_article(content, tuple(text for _, text in path))
        if section is not None:
            sections.append(section)

    return ParsedDocument(
        title=title,
        doc_type=LAW,
        access_level="ALL",
        version=_normalize(version),
        effective_date=date(int(year), int(month), int(day)),
        source_path=source_path,
        sections=tuple(sections),
    )


def _parse_law_article(content: Tag, path: tuple[str, ...]) -> Section | None:
    label_tag = content.select_one("span.bl")
    if label_tag is None:
        return None
    match = ARTICLE_LABEL_PATTERN.match(_normalize(label_tag.get_text()))
    if match is None:
        return None
    number, title = match.group(1), match.group(2) or ""
    label_tag.decompose()

    # 개정 이력 표시는 지우고, 아직 시행 전임을 알리는 [시행일: ...] 표시는 남긴다.
    for note in content.select("span.sfon"):
        if not _normalize(note.get_text()).startswith("[시행일"):
            note.decompose()

    blocks = []
    for paragraph in content.find_all("p"):
        line = _normalize(paragraph.get_text())
        if line and not DELETED_LINE_PATTERN.match(line):
            blocks.append(classify_line(line))
    if not blocks:
        return None
    return Section(path=path, label=number, title=title, blocks=tuple(blocks))


def parse_markdown(markdown: str, source_path: str) -> ParsedDocument:
    """front matter가 있는 Markdown을 읽는다.

    제목(#)마다 새 섹션을 시작하고, 상위 제목은 경로가 된다.
    제목이 "제N조(제목)" 형식이면 조 번호를 섹션 라벨로 쓴다.
    """
    meta, body = _split_front_matter(markdown, source_path)
    access_level = meta.get("access_level", "")
    if access_level not in ACCESS_LEVELS:
        raise ValueError(f"Invalid access_level {access_level!r}: {source_path}")
    try:
        title = meta["title"]
        version = meta["version"]
        effective_date = date.fromisoformat(meta["effective_date"])
    except (KeyError, ValueError) as error:
        raise ValueError(f"Invalid front matter: {source_path}") from error

    sections: list[Section] = []
    headings: list[tuple[int, str]] = []
    blocks: list[Block] = []

    def flush() -> None:
        if not blocks:
            return
        *parents, current = headings or [(0, "")]
        label_match = ARTICLE_LABEL_PATTERN.match(current[1])
        sections.append(
            Section(
                path=tuple(text for _, text in parents),
                label=label_match.group(1) if label_match else "",
                title=(label_match.group(2) or "") if label_match else current[1],
                blocks=tuple(blocks),
            )
        )

    for raw_line in body.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.*)$", raw_line)
        if heading is not None:
            flush()
            blocks = []
            depth, text = len(heading.group(1)), _normalize(heading.group(2))
            # 문서 제목과 같은 최상위 제목은 경로에 넣지 않는다.
            if depth == 1 and text == title:
                headings = []
                continue
            # 부칙은 시행일만 담고 있어 제외한다. 시행일은 front matter에 있다.
            if text.replace(" ", "") == "부칙":
                break
            headings = [h for h in headings if h[0] < depth] + [(depth, text)]
            continue
        line = raw_line.strip()
        if not line:
            continue
        bullet = re.match(r"^(\s*)[-*]\s+(.*)$", raw_line)
        if bullet is not None:
            level = 3 if len(bullet.group(1)) >= 2 else 2
            blocks.append(Block(level, "", _normalize(bullet.group(2))))
        else:
            blocks.append(classify_line(_normalize(line)))
    else:
        flush()

    return ParsedDocument(
        title=title,
        doc_type=COMPANY_RULE,
        access_level=access_level,
        version=version,
        effective_date=effective_date,
        source_path=source_path,
        sections=tuple(sections),
    )


def _split_front_matter(markdown: str, source_path: str) -> tuple[dict[str, str], str]:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"Front matter not found: {source_path}")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError(f"Front matter is not closed: {source_path}") from error
    meta = {}
    for line in lines[1:end]:
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, "\n".join(lines[end + 1 :])


def _push_law_heading(
    path: list[tuple[int, str]], heading: str
) -> list[tuple[int, str]]:
    """법령 장·절 제목을 경로에 넣는다.

    단위를 알 수 없는 제목은 가장 깊은 단계로 둔다.
    """
    match = HEADING_PATTERN.match(heading)
    level = HEADING_LEVELS[match.group(1)] if match else len(HEADING_LEVELS)
    return [item for item in path if item[0] < level] + [(level, heading)]


def _normalize(text: str) -> str:
    """연속 공백을 하나로 줄이고, 괄호 안쪽 공백을 없앤다."""
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", text))
