from __future__ import annotations

from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

from src.finance_copilot.service import answer_finance_question
from src.finance_copilot.validator import FinanceCopilotValidationError

load_dotenv()

def escape_currency_for_markdown(text: str) -> str:
    """Prevent Streamlit Markdown from treating $ currency as LaTeX."""
    return text.replace("$", r"\$")

st.set_page_config(
    page_title="Stratum | Finance Copilot",
    page_icon="💬",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {max-width: 1180px; padding-top: 2.1rem; padding-bottom: 3rem;}
        .stratum-kicker {font-size: .74rem; font-weight: 700; letter-spacing: .10em; color: #667085; margin-bottom: .2rem;}
        .stratum-subtitle {color: #667085; font-size: .98rem; margin-top: -.45rem; margin-bottom: 1.25rem;}
        .scope-card {border: 1px solid #E4E7EC; border-radius: 10px; background: #F9FAFB; padding: 14px 16px; margin-bottom: 1rem;}
        .scope-title {font-size: .76rem; font-weight: 700; letter-spacing: .07em; color: #475467; margin-bottom: 4px;}
        .scope-copy {font-size: .86rem; line-height: 1.45; color: #667085;}
        .source-line {margin-top: .4rem; font-size: .76rem; color: #98A2B3;}
        .status-note {font-size: .80rem; color: #667085; margin-top: .15rem;}
        div[data-testid="stButton"] button {border-radius: 8px;}
    </style>
    """,
    unsafe_allow_html=True,
)

MONTHS = [
    f"{year}-{month:02d}"
    for year in range(2024, 2027)
    for month in range(1, 13)
    if year < 2026 or month <= 6
]
MONTHS = list(reversed(MONTHS))
MONTH_LABELS = {
    value: datetime.strptime(value, "%Y-%m").strftime("%b %Y")
    for value in MONTHS
}

if "finance_copilot_messages" not in st.session_state:
    st.session_state.finance_copilot_messages = []

if "finance_copilot_month" not in st.session_state:
    st.session_state.finance_copilot_month = "2026-06"

if "finance_copilot_pending_question" not in st.session_state:
    st.session_state.finance_copilot_pending_question = None


def reset_conversation() -> None:
    st.session_state.finance_copilot_messages = []
    st.session_state.finance_copilot_pending_question = None


def format_sources(source_metrics: list[str]) -> str:
    if not source_metrics:
        return ""
    labels = []
    for metric in source_metrics:
        if metric in {"nrr_12m", "grr_12m"}:
            labels.append(metric.upper())
        else:
            labels.append(metric.replace("_", " ").title())
    return " • ".join(labels)


def render_assistant_message(message: dict) -> None:
    with st.chat_message("assistant"):
        st.markdown(escape_currency_for_markdown(message["content"])
)

        source_metrics = message.get("source_metrics", [])
        if source_metrics:
            st.markdown(
                f'<div class="source-line">Certified sources: {format_sources(source_metrics)}</div>',
                unsafe_allow_html=True,
            )

        status = message.get("status")
        if status == "unsupported":
            st.markdown(
                '<div class="status-note">This question is outside the currently certified Stratum metric scope.</div>',
                unsafe_allow_html=True,
            )
        elif status == "partially_supported":
            st.markdown(
                '<div class="status-note">Only the certified portion of the question was answered.</div>',
                unsafe_allow_html=True,
            )


def run_question(question: str, month: str) -> None:
    st.session_state.finance_copilot_messages.append(
        {"role": "user", "content": question, "month": month}
    )

    try:
        with st.spinner("Checking certified finance metrics..."):
            result = answer_finance_question(
                question=question,
                default_period=month,
            )

        st.session_state.finance_copilot_messages.append(
            {
                "role": "assistant",
                "content": result["answer"],
                "source_metrics": result.get("source_metrics", []),
                "status": result.get("status", "supported"),
                "month": month,
            }
        )

    except FinanceCopilotValidationError:
        st.session_state.finance_copilot_messages.append(
            {
                "role": "assistant",
                "content": (
                    "I couldn't produce a response that passed Stratum's validation checks, "
                    "so no unverified answer was shown. Please retry or rephrase the question."
                ),
                "source_metrics": [],
                "status": "validation_error",
                "month": month,
            }
        )

    except Exception:
        st.session_state.finance_copilot_messages.append(
            {
                "role": "assistant",
                "content": (
                    "Finance Copilot is temporarily unavailable. "
                    "Please try again in a moment."
                ),
                "source_metrics": [],
                "status": "technical_error",
                "month": month,
            }
        )


header_left, header_right = st.columns([4.8, 1.2])

with header_left:
    st.markdown(
        '<div class="stratum-kicker">STRATUM | STRATEGIC FINANCE</div>',
        unsafe_allow_html=True,
    )
    st.title("Finance Copilot")
    st.markdown(
        """
        <div class="stratum-subtitle">
            Ask questions about certified recurring-revenue, retention,
            customer, and concentration metrics.
        </div>
        """,
        unsafe_allow_html=True,
    )

with header_right:
    selected_month = st.selectbox(
        "Reporting month",
        options=MONTHS,
        index=MONTHS.index(st.session_state.finance_copilot_month),
        format_func=lambda value: MONTH_LABELS[value],
        key="finance_copilot_month",
        help=(
            "Used when your question does not explicitly name another "
            "supported reporting month."
        ),
    )

control_left, control_right = st.columns([5, 1])

with control_left:
    st.markdown(
        """
        <div class="scope-card">
            <div class="scope-title">CERTIFIED SCOPE</div>
            <div class="scope-copy">
                Finance Copilot answers only from Stratum's governed metric layer.
                It can explain ARR, MRR, recurring-revenue movement, NRR, GRR,
                customer retention, active customers, ARR per account, customer
                growth, concentration, and validated management commentary.
                Unsupported metrics or analyses are identified rather than invented.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with control_right:
    st.write("")
    st.write("")
    if st.button("Clear conversation", use_container_width=True):
        reset_conversation()
        st.rerun()

st.markdown("#### Try a question")

example_questions = [
    "What drove MRR in June 2026?",
    "How is retention overall?",
    "How fast is ARR growing?",
    "How many active customers do we have?",
]

for col, question in zip(st.columns(4), example_questions):
    with col:
        if st.button(
            question,
            key=f"example_{question}",
            use_container_width=True,
        ):
            st.session_state.finance_copilot_pending_question = question
            st.rerun()

st.markdown("")

if not st.session_state.finance_copilot_messages:
    with st.chat_message("assistant"):
        st.markdown(
            f"""
            I'm ready to answer questions using Stratum's certified finance metrics.
            The current default reporting period is **{MONTH_LABELS[selected_month]}**.

            You can ask a direct metric question, request an explanation of
            recurring-revenue drivers, or ask whether a metric is currently tracked.
            """
        )

for message in st.session_state.finance_copilot_messages:
    if message["role"] == "user":
        with st.chat_message("user"):
            st.markdown(message["content"])
    else:
        render_assistant_message(message)

pending_question = st.session_state.finance_copilot_pending_question
if pending_question:
    st.session_state.finance_copilot_pending_question = None
    run_question(
        question=pending_question,
        month=selected_month,
    )
    st.rerun()

user_question = st.chat_input("Ask Stratum Finance Copilot...")
if user_question:
    run_question(
        question=user_question,
        month=selected_month,
    )
    st.rerun()
