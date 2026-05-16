# 08_MultiAgent 평가 모듈

멀티에이전트 파이프라인의 결과를 정량 측정한다.
요구사항 2에 따라 평가 항목을 **코드 검증**과 **LLM 판단** 두 그룹으로 명확히 분리한다.

## 1. 평가 항목

### 🧪 Code Checks (LLM 호출 없음)
- `retrieval_precision`: `expected_doc_ids` 중 실제 검색된 출처에 매치된 비율.
- `overall_summary_min_length`, `section_min_count`, `section_key_points_min`,
  `keyword_min_count`, `qa_pairs_min_count`, `references_present`, `no_html_tags`:
  백엔드 `app/agents/validator.py` 의 코드 규칙을 그대로 재사용해 평가와 운영의
  검증 기준을 일치시킨다.

### 🧠 LLM Judgments
- `faithfulness`: 생성된 답변이 컨텍스트에 충실한가 (0~1).
- `requirement_coverage`: 사용자의 요구사항이 답변에 반영되었는가 (0~1).

`overall_score` 는 두 그룹 평균의 평균(보조 지표)이며,
주된 의사결정은 그룹별 평균과 항목별 통과율로 한다.

## 2. 사용법

```bash
# 프로젝트 루트에서
python -m evaluation.runner
```

결과는 `evaluation/reports/report_<timestamp>.{json,md}` 으로 저장된다.

## 3. 테스트 케이스 작성

```json
{
  "id": "TC-001",
  "query": "질문",
  "expected_doc_ids": ["기대_파일명.pdf"],
  "requirements": ["반드시 포함될 내용"],
  "uploaded_document": null
}
```

`uploaded_document` 에 텍스트를 넣으면, 사전 업로드된 문서가 있는 시나리오를
재현할 수 있다.
