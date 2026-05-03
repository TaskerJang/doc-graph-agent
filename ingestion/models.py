"""
Layer A 노드 정의 — doc-graph-agent의 Document Structure Ontology.

본 모듈은 `docs/ontology/doc-ontology.md` §3 "Layer A 노드 정의"의 Cypher 스키마를
Python dataclass로 매핑한다. 그래프 DB 적재 전 단계의 in-memory 표현이며,
Layer B/C에서 이 객체를 입력으로 받아 Entity·Community 추출을 수행한다.

설계 원칙:
- 보편 라벨 + doc_type/original_section 2-tier (옵션 C, ADR-0002)
- chunker.Chunk(TypedDict)와 분리: Layer A는 그래프 표현, chunker.Chunk는 평면 청크
- Section 라벨은 W3 Entity 추출 시점에 LLM이 채움 (현재는 Optional)
- ID는 호출자가 부여 (UUID 또는 file hash 기반)
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class DocType(str, Enum):
    """문서 타입 — ADR-0002 §Decision의 4종."""
    REPORT = "report"          # 증권사·연구기관 리포트
    IR = "ir"                  # 기업 자체 IR 자료
    DISCLOSURE = "disclosure"  # 정부·감독기관 공시·보도자료
    FILING = "filing"          # 법정 공시 사업보고서


class SectionLabel(str, Enum):
    """Section 보편 라벨 8개 — ADR-0002 §Decision."""
    OVERVIEW = "Overview"
    PERFORMANCE = "Performance"
    OUTLOOK = "Outlook"
    RISK = "Risk"
    RECOMMENDATION = "Recommendation"
    BUSINESS_SEGMENT = "BusinessSegment"
    STATISTICS = "Statistics"
    DISCLAIMER = "Disclaimer"


class ChunkType(str, Enum):
    """Chunk 종류 — chunker.py의 chunk_type과 1:1."""
    TEXT = "text"
    TABLE = "table"


class SourceFormat(str, Enum):
    """원본 파일 포맷."""
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    HWP = "hwp"
    HWPX = "hwpx"


@dataclass
class Chunk:
    """
    Layer A의 Chunk 노드 — LLM 입력 단위.

    chunker.chunk()의 Chunk(TypedDict) 결과를 1:1로 변환받아 생성된다.
    회사 레포 chunk 결과의 `section` 문자열은 부모 Section 노드의
    `original_section` 속성으로 보존되고, 본 객체는 텍스트와 위치만 담는다.

    Cypher 매핑 (doc-ontology.md §3.3):
        (:Chunk {id, text, chunk_type, char_count, page, order_index})
    """
    id: str
    text: str
    chunk_type: ChunkType
    char_count: int
    page: Optional[int] = None
    order_index: int = 0

    # chunker.py가 추출한 메타데이터 (Layer B Entity 추출 힌트로 활용)
    doc_year: Optional[str] = None
    section_type_hint: Optional[str] = None  # chunker의 정규식 분류 결과 ("실적"/"리스크"/"전망")
    metric_keywords: list[str] = field(default_factory=list)


@dataclass
class Table:
    """
    Layer A의 Table 노드 — 표 데이터 명시 노드.

    chunker.py가 chunk_type="table"로 분류한 청크는 본 노드로 변환된다.
    Layer B에서 셀 단위 Metric 추출의 입력이 된다.

    Cypher 매핑 (doc-ontology.md §3.4):
        (:Table {id, raw_markdown, caption, row_count, column_count, page})
    """
    id: str
    raw_markdown: str
    row_count: int = 0
    column_count: int = 0
    caption: Optional[str] = None
    page: Optional[int] = None
    order_index: int = 0


@dataclass
class Section:
    """
    Layer A의 Section 노드 — 보편 라벨 + 원본 보존 (옵션 C).

    label은 W3 Entity 추출 시 LLM이 채울 예정이라 현재 Optional.
    원본 chunker.py 결과의 `section: str`은 그대로 `original_section`에 보존된다.

    Cypher 매핑 (doc-ontology.md §3.2):
        (:Section {id, label, doc_type, original_section, heading_level, ...})
    """
    id: str
    original_section: str           # 원본 섹션명 그대로 (예: "1Q 2025 Key Highlights")
    doc_type: DocType               # 부모 Document의 doc_type 복사
    label: Optional[SectionLabel] = None  # W3에서 LLM이 채움
    heading_level: int = 1          # 1=h1, 2=h2, 3=h3
    order_index: int = 0            # 문서 내 순서
    page_start: Optional[int] = None
    page_end: Optional[int] = None

    chunks: list[Chunk] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    subsections: list["Section"] = field(default_factory=list)


@dataclass
class Document:
    """
    Layer A의 Document 노드 — 업로드된 파일 1개 = 1노드.

    Cypher 매핑 (doc-ontology.md §3.1):
        (:Document {id, filename, doc_type, source_format, publisher, ...})
    """
    id: str
    filename: str
    source_format: SourceFormat
    doc_type: DocType
    total_pages: int = 0

    publisher: Optional[str] = None       # 발행 기관 (W3 메타 추출 시 채움)
    subject: Optional[str] = None         # 주제 (분석 대상 회사명, IR이면 자사명)
    fiscal_year: Optional[int] = None     # 회계연도 (표지 명시 추출)
    published_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None

    sections: list[Section] = field(default_factory=list)
