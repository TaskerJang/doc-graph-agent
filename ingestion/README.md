# ingestion — 문서 인제스트 모듈

회사 레포 [doc-summary-agent](https://github.com/TaskerJang/doc-summary-agent)의
인제스트 자산(`doc_parser/`, `chunker/`)을 그대로 차용하고 Layer A 어댑터를
얹은 모듈. **VectorRAG vs GraphRAG 비교의 정직성**을 위해 인제스트 단계는
회사 레포 코드를 그대로 사용한다.

## 구조

```
ingestion/
├── __init__.py          # parse_document() 진입점
├── adapter.py           # 회사 레포 결과 → Layer A 객체 변환
├── models.py            # Layer A 노드 dataclass (Document, Section, Chunk, Table)
├── chunker.py           # [PORTED] 회사 레포 그대로
└── doc_parser/          # [PORTED] 회사 레포 그대로
    ├── __init__.py
    ├── exceptions.py
    ├── pdf.py
    ├── docx.py
    ├── hwp.py
    ├── metadata.py
    ├── ocr_cache.py
    ├── preprocessor.py
    └── table_extractor.py
```

## 파이프라인

```
파일(.pdf/.docx/.hwp/...)
   │
   ↓  doc_parser.parse(path)
markdown 문자열
   │
   ↓  chunker.chunk(text)
list[Chunk(TypedDict)]  ← 회사 레포와 동일한 평면 청크
   │
   ↓  adapter.chunks_to_layer_a()
Layer A 객체 (Document → Section → Chunk/Table)
```

## 사용법

```python
from pathlib import Path
from ingestion import parse_document

doc = parse_document(Path("eval/dataset/documents/한화투자증권_두산밥캣_기업분석_리포트.pdf"))

print(doc.filename)            # '한화투자증권_두산밥캣_기업분석_리포트.pdf'
print(doc.doc_type)            # DocType.REPORT
print(len(doc.sections))       # 섹션 수
print(doc.sections[0].label)   # None (W3 LLM 추출에서 채워질 예정)
print(doc.sections[0].original_section)  # '# 투자의견 Buy, 목표주가 80,000원 유지'

for sec in doc.sections:
    for c in sec.chunks:
        print(c.id, c.char_count, c.section_type_hint)
```

## chunk 정책

회사 레포 dev 현재 상태(2026-05-03 기준)와 동일:

| 파라미터 | 값 |
|---|---|
| `DEFAULT_CHUNK_SIZE` | 700 |
| `DEFAULT_CHUNK_OVERLAP` | 200 |
| `DEFAULT_MIN_CHUNK_SIZE` | 50 |

이 정책은 변경 금지 — 변경 시 평가 셋 동일성이 깨져 VectorRAG vs GraphRAG
비교 결과의 의미가 약화된다. 변경이 필요하면 ADR로 박제하고 Before
베이스라인을 재측정해야 한다 (이슈 #35 참고).

## 의존성

본 모듈을 사용하려면 다음 의존성을 추가해야 한다.
**pyproject.toml은 PR #29(Spike)에서 별도로 관리**되므로, 본 PR에서는
의존성 파일을 건드리지 않는다. 로컬에서 직접 추가:

```bash
# PDF 처리
uv add pymupdf pymupdf4llm pdfplumber

# DOCX 처리
uv add python-docx docx2python

# OCR (이미지 기반 PDF용)
uv add easyocr numpy

# Chunking
uv add langchain-text-splitters langchain-experimental langchain-community

# 메타데이터·검증
uv add pydantic langdetect

# 옵션 (있으면 좋음, 없어도 fallback 동작)
uv add gmft
```

**외부 도구**:
- `libreoffice` — `.doc` → `.docx` 변환 (시스템에 설치 필요)
- `hwp5html` (pyhwp 패키지) — `.hwp` 처리 (`uv add pyhwp six`)

## 테스트

```bash
# 단위 테스트 (의존성·fixture 없이 실행 가능)
pytest tests/ingestion -v -k "not eval_docs"

# 통합 sanity check (회사 레포 평가 셋 8문서 사용)
set DOC_FIXTURE_DIR=C:\path\to\doc-summary-agent\eval\dataset\documents  # Windows
export DOC_FIXTURE_DIR=/path/to/doc-summary-agent/eval/dataset/documents  # Linux/macOS
pytest tests/ingestion -v
```

`DOC_FIXTURE_DIR`이 없으면 통합 테스트는 자동 skip되어 단위 테스트만 실행된다.

## Layer A 매핑

본 어댑터가 생성하는 객체는 [`docs/ontology/doc-ontology.md`](../docs/ontology/doc-ontology.md) §3
"Layer A 노드 정의"의 Cypher 스키마와 1:1 매핑된다.

| Python 객체 | Cypher 노드 | 비고 |
|---|---|---|
| `Document` | `(:Document)` | filename, doc_type, source_format 등 |
| `Section` | `(:Section)` | label은 W3 LLM 추출에서 채움 |
| `Chunk` | `(:Chunk)` | chunker.py의 평면 chunk와 1:1 |
| `Table` | `(:Table)` | chunk_type='table'인 청크에서 변환 |

## 출처

- 회사 레포 chunker: [doc-summary-agent/chunker/chunker.py](https://github.com/TaskerJang/doc-summary-agent/blob/dev/chunker/chunker.py)
- 회사 레포 doc_parser: [doc-summary-agent/doc_parser/](https://github.com/TaskerJang/doc-summary-agent/tree/dev/doc_parser)
- 평가 셋: [doc-summary-agent/eval/dataset/qa_pairs.json](https://github.com/TaskerJang/doc-summary-agent/blob/dev/eval/dataset/qa_pairs.json) (40 QA, 5종 문서)
- Layer A 설계: [`docs/ontology/doc-ontology.md`](../docs/ontology/doc-ontology.md)
- 옵션 C 결정: [ADR-0002](../docs/adr/0002-section-schema-option-c.md)
- 트래킹 이슈: [#11 W2 인제스트 포팅](https://github.com/TaskerJang/doc-graph-agent/issues/11)
- chunk 정책 재측정 트래킹: [#35 Before 베이스라인 700/200 재측정](https://github.com/TaskerJang/doc-graph-agent/issues/35)

각 포팅된 파일 상단에 `# Ported from ...` 주석으로 출처를 박제했다.
