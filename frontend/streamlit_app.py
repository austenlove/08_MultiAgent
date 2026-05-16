"""Streamlit UI for 08_MultiAgent — Integrated (Monolith) Version.

요구사항 6 반영:
- 내부 검증 실패 시 명시적 경고
- 평가/실행 이력 가독성 개선
- DocReport 카드 뷰 + JSON 뷰 + .json 다운로드
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

# 프로젝트 루트를 path 에 추가 (backend 패키지 import 용)
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

import streamlit as st
from dotenv import load_dotenv

from backend.app import reports as reports_store
from backend.app.config import settings
from backend.app.orchestrator import run_pipeline
from backend.app.schemas import ChatMessage

load_dotenv()

try:
    import pdfplumber
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

try:
    from docx import Document as DocxDocument
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False


st.set_page_config(
    page_title="MultiAgent 기술문서 분석 봇",
    page_icon="🤖",
    layout="wide",
)

# Black & white theme + 검증 경고용 스타일
st.markdown(
    """
<style>
/* 1. Global Reset - Light Theme Only */
.stApp {
    background-color: #FFFFFF !important;
}

/* 2. Global Text Colors */
body, .stApp, .stMarkdown, p, span, label, li, small {
    color: #1A1A1A !important;
}

/* 3. Heading Colors */
h1, h2, h3, h4, h5, h6, [data-testid="stHeader"], [data-testid="stSubheader"] {
    color: #000000 !important;
}

/* 4. Sidebar Styles */
[data-testid="stSidebar"] {
    background-color: #F8F9FA !important;
    border-right: 1px solid #E0E0E0 !important;
}
[data-testid="stSidebar"] * {
    color: #1A1A1A !important;
}

/* 5. Button Styles (Black with White Text) */
.stButton > button {
    background-color: #000000 !important;
    color: #FFFFFF !important;
    border-radius: 8px !important;
    border: none !important;
    width: 100%;
}
.stButton > button * {
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}
.stButton > button:hover {
    background-color: #333333 !important;
}

/* 6. Input & Chat Visibility */
input, textarea, [data-testid="stChatInput"] textarea {
    background-color: #FFFFFF !important;
    color: #1A1A1A !important;
    -webkit-text-fill-color: #1A1A1A !important;
}
[data-testid="stChatInput"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E0E0E0 !important;
    border-radius: 12px !important;
}
[data-testid="stChatMessage"] {
    background-color: #F7F9FB !important;
    border: 1px solid #E9EDF1 !important;
}
[data-testid="stChatMessage"] * {
    color: #1A1A1A !important;
}

/* Tabs styling */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
}
.stTabs [data-baseweb="tab-list"] button {
    background-color: #F1F3F5 !important;
    border-radius: 8px 8px 0 0 !important;
    color: #495057 !important;
    padding: 8px 16px !important;
}
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
    background-color: #FFFFFF !important;
    color: #000000 !important;
    border-bottom: 2px solid #000000 !important;
}

/* Tables */
table { width: 100%; border-collapse: collapse; margin: 1.5rem 0; border-radius: 8px; overflow: hidden; }
th { background: #000000 !important; color: #FFFFFF !important; padding: 14px; text-align: left; }
td { padding: 12px; border: 1px solid #F0F0F0; color: #333333 !important; }
tr:nth-child(even) { background-color: #FAFAFA; }

/* Badges & Alerts */
.validation-warn { background: #FFF9C4; border-left: 4px solid #FBC02D; padding: 12px 16px; border-radius: 8px; margin: 12px 0; color: #5D4037 !important; }
.validation-ok { background: #E8F5E9; border-left: 4px solid #43A047; padding: 12px 16px; border-radius: 8px; margin: 12px 0; color: #1B5E20 !important; }
.history-row { padding: 10px; border-bottom: 1px solid #F0F0F0; transition: background 0.2s; }
.history-row:hover { background: #F8F9FA; }
.badge-pass { background: #43A047; color: #FFFFFF; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
.badge-fail { background: #E53935; color: #FFFFFF; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
.badge-info { background: #546E7A; color: #FFFFFF; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }

/* Sidebar user info - text style */
.sidebar-user { color: #1A1A1A !important; padding: 10px 5px; margin-bottom: 10px; font-size: 1.1rem; border-bottom: 1px solid #E0E0E0; }
.sidebar-user b { color: #000000; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #F1F1F1; }
::-webkit-scrollbar-thumb { background: #888888; border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: #555555; }
</style>
""",
    unsafe_allow_html=True,
)


# ── 세션 상태 ───────────────────────────────────────────────────────────────
def _init_state() -> None:
    st.session_state.setdefault("token", None)
    st.session_state.setdefault("username", None)
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("last_response", None)
    st.session_state.setdefault("uploaded_document", None)
    st.session_state.setdefault("uploaded_filename", None)
    # 평가/분석 이력: [{id, document_title, created_at, validation_passed, attempts}]
    st.session_state.setdefault("history_list", [])


_init_state()


# ── 로그인 화면 ─────────────────────────────────────────────────────────────
def render_login() -> None:
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.write("")
        st.write("")
        st.title("🤖 MultiAgent 기술문서 분석 봇")
        st.caption("멀티에이전트(Planner·Researcher·Analyst·Validator·Writer) 가 협업합니다.")

        with st.form("login_form"):
            u = st.text_input("아이디")
            p = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("로그인", use_container_width=True)

        if submitted:
            if u == settings.admin_username and p == settings.admin_password:
                st.session_state.token = "integrated-session"
                st.session_state.username = u
                _refresh_history()
                st.success("로그인 성공")
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")


# ── 헬퍼들 ──────────────────────────────────────────────────────────────────
def _extract_text(file) -> str:
    name = file.name.lower()
    if name.endswith(".pdf") and _PDF_AVAILABLE:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            return "\n".join([page.extract_text() or "" for page in pdf.pages])
    if name.endswith(".docx") and _DOCX_AVAILABLE:
        doc = DocxDocument(io.BytesIO(file.read()))
        return "\n".join(p.text for p in doc.paragraphs)
    return file.read().decode("utf-8", errors="ignore")


def _refresh_history() -> None:
    """디스크에 저장된 분석 결과 목록을 다시 읽어 사이드바에 반영."""
    try:
        st.session_state.history_list = [
            s.model_dump() for s in reports_store.list_reports(limit=20)
        ]
    except Exception:
        st.session_state.history_list = []


def _to_response_dict(resp) -> dict:
    return resp.model_dump() if hasattr(resp, "model_dump") else (resp or {})


# ── 검증 결과 표시 ──────────────────────────────────────────────────────────
def _render_validation(validation: dict | None) -> None:
    if not validation:
        st.caption("이 메시지는 검증 단계를 거치지 않았습니다 (chat 모드).")
        return

    passed = bool(validation.get("passed"))
    summary = validation.get("summary", "")
    attempts = validation.get("attempts", 1)

    if passed:
        st.markdown(
            f"<div class='validation-ok'>✅ <b>검증 통과</b> · {summary} · 시도 {attempts}회</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div class='validation-warn'>⚠️ <b>내부 검증 실패</b> · {summary} · 시도 {attempts}회</div>",
            unsafe_allow_html=True,
        )
        issues = validation.get("issues") or []
        if issues:
            with st.expander("실패한 항목 자세히 보기", expanded=False):
                for i in issues:
                    st.markdown(f"- {i}")

    code_checks = validation.get("code_checks") or []
    llm_judgments = validation.get("llm_judgments") or []

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**🧪 코드 규칙 검증**")
        for c in code_checks:
            badge_cls = "badge-pass" if c["status"] == "pass" else "badge-fail" if c["status"] == "fail" else "badge-info"
            st.markdown(
                f"<div class='history-row'>"
                f"<span class='{badge_cls}'>{c['status']}</span> "
                f"<code>{c['name']}</code> "
                f"<small>{c.get('actual') or ''} / 기준 {c.get('threshold') or ''}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )
    with col_b:
        st.markdown("**🧠 LLM 판단**")
        if not llm_judgments:
            st.caption("코드 검증 실패로 LLM 판단을 생략했거나 chat 모드입니다.")
        for j in llm_judgments:
            badge_cls = "badge-pass" if j["status"] == "pass" else "badge-fail" if j["status"] == "fail" else "badge-info"
            st.markdown(
                f"<div class='history-row'>"
                f"<span class='{badge_cls}'>{j['status']}</span> "
                f"<code>{j['name']}</code> "
                f"<small>score={j.get('score', 0):.2f} · {(j.get('reason') or '')[:120]}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ── DocReport 카드/JSON/다운로드 ────────────────────────────────────────────
def _render_doc_report(resp: dict) -> None:
    report = resp.get("doc_report")
    report_id = resp.get("report_id")
    if not report:
        st.caption("이번 응답에는 분석 리포트(DocReport)가 포함되지 않았습니다.")
        return

    tab_card, tab_json, tab_download = st.tabs(["📑 카드 뷰", "🧾 JSON 뷰", "⬇️ 다운로드"])

    with tab_card:
        st.markdown(f"### {report['document_title']}")
        st.markdown("**전체 요약**")
        st.info(report["overall_summary"])

        if report.get("sections"):
            st.markdown("#### 🔍 섹션별 분석")
            for s in report["sections"]:
                with st.expander(f"📌 {s['title']}", expanded=True):
                    st.write(s["summary"])
                    if s.get("key_points"):
                        st.markdown("\n".join(f"- {p}" for p in s["key_points"]))

        if report.get("qa_pairs"):
            st.markdown("#### ❓ Q&A")
            for qa in report["qa_pairs"]:
                st.markdown(f"**Q: {qa['question']}**")
                st.markdown(f"A: {qa['answer']}")
                st.divider()

        if report.get("keywords"):
            st.markdown("#### 🏷️ 핵심 키워드")
            st.write(", ".join(report["keywords"]))

        refs = report.get("references") or []
        if refs:
            st.markdown(f"**참고 자료**: {', '.join(refs)}")

    with tab_json:
        st.json(report)

    with tab_download:
        st.write("아래 버튼으로 분석 결과 전체(JSON)를 다운로드할 수 있습니다.")
        payload = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            label="📥 DocReport JSON 다운로드",
            data=payload,
            file_name=f"doc_report_{report_id or 'latest'}.json",
            mime="application/json",
            use_container_width=True,
        )
        if report_id:
            st.caption(f"서버 저장 ID: `{report_id}`")


# ── 에이전트 trace 표시 ─────────────────────────────────────────────────────
def _render_trace(resp: dict) -> None:
    trace = resp.get("agent_trace") or []
    if not trace:
        st.info("에이전트 실행 기록이 없습니다.")
        return
    for i, step in enumerate(trace, 1):
        badge = {
            "ok": "badge-pass",
            "error": "badge-fail",
            "retry": "badge-info",
            "skipped": "badge-info",
        }.get(step.get("status"), "badge-info")
        with st.expander(
            f"#{i} {step['agent']} · {step['status']} · {step.get('detail','')}",
            expanded=False,
        ):
            st.markdown(
                f"<span class='{badge}'>{step['status']}</span> "
                f"<code>{step['agent']}</code>",
                unsafe_allow_html=True,
            )
            preview = step.get("payload_preview")
            if preview:
                st.code(preview, language="text")


# ── 사이드바: 분석 이력 ──────────────────────────────────────────────────────
def _render_history_sidebar() -> None:
    st.markdown("### 📚 분석 이력")
    if st.button("🔄 새로고침", use_container_width=True):
        _refresh_history()
        st.rerun()

    items = st.session_state.history_list or []
    if not items:
        st.caption("아직 저장된 분석 결과가 없습니다.")
        return

    for item in items:
        passed = item.get("validation_passed")
        badge = "✅" if passed else "⚠️"
        title = (item.get("document_title") or "(제목 없음)")[:32]
        created = (item.get("created_at") or "")[:19].replace("T", " ")
        st.markdown(
            f"<div class='history-row'>"
            f"<small>{badge} <code>{item['id']}</code> · {created}</small><br>"
            f"<b>{title}</b> · 시도 {item.get('attempts', 1)}회"
            f"</div>",
            unsafe_allow_html=True,
        )
        col_l, col_r = st.columns([1, 1])
        with col_l:
            if st.button("불러오기", key=f"load_{item['id']}", use_container_width=True):
                record = reports_store.get_report(item["id"])
                if record is None:
                    st.toast("해당 리포트를 찾을 수 없습니다.", icon="⚠️")
                else:
                    st.session_state.last_response = {
                        "reply": f"📚 저장된 분석 ({item['id']}) 을 불러왔습니다.",
                        "complete": True,
                        "doc_report": record.doc_report.model_dump(),
                        "validation_result": record.validation_result.model_dump()
                        if record.validation_result
                        else None,
                        "agent_trace": [],
                        "report_id": record.id,
                    }
                    st.rerun()
        with col_r:
            path = reports_store.report_path(item["id"])
            if path and path.exists():
                st.download_button(
                    label="JSON",
                    data=path.read_bytes(),
                    file_name=f"doc_report_{item['id']}.json",
                    mime="application/json",
                    key=f"dl_{item['id']}",
                    use_container_width=True,
                )


# ── 메인 채팅 화면 ─────────────────────────────────────────────────────────
def render_chat() -> None:
    # ── 사이드바 ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f"<div class='sidebar-user'>👤 <b>{st.session_state.username}</b>님, 환영합니다</div>",
            unsafe_allow_html=True
        )
        if st.button("로그아웃", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        if st.button("💬 대화 초기화", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_response = None
            st.rerun()

        st.divider()
        _render_history_sidebar()

    # ── 메인 영역 ─────────────────────────────────────────────────────────────
    st.markdown("## 🤖 MultiAgent 기술문서 분석 서비스")
    
    # 50:50 레이아웃 분할
    col_left, col_right = st.columns([1, 1], gap="medium")

    # [좌측] 문서 업로드 및 분석 결과
    with col_left:
        st.subheader("📄 문서 관리 및 분석")
        
        with st.container(border=True):
            uploaded_file = st.file_uploader(
                "분석할 TXT / PDF / DOCX 파일을 선택하세요",
                type=["txt", "pdf", "docx"],
                key="doc_uploader",
                label_visibility="collapsed"
            )
            
            if uploaded_file is not None and uploaded_file.name != st.session_state.uploaded_filename:
                with st.spinner("문서에서 텍스트를 추출하고 분석 중입니다..."):
                    text = _extract_text(uploaded_file)
                    st.session_state.uploaded_document = text
                    st.session_state.uploaded_filename = uploaded_file.name
                    
                    # 자동 요약 프롬프트 실행
                    summary_prompt = (
                        f"새로 업로드된 문서 '{uploaded_file.name}' 의 주요 구성과 핵심 내용을 "
                        "표(Table) 형태로 정리해서 알려줘."
                    )
                    response = run_pipeline(
                        user_message=summary_prompt,
                        history=[ChatMessage(**m) for m in st.session_state.messages if m["role"] in {"user", "assistant"}],
                        uploaded_document=text,
                        user=st.session_state.username,
                    )
                    st.session_state.messages.append({"role": "user", "content": f"📎 문서 업로드: {uploaded_file.name}"})
                    st.session_state.messages.append({"role": "assistant", "content": response.reply})
                    st.session_state.last_response = _to_response_dict(response)
                    _refresh_history()
                    st.rerun()

            if st.session_state.uploaded_filename:
                st.success(f"📎 현재 문서: **{st.session_state.uploaded_filename}**")
                if st.button("🗑️ 문서 제거", use_container_width=True):
                    st.session_state.uploaded_document = None
                    st.session_state.uploaded_filename = None
                    st.rerun()
            else:
                st.info("왼쪽 상단의 업로드 버튼을 통해 문서를 추가하세요.")

        st.divider()
        
        # 분석 결과 탭 (좌측 배치)
        resp = st.session_state.last_response or {}
        tab_report, tab_validation, tab_trace = st.tabs(
            ["📋 분석 리포트", "✅ 검증 결과", "🛠️ 에이전트 Trace"]
        )
        with tab_report:
            _render_doc_report(resp)
        with tab_validation:
            _render_validation(resp.get("validation_result"))
        with tab_trace:
            _render_trace(resp)

    # [우측] 채팅 인터페이스
    with col_right:
        st.subheader("💬 실시간 대화")
        
        # 채팅 내역 표시 영역 (스크롤 가능하도록 컨테이너 사용)
        chat_container = st.container(height=650)
        
        # 1. 기존 메시지 렌더링 (루프)
        with chat_container:
            for m in st.session_state.messages:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"], unsafe_allow_html=True)

        # 2. 채팅 입력창 (항상 하단에 위치)
        if prompt := st.chat_input("문서에 대해 궁금한 점을 물어보세요"):
            # 사용자 메시지 즉시 표시
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)
                
                # 어시스턴트 응답 생성 및 표시
                with st.chat_message("assistant"):
                    with st.spinner("멀티에이전트가 답변을 준비 중입니다..."):
                        # 세션에 메시지 선행 추가 (히스토리 포함용)
                        st.session_state.messages.append({"role": "user", "content": prompt})
                        
                        history_objs = [
                            ChatMessage(**m)
                            for m in st.session_state.messages[:-1]
                            if m["role"] in {"user", "assistant"}
                        ]
                        
                        try:
                            response = run_pipeline(
                                user_message=prompt,
                                history=history_objs,
                                uploaded_document=st.session_state.get("uploaded_document"),
                                user=st.session_state.username,
                            )
                            # AI 응답 내의 <br> 태그 등이 잘 렌더링되도록 처리
                            st.markdown(response.reply, unsafe_allow_html=True)
                            st.session_state.messages.append(
                                {"role": "assistant", "content": response.reply}
                            )
                            st.session_state.last_response = _to_response_dict(response)
                            
                            if response.validation_result and not response.validation_result.passed:
                                st.warning("⚠️ 내부 검증이 일부 통과하지 못했습니다. 좌측 패널을 확인하세요.")
                            
                            _refresh_history()
                        except Exception as e:
                            err_msg = f"에러가 발생했습니다: {str(e)}"
                            st.error(err_msg)
                            st.session_state.messages.append({"role": "assistant", "content": f"❌ {err_msg}"})
            
            # 렌더링 완료 후 상태 반영을 위해 재실행 (메시지 리스트 동기화)
            st.rerun()


# ── 진입점 ────────────────────────────────────────────────────────────────
if not st.session_state.token:
    render_login()
else:
    render_chat()
