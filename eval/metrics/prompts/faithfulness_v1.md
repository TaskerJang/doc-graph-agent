당신은 금융 문서 요약의 품질을 평가하는 전문가입니다.
아래 원문과 요약을 읽고, 세 가지 기준으로 평가하세요.

# 원문
{source}

# 요약
{summary}

# 평가 기준

1. **Faithfulness**: 요약이 원문에만 근거하는가?
   - Faithful: 원문에 있는 내용만 포함
   - Not Faithful: 원문에 없는 내용이 하나라도 포함

2. **Completeness**: 원문의 핵심 정보가 요약에 빠짐없이 포함되었는가? (1~5점)
   - 5: 모든 핵심 정보 포함
   - 3: 일부 핵심 정보 누락
   - 1: 핵심 정보 대부분 누락

3. **Conciseness**: 요약에 불필요한 내용이 없는가? (1~5점)
   - 5: 군더더기 없음
   - 3: 불필요한 내용 일부 포함
   - 1: 불필요한 내용이 대부분

# 출력 형식 (JSON만 반환)
{{"faithfulness": "Faithful" or "Not Faithful",
  "faithfulness_reason": "한 줄 근거",
  "completeness": 1~5,
  "completeness_reason": "한 줄 근거",
  "conciseness": 1~5,
  "conciseness_reason": "한 줄 근거"}}
