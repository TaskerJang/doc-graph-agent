# 1. 작업 (Task)

아래 문서 청크를 읽고 **Layer B Entity (5타입)** 와 **Relation (4타입)** 을 추출하여 JSON 으로 반환하세요.

# 2. 입력

문서ID: {doc_id}
섹션: {section}

청크 내용:
```
{text}
```

# 3. 제약사항 (Constraints)

## 3.1 Entity 추출
- 동일 Entity 가 청크 내 여러 번 등장해도 **1번만** 추출 (NED 는 다음 단계 #14 에서 처리).
- 각 Entity 에 청크 내 고유 `local_id` 부여 (예: `"ent_001"`, `"ent_002"` ...).
- `source_span` 은 원문 인용. `canonical` 은 정규화된 이름 (Metric 의 경우 통합 표현).
- `section` 필드는 입력 섹션명을 그대로 복사.

## 3.2 Relation 추출
- `source` 와 `target` 은 **본 청크에서 추출한 Entity 의 `local_id`** 여야 함.
- 청크 외부 Entity 참조 금지 (예: 다른 청크에서 추출했을 법한 ID 추측 금지).
- `evidence` 는 관계의 근거가 된 원문 1~2 문장.

## 3.3 빈 결과
- 청크에 추출 가능한 Entity 가 없으면 `entities` 와 `relations` 모두 빈 배열로 반환.
- 면책고지·법적고지·광고성 문구 청크도 빈 배열로 반환.

# 4. Few-shot 예시 (Spike v0 결함을 v1 에서 어떻게 고치는가)

## 4.1 입력

```
두산밥캣은 2024년 3분기 영업이익이 전년 동기 대비 35% 감소했다고 공시했다.
북미 시장의 고금리 장기화로 건설장비 수요가 둔화된 것이 주된 원인이다.
```

## 4.2 ❌ Spike v0 가 했던 잘못 (피할 것)

- Metric 을 분해: `["영업이익"]` + `["35% 감소"]` (2개로 쪼갬)
- "건설장비 수요 둔화" 를 `Outlook` 으로 분류 (현재 진행 중인 Risk 임)
- Relation 자체를 추출하지 않음

## 4.3 ✅ v1 이 해야 할 일

```json
{{
  "entities": [
    {{
      "local_id": "ent_001",
      "type": "Company",
      "canonical": "두산밥캣",
      "source_span": "두산밥캣",
      "section": "{section}"
    }},
    {{
      "local_id": "ent_002",
      "type": "Metric",
      "canonical": "영업이익 전년 동기 대비 35% 감소 (2024Q3)",
      "source_span": "2024년 3분기 영업이익이 전년 동기 대비 35% 감소",
      "section": "{section}"
    }},
    {{
      "local_id": "ent_003",
      "type": "Risk",
      "canonical": "북미 고금리 장기화에 따른 건설장비 수요 둔화",
      "source_span": "북미 시장의 고금리 장기화로 건설장비 수요가 둔화된 것",
      "section": "{section}"
    }}
  ],
  "relations": [
    {{
      "source": "ent_001",
      "type": "HAS_METRIC",
      "target": "ent_002",
      "evidence": "두산밥캣은 2024년 3분기 영업이익이 전년 동기 대비 35% 감소했다고 공시했다"
    }},
    {{
      "source": "ent_001",
      "type": "FACES_RISK",
      "target": "ent_003",
      "evidence": "북미 시장의 고금리 장기화로 건설장비 수요가 둔화된 것이 주된 원인이다"
    }}
  ]
}}
```

## 4.4 v0 → v1 의 4가지 개선점

1. **Metric 통합**: 지표명+값+기간을 하나로 (`ent_002`)
2. **Risk 정확 분류**: 현재 진행 = Risk (Outlook 아님)
3. **Relation 명시**: HAS_METRIC, FACES_RISK 두 관계 추출
4. **source_span**: 원문 그대로 인용 (canonical 과 분리)

# 5. 출력 형식 (Output)

JSON 만 반환. 다른 텍스트 일체 금지:

```json
{{
  "entities": [...],
  "relations": [...]
}}
```
