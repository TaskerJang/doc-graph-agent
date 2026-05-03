"""
doc-graph-agent의 인제스트 모듈.

회사 레포 doc-summary-agent의 인제스트 자산(doc_parser/, chunker/)을
그대로 차용하고 Layer A 어댑터를 얹은 구조. 자세한 설계 의도는
`docs/ontology/doc-ontology.md`와 ADR-0002 참고.

Public API:
    parse_document(path) -> Document   # 단일 진입점 (chunker 의존성 필요)
    Document, Section, Chunk, Table    # Layer A 노드 dataclass (의존성 불필요)
    DocType, SectionLabel              # enum

`adapter`/`chunker`/`doc_parser`는 langchain·pymupdf 등 무거운 의존성이 필요해
의존성 미설치 환경에서도 `from ingestion.models import ...`만큼은 가능하도록
adapter import는 lazy하게 처리한다.
"""
from ingestion.models import (
    Chunk,
    ChunkType,
    Document,
    DocType,
    Section,
    SectionLabel,
    SourceFormat,
    Table,
)

# adapter는 chunker → langchain 의존성을 끌고 들어오므로 lazy import
try:
    from ingestion.adapter import chunks_to_layer_a, parse_document
    _ADAPTER_AVAILABLE = True
except ImportError:
    _ADAPTER_AVAILABLE = False

    def parse_document(*args, **kwargs):  # type: ignore[no-redef]
        raise ImportError(
            "parse_document 사용에는 추가 의존성이 필요합니다. "
            "ingestion/README.md의 'uv add' 모음을 참고하세요."
        )

    def chunks_to_layer_a(*args, **kwargs):  # type: ignore[no-redef]
        raise ImportError(
            "chunks_to_layer_a 사용에는 추가 의존성이 필요합니다. "
            "ingestion/README.md의 'uv add' 모음을 참고하세요."
        )


__all__ = [
    "parse_document",
    "chunks_to_layer_a",
    "Document",
    "Section",
    "Chunk",
    "Table",
    "DocType",
    "SectionLabel",
    "ChunkType",
    "SourceFormat",
]
