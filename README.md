# 08_MultiAgent

`07_SingleAgent` 의 단일 ReAct 에이전트 구조를 **5단계 멀티에이전트 파이프라인**으로 전환한 프로젝트.

```
사용자 메시지
   ↓
[Planner] → mode/검색 필요 여부 결정 (JSON)
   ↓
[Researcher] → RAG + 웹 검색 → context_summary
   ↓
[Analyst]  → DocReport 생성 (structured output)
   ↓
[Validator] ─ Code Checks (결정적 규칙)  ──┐
              LLM Judgments (faithfulness, coverage) │
   ↓ pass                                          │
                                       ↓ fail (재시도 N회)
[Writer] → 최종 사용자 답변 마크다운 ←─────┘
```

## 구조

```
08_MultiAgent/
├── backend/
│   ├── app/
│   │   ├── main.py                  FastAPI (/auth, /chat, /reports*)
│   │   ├── orchestrator.py          5단계 파이프라인 + 검증 재시도
│   │   ├── reports.py               DocReport JSON 저장소
│   │   ├── config.py / auth.py
│   │   ├── retrieval/               요구사항 4 — 공용 검색/임베딩 계층
│   │   │   ├── clients.py           OpenAI / Chroma 싱글톤
│   │   │   ├── hybrid.py            Dense + BM25 + RRF + Rerank
│   │   │   └── web.py               Tavily 호출 helper
│   │   ├── agents/                  서브 에이전트들
│   │   │   ├── base.py              load_prompt + chat_completion
│   │   │   ├── planner.py
│   │   │   ├── researcher.py
│   │   │   ├── analyst.py
│   │   │   ├── validator.py         CodeChecks + LLMJudgments 분리
│   │   │   └── writer.py
│   │   └── schemas/                 chat / doc_report / validation / reports …
│   ├── prompts/                     요구사항 1 — 에이전트별 .txt 분리
│   │   ├── planner.txt
│   │   ├── researcher.txt
│   │   ├── analyst.txt
│   │   ├── validator.txt
│   │   └── writer.txt
│   ├── data/
│   │   ├── chroma_db/ bm25_index.pkl
│   │   ├── static/                  정적 참고 문서
│   │   └── reports/                 DocReport JSON 영속화
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── streamlit_app.py             요구사항 6 — 검증 경고/이력/카드·JSON·다운로드
│   ├── .streamlit/config.toml
│   └── requirements.txt
├── evaluation/                      요구사항 2 — Code/LLM 스키마 분리
│   ├── schemas.py
│   ├── evaluators.py
│   ├── runner.py
│   ├── test_cases.json
│   └── README.md
├── docker/docker-compose.yml        요구사항 7 — prompts/, reports/ 마운트
├── .env.example
└── README.md
```

## API

| Method | Path | 설명 |
| --- | --- | --- |
| GET  | `/health` | 라이브니스 + 활성 에이전트 목록 |
| POST | `/auth/login` | `{username, password}` → JWT |
| GET  | `/auth/verify` | Bearer 토큰 검증 |
| POST | `/chat` | 5단계 파이프라인 실행 |
| GET  | `/reports?limit=50` | 저장된 DocReport 목록 (요약) |
| GET  | `/reports/{id}` | 단일 DocReport 전체 |
| GET  | `/reports/{id}/download` | `.json` 파일 다운로드 |

### `/chat` 응답 예시

```json
{
  "reply": "...최종 마크다운 답변...",
  "complete": true,
  "doc_report": { "document_title": "...", "sections": [...], "...": "..." },
  "validation_result": {
    "passed": true,
    "code_checks": [
      { "name": "overall_summary_min_length", "status": "pass", "threshold": ">= 50자", "actual": "182자", "detail": "" }
    ],
    "llm_judgments": [
      { "name": "faithfulness", "status": "pass", "score": 0.85, "reason": "...", "passed_threshold": 0.7 }
    ],
    "summary": "모든 코드 규칙과 LLM 판단을 통과했습니다.",
    "issues": [],
    "attempts": 1
  },
  "agent_trace": [
    { "agent": "planner", "status": "ok", "detail": "mode=analysis need_rag=true ..." },
    { "agent": "researcher", "status": "ok", "detail": "rag=5 web=0" },
    { "agent": "analyst", "status": "ok", "detail": "attempt=1 sections=4 qa=3" },
    { "agent": "validator", "status": "ok", "detail": "모든 코드 규칙과 LLM 판단을 통과했습니다." },
    { "agent": "writer", "status": "ok", "detail": "analysis reply" }
  ],
  "report_id": "a1b2c3d4e5f6"
}
```

## 환경 변수

`.env.example` 참조. **필수**:
- `OPENAI_API_KEY`, `TAVILY_API_KEY`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`

선택값: `JWT_SECRET`, `MAX_VALIDATION_RETRIES`(기본 2), `MAX_RESEARCH_QUERIES`(기본 3),
`CHAT_MODEL`, `EMBEDDING_MODEL`, `REPORTS_PATH` 등.

## 로컬 실행

```powershell
# 백엔드
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example ..\.env  # 키 채우기
uvicorn app.main:app --reload --port 8000

# 프론트엔드 (별도 터미널)
cd frontend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run streamlit_app.py
```

> 통합형 Streamlit 앱은 백엔드 모듈을 직접 import 합니다.
> 분리형으로 배포하려면 Streamlit 에서 `BACKEND_URL` 을 통해 호출하도록 분기 추가.

## Docker

```powershell
copy .env.example .env  # 키 채우기
docker compose -f docker/docker-compose.yml up -d --build
# → http://localhost:8000/health
```

`backend/prompts/` 는 read-only 로 마운트되므로, **컨테이너 재빌드 없이**
에이전트 시스템 프롬프트만 수정해 재시작할 수 있습니다 (요구사항 1).

## 평가

```powershell
python -m evaluation.runner
```

`evaluation/reports/` 에 코드 검증 통과율과 LLM 판단 평균을
**별도로** 표시하는 JSON/Markdown 리포트가 생성됩니다.

## 07_SingleAgent 와 비교

| 항목 | 07_SingleAgent | 08_MultiAgent |
| --- | --- | --- |
| 에이전트 구조 | 단일 ReAct + tool registry | 5단계 파이프라인 (Planner→Researcher→Analyst→Validator→Writer) |
| 시스템 프롬프트 | `prompts/system_prompt.txt` 1개 | 에이전트별 5개 `.txt` (요구사항 1) |
| 검증 | 없음 | CodeChecks + LLMJudgments + 재시도 루프 (요구사항 3) |
| 검색 계층 | `retriever.py` 단일 파일 | `retrieval/` 패키지로 client/hybrid/web 분리 (요구사항 4) |
| 결과 저장 | 메모리 | `/reports/*` API + 디스크 JSON (요구사항 5) |
| Streamlit | 카드뷰 | 카드 + JSON + 다운로드 + 이력 + 검증 경고 (요구사항 6) |
| Docker | data 마운트 | data + reports + prompts(ro) 마운트 (요구사항 7) |
| 평가 | 혼합 score | Code/LLM 그룹 분리, 항목별 통과율/평균 (요구사항 2) |
