# ingestion/

**책임**: 문서 파싱 + 전처리 + 청킹 + Entity 추출 입력 정규화.

**출처**: 기존 [`doc-summary-agent`](https://github.com/TaskerJang/doc-summary-agent)의 `doc_parser/` + `chunker/` 포팅 + 확장.

## 모듈 (예정)

- `parser.py` — PDF/DOCX/HWP 파싱 (기존 `doc_parser/parser.py` 포팅)
- `ocr.py` — EasyOCR 캐시 처리 (기존 `doc_parser/ocr_cache.py` 포팅)
- `preprocessor.py` — 노이즈 제거 (기존 `doc_parser/preprocessor.py` 포팅)
- `chunker.py` — 구조 기반 청킹 (기존 `chunker/chunker.py` 포팅)
- `entity_extractor.py` — LLM 기반 엔티티 추출 (신규)

## 변경점

기존 `chunker.py`의 `_extract_doc_year`, `_extract_section_type`, `_extract_metrics` 같은 정규식 기반 메타데이터 추출은 점진적으로 LLM 기반 entity 추출로 대체한다. 단 W3 초기에는 Before 비교를 위해 기존 방식도 유지.
