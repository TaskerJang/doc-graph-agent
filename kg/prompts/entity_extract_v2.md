# 1. Task

아래 청크에서 system 규칙에 정의된 **Entity(5 타입)** 와 **Relation(4 타입)** 을 추출해,
system `<output_contract>` 의 스키마를 정확히 따르는 **JSON 객체 1개**로만 반환하세요.

# 2. Input

문서ID: {doc_id}
섹션: {section}

청크 내용 (--- 구분선 사이) :
---
{text}
---

# 3. Reminder (system 규칙의 압축 재확인)

- JSON 객체 1개만 출력. 마크다운 코드펜스·머리말·설명·주석 금지. 첫 글자 '{{', 끝 글자 '}}'.
- `source_span` 은 원문 그대로 인용. 수치(금액·비율·날짜) 변환·반올림 금지.
- `Metric` 은 이름+값+기간을 하나로 통합. 쪼개지 말 것.
- **표 데이터 셀 값을 `Company` 로 만들지 말 것.** 실재하는 기업·종목명만 `Company`.
- 명백히 존재하는 Entity 누락 금지 ↔ 동시에 없는 것 날조 금지 (둘 다 오류).
- 5개 타입에 명확히 안 맞으면 생략. 질문하지 말 것.
- 각 Entity 의 `section` 필드엔 위 섹션값 "{section}" 을 그대로 넣을 것.
- 추출 대상이 없으면 {{"entities": [], "relations": []}} 반환.
