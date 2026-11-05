"""원본 문서를 조문 단위의 공통 구조로 바꾼다.

- 법령: 국가법령정보센터 본문 HTML (data/public/*.html)
- 회사 규정: front matter가 있는 Markdown (data/company/*.md)

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

# 장·절 제목의 단위와 깊이. 큰 단위가 나오면 그 아래 단위 경로를 비운다.
HEADING_LEVELS = {"편": 0, "장": 1, "절": 2, "관": 3}
HEADING_PATTERN = re.compile(r"^제\d+(?:의\d+)?(편|장|절|관)\b")
ARTICLE_LABEL_PATTERN = re.compile(r"^(제\d+조(?:의\d+)?)\s*(?:\(\s*(.*?)\s*\))?$")
LAW_HEADER_PATTERN = re.compile(
    r"\[시행\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\]\s*"
    r"\[((?:법률|대통령령|총리령|[가-힣]+부령)\s*제\d+호)"
)
# "③ 삭제", "2. 삭제", "가. 삭제"처럼 내용 없이 삭제 표시만 남은 줄
DELETED_LINE_PATTERN = re.compile(
    r"^(?:[①-⓿㉑-㉟㊱-㊿]|\d+(?:의\d+)?\.|[가-힣]\.)?\s*삭제$"
)


@dataclass(frozen=True)
class Article:
    path: tuple[str, ...]
    number: str
    title: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    doc_type: str
    access_level: str
    version: str
    effective_date: date
    source_path: str
    articles: tuple[Article, ...]


def parse_document(path: Path, root: Path) -> ParsedDocument:
    """파일 확장자에 맞는 파서로 문서를 읽는다. source_path는 root 기준 경로다."""
    source_path = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        return parse_law_html(text, source_path)
    if path.suffix == ".md":
        return parse_company_markdown(text, source_path)
    raise ValueError(f"Unsupported document type: {source_path}")


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

    articles = []
    path: list[tuple[int, str]] = []
    for group in soup.select("div.pgroup"):
        heading = group.select_one("p.gtit")
        if heading is not None:
            path = _push_heading(path, _normalize(heading.get_text()))
            continue
        content = group.select_one("div.lawcon")
        if content is None or content.select_one('input[id^="delJo"]') is not None:
            continue
        article = _parse_law_article(content, tuple(text for _, text in path))
        if article is not None:
            articles.append(article)

    return ParsedDocument(
        title=title,
        doc_type=LAW,
        access_level="ALL",
        version=_normalize(version),
        effective_date=date(int(year), int(month), int(day)),
        source_path=source_path,
        articles=tuple(articles),
    )


def _parse_law_article(content: Tag, path: tuple[str, ...]) -> Article | None:
    label = content.select_one("span.bl")
    if label is None:
        return None
    match = ARTICLE_LABEL_PATTERN.match(_normalize(label.get_text()))
    if match is None:
        return None
    number, title = match.group(1), match.group(2) or ""
    label.decompose()

    # 개정 이력 표시는 지우고, 아직 시행 전임을 알리는 [시행일: ...] 표시는 남긴다.
    for note in content.select("span.sfon"):
        if not _normalize(note.get_text()).startswith("[시행일"):
            note.decompose()

    lines = []
    for paragraph in content.find_all("p"):
        line = _normalize(paragraph.get_text())
        if line and not DELETED_LINE_PATTERN.match(line):
            lines.append(line)
    if not lines:
        return None
    return Article(path=path, number=number, title=title, lines=tuple(lines))


def parse_company_markdown(markdown: str, source_path: str) -> ParsedDocument:
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

    articles = []
    path: list[tuple[int, str]] = []
    current: tuple[str, str] | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current is not None and current_lines:
            number, article_title = current
            articles.append(
                Article(
                    path=tuple(text for _, text in path),
                    number=number,
                    title=article_title,
                    lines=tuple(current_lines),
                )
            )

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            flush()
            current, current_lines = None, []
            heading = _normalize(line[3:])
            # 부칙은 시행일만 담고 있어 제외한다. 시행일은 front matter에 있다.
            if heading.replace(" ", "") == "부칙":
                break
            path = _push_heading(path, heading)
        elif line.startswith("### "):
            flush()
            match = ARTICLE_LABEL_PATTERN.match(_normalize(line[4:]))
            if match is None:
                raise ValueError(f"Invalid article heading {line!r}: {source_path}")
            current, current_lines = (match.group(1), match.group(2) or ""), []
        elif line and not line.startswith("# ") and current is not None:
            current_lines.append(_normalize(line))
    else:
        flush()

    return ParsedDocument(
        title=title,
        doc_type=COMPANY_RULE,
        access_level=access_level,
        version=version,
        effective_date=effective_date,
        source_path=source_path,
        articles=tuple(articles),
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


def _push_heading(path: list[tuple[int, str]], heading: str) -> list[tuple[int, str]]:
    """장·절 제목을 경로에 넣는다. 단위를 알 수 없는 제목은 가장 깊은 단계로 둔다."""
    match = HEADING_PATTERN.match(heading)
    level = HEADING_LEVELS[match.group(1)] if match else len(HEADING_LEVELS)
    return [item for item in path if item[0] < level] + [(level, heading)]


def _normalize(text: str) -> str:
    """연속 공백을 하나로 줄이고, 괄호 안쪽 공백을 없앤다."""
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", text))
