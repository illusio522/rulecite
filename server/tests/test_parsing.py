from datetime import date
from pathlib import Path

import pytest

from rulecite.ingestion.parsing import (
    COMPANY_RULE,
    LAW,
    Block,
    parse_document,
    parse_law_html,
    parse_markdown,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# 국가법령정보센터 본문 HTML 구조를 줄인 합성 예시
LAW_HTML = """
<div id="conTop"><h2> 가상근로법 <span>( 약칭: 가상법 )</span> </h2>
<div class="ct_sub">
  <span>[시행 2026. 3. 1.] [법률 제12345호, 2026. 1. 2., 일부개정]</span>
</div>
</div>
<div class="pgroup"><p class="gtit"> 제1장 총칙 </p></div>
<div class="pgroup"><div class="lawcon">
  <p class="pty1_p4"><span class="bl"><label> 제1조(목적) </label></span>
  이 법은 근로자를 보호한다. <span class="sfon">&lt;개정 2020. 1. 1.&gt;</span></p>
</div></div>
<div class="pgroup"><p class="gtit"> 제1절 휴가 </p></div>
<div class="pgroup"><div class="lawcon">
  <p class="pty1_p4"><span class="bl"><label> 제2조( 연차 휴가 ) </label></span>
  ① 사용자는 15일의 휴가를 준다.</p>
  <p class="pty1_de2_1">② 삭제 <span class="sfon">&lt;2017. 11. 28.&gt;</span></p>
  <p class="pty1_de2h">1. <a>제1조</a><a>제1항</a>에 따른 기간</p>
  <p class="pty1_de2"><span class="sfon">[시행일: 2027. 1. 1.] 제2조제1항</span></p>
</div></div>
<div class="pgroup"><div class="lawcon">
  <p class="pty1_p4"><span class="bl"><label> 제3조 </label></span>
  <input type="hidden" id="delJo1" value="삭제" /> 삭제
  <span class="sfon">&lt;2019. 1. 15.&gt;</span></p>
</div></div>
<div class="pgroup"><p class="gtit"> 제2장 보칙 </p></div>
<div class="pgroup"><div class="lawcon">
  <p class="pty1_p4"><span class="bl"><label> 제3조의2(벌칙) </label></span>
  위반하면 과태료를 부과한다.</p>
</div></div>
<div id="arDivArea"><div class="pgroup"><div class="lawcon">
  <p class="pty1_p4"><span class="bl"><label> 제1조(시행일) </label></span>
  이 법은 공포한 날부터 시행한다.</p>
</div></div></div>
"""

COMPANY_MARKDOWN = """---
title: 가상 규정
company: analogia
access_level: HR_ONLY
version: "1.0"
effective_date: 2026-01-01
---

# 가상 규정

## 제1장 총칙

### 제1조(목적)

이 규정은 목적을 정한다.

### 제2조(휴가)

① 회사는 휴가를 준다.

1. 결혼: 5일

## 부칙

### 제1조(시행일)

이 규정은 2026년 1월 1일부터 시행한다.
"""


GENERAL_MARKDOWN = """---
title: 인사 매뉴얼
access_level: ALL
version: "2.0"
effective_date: 2026-02-01
---

# 인사 매뉴얼

## 휴가

### 신청 절차

휴가는 사내 시스템에서 신청한다.

- 3일 이상은 팀장 승인이 필요하다.
  - 승인은 사용 전날까지 받는다.
"""


def text_lines(section):
    return tuple(block.text for block in section.blocks)


def test_law_html_reads_title_version_and_effective_date():
    """법령 제목은 약칭을 빼고, 법령 번호와 시행일은 머리 줄에서 읽는다."""
    # given
    html = LAW_HTML

    # when
    document = parse_law_html(html, "data/public/fake.html")

    # then
    assert document.title == "가상근로법"
    assert document.version == "법률 제12345호"
    assert document.effective_date == date(2026, 3, 1)
    assert document.doc_type == LAW
    assert document.access_level == "ALL"


def test_law_html_excludes_addenda_and_deleted_articles():
    """부칙 조문과 삭제된 조문은 결과에 넣지 않는다."""
    # given
    html = LAW_HTML

    # when
    document = parse_law_html(html, "data/public/fake.html")

    # then
    assert [s.label for s in document.sections] == ["제1조", "제2조", "제3조의2"]


def test_law_html_cleans_lines_and_classifies_blocks():
    """개정 표시와 삭제된 항은 지우고, 번호에 따라 블록 단계와 라벨을 붙인다."""
    # given
    html = LAW_HTML

    # when
    sections = parse_law_html(html, "data/public/fake.html").sections

    # then
    assert sections[1].title == "연차 휴가"
    assert sections[1].blocks == (
        Block(1, "제1항", "① 사용자는 15일의 휴가를 준다."),
        Block(2, "제1호", "1. 제1조제1항에 따른 기간"),
        Block(1, "", "[시행일: 2027. 1. 1.] 제2조제1항"),
    )
    assert text_lines(sections[0]) == ("이 법은 근로자를 보호한다.",)


def test_law_html_tracks_chapter_and_section_path():
    """절은 장 아래에 붙고, 새 장이 나오면 이전 절은 경로에서 빠진다."""
    # given
    html = LAW_HTML

    # when
    sections = parse_law_html(html, "data/public/fake.html").sections

    # then
    assert sections[0].path == ("제1장 총칙",)
    assert sections[1].path == ("제1장 총칙", "제1절 휴가")
    assert sections[2].path == ("제2장 보칙",)


def test_markdown_reads_front_matter_and_excludes_addenda():
    """front matter로 문서 정보를 읽고, 조 제목은 라벨로, 부칙 이후는 넣지 않는다."""
    # given
    markdown = COMPANY_MARKDOWN

    # when
    document = parse_markdown(markdown, "data/company/fake.md")

    # then
    assert document.title == "가상 규정"
    assert document.doc_type == COMPANY_RULE
    assert document.access_level == "HR_ONLY"
    assert document.version == "1.0"
    assert document.effective_date == date(2026, 1, 1)
    assert [(s.label, s.title) for s in document.sections] == [
        ("제1조", "목적"),
        ("제2조", "휴가"),
    ]
    assert document.sections[1].path == ("제1장 총칙",)
    assert document.sections[1].blocks == (
        Block(1, "제1항", "① 회사는 휴가를 준다."),
        Block(2, "제1호", "1. 결혼: 5일"),
    )


def test_markdown_without_article_numbers_uses_headings():
    """조 번호가 없는 일반 문서는 제목을 섹션 이름으로, 목록을 하위 블록으로 읽는다."""
    # given
    markdown = GENERAL_MARKDOWN

    # when
    document = parse_markdown(markdown, "data/company/manual.md")

    # then
    [section] = document.sections
    assert section.path == ("휴가",)
    assert section.label == ""
    assert section.title == "신청 절차"
    assert section.blocks == (
        Block(1, "", "휴가는 사내 시스템에서 신청한다."),
        Block(2, "", "3일 이상은 팀장 승인이 필요하다."),
        Block(3, "", "승인은 사용 전날까지 받는다."),
    )


def test_markdown_rejects_unknown_access_level():
    """정해지지 않은 접근 등급의 문서는 거부한다."""
    # given
    markdown = COMPANY_MARKDOWN.replace("HR_ONLY", "PUBLIC")

    # when / then
    with pytest.raises(ValueError, match="access_level"):
        parse_markdown(markdown, "data/company/fake.md")


def test_real_labor_standards_act_is_parsed():
    """저장한 근로기준법 원문에서 본칙 조문과 문서 정보를 읽는다."""
    # given
    path = REPO_ROOT / "data/public/labor-standards-act.html"

    # when
    document = parse_document(path, REPO_ROOT)

    # then
    assert document.title == "근로기준법"
    assert document.version == "법률 제21533호"
    assert document.effective_date == date(2026, 10, 8)
    assert document.source_path == "data/public/labor-standards-act.html"
    assert len(document.sections) == 131
    article_60 = next(s for s in document.sections if s.label == "제60조")
    assert article_60.title == "연차 유급휴가"
    assert article_60.blocks[0] == Block(
        1,
        "제1항",
        "① 사용자는 1년간 80퍼센트 이상 출근한 근로자에게"
        " 15일의 유급휴가를 주어야 한다.",
    )


def test_real_disciplinary_procedure_is_hr_only():
    """징계 처리 지침은 인사팀 전용 문서로 읽고, 부칙은 넣지 않는다."""
    # given
    path = REPO_ROOT / "data/company/disciplinary-procedure.md"

    # when
    document = parse_document(path, REPO_ROOT)

    # then
    assert document.access_level == "HR_ONLY"
    assert len(document.sections) == 9
    assert document.sections[-1].label == "제9조"
