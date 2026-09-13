"""Stratum MVP: Power BI + shared Streamlit period state + simple chat echo.

Purpose
-------
Prove that:
1) Power BI and a native Streamlit interaction can live on the same page.
2) One Streamlit month filter can be shared by both surfaces.
3) The "AI" area can read the same selected period before any LLM/API is added.

Environment
-----------
Set POWER_BI_EMBED_URL to your Power BI report embed URL.

Optional:
- POWER_BI_FILTER_TABLE   default: Calendar
- POWER_BI_FILTER_FIELD   default: Year Month

The page appends a Power BI URL filter like:
    filter=Calendar/Year Month eq 202606

If your specific Power BI embed type does not honor URL filters, the page will
still render correctly and the chat will still share the Streamlit filter.
The later production integration can replace this URL-filter helper with the
Power BI JavaScript embed API without changing the page-level state pattern.
"""

from __future__ import annotations

import os
from urllib.parse import quote, urlencode, urlsplit, urlunsplit, parse_qsl

import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="Stratum | Strategic Finance",
    page_icon="📊",
    layout="wide",
)

# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
    <style>
        .block-container {
            max-width: 1500px;
            padding-top: 1.25rem;
            padding-bottom: 2rem;
        }
        .stratum-kicker {
            color: #667085;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: .25rem;
        }
        .stratum-period {
            display: inline-block;
            padding: .25rem .6rem;
            border: 1px solid #E4E7EC;
            border-radius: 999px;
            color: #172033;
            background: #FFFFFF;
            font-size: .85rem;
            margin-bottom: .75rem;
        }
        .stratum-note {
            color: #667085;
            font-size: .9rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Shared app state
# -----------------------------
MONTHS = [
    f"{year}-{month:02d}"
    for year in range(2024, 2027)
    for month in range(1, 13)
    if (year < 2026 or month <= 6)
]
MONTHS = list(reversed(MONTHS))

MONTH_LABELS = {
    value: __import__("datetime").datetime.strptime(value, "%Y-%m").strftime("%b %Y")
    for value in MONTHS
}

if "selected_month" not in st.session_state:
    st.session_state.selected_month = "2026-06"

if "messages" not in st.session_state:
    st.session_state.messages = []


def yyyymm(period: str) -> int:
    """Convert YYYY-MM to integer YYYYMM for the Power BI filter."""
    return int(period.replace("-", ""))


def build_filtered_power_bi_url(base_url: str, period: str) -> str:
    """Append/replace a simple Power BI URL filter using the shared month state."""
    table = os.getenv("POWER_BI_FILTER_TABLE", "Calendar")
    field = os.getenv("POWER_BI_FILTER_FIELD", "Year Month")

    # Power BI filter expression. Spaces remain readable after URL encoding.
    filter_expression = f"{table}/{field} eq {yyyymm(period)}"

    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["filter"] = filter_expression

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query, quote_via=quote, safe="/'"),
            parts.fragment,
        )
    )


def local_chat_reply(prompt: str, period: str) -> str:
    """Tiny deterministic stand-in for the future AI integration."""
    label = MONTH_LABELS[period]

    normalized = prompt.lower()
    if any(word in normalized for word in ("month", "period", "date", "viewing", "filter")):
        return f"You’re currently viewing **{label}**."

    return (
        f"I don’t have an LLM connected yet, but I can see the shared dashboard "
        f"context. The selected reporting period is **{label}**."
    )


# -----------------------------
# Header + master filter
# -----------------------------
header_left, header_right = st.columns([4, 1.25], vertical_alignment="bottom")

with header_left:
    st.markdown('<div class="stratum-kicker">STRATUM | Strategic Finance Lab</div>', unsafe_allow_html=True)
    st.title("Strategic Finance Intelligence")
    st.caption("Power BI executive reporting + shared application context")

with header_right:
    selected_month = st.selectbox(
        "As of month",
        options=MONTHS,
        index=MONTHS.index(st.session_state.selected_month),
        format_func=lambda x: MONTH_LABELS[x],
        key="selected_month",
    )

period_label = MONTH_LABELS[selected_month]
st.markdown(
    f'<div class="stratum-period">Shared page context: <strong>{period_label}</strong></div>',
    unsafe_allow_html=True,
)

# -----------------------------
# Power BI surface
# -----------------------------
st.subheader("Executive Finance Dashboard")

power_bi_url = os.getenv("POWER_BI_EMBED_URL", "").strip()

if power_bi_url:
    filtered_url = build_filtered_power_bi_url(power_bi_url, selected_month)

    components.iframe(
        filtered_url,
        height=760,
        scrolling=True,
    )

    with st.expander("MVP integration details"):
        st.write(
            "The Power BI iframe is being rebuilt from the same Streamlit "
            "month state used by the chat panel."
        )
        st.code(f"Selected month: {selected_month}")
        st.code(f"Power BI filter value: {yyyymm(selected_month)}")
else:
    st.warning(
        "POWER_BI_EMBED_URL is not set yet. Add your Power BI embed URL and "
        "rerun Streamlit to render the report here."
    )
    st.markdown(
        """
        **For the MVP, set this environment variable:**

        `POWER_BI_EMBED_URL=<your Power BI embed URL>`

        The page is already wired to append the selected month as a Power BI
        URL filter using `Calendar[Year Month]`.
        """
    )

st.divider()

# -----------------------------
# Local chat proof
# -----------------------------
chat_col, context_col = st.columns([2, 1])

with chat_col:
    st.subheader("Ask Stratum Finance")
    st.caption("Local demo only — no AI/API call yet.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Try: What month am I looking at?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        reply = local_chat_reply(prompt, selected_month)
        st.session_state.messages.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)

with context_col:
    st.subheader("Shared context")
    st.metric("As-of month", period_label)
    st.caption(
        "This is the state object both the Power BI embed helper and the "
        "chat surface read from."
    )

    st.json(
        {
            "as_of_month": selected_month,
            "power_bi_filter": {
                "table": os.getenv("POWER_BI_FILTER_TABLE", "Calendar"),
                "field": os.getenv("POWER_BI_FILTER_FIELD", "Year Month"),
                "value": yyyymm(selected_month),
            },
            "ai_context": {
                "as_of_month": selected_month,
            },
        }
    )
