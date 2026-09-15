from __future__ import annotations

import html
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from src.management_flags.service import get_management_flags


# ---------------------------------------------------------
# Page config
# ---------------------------------------------------------

st.set_page_config(
    page_title="Stratum | Executive Dashboard",
    page_icon="📊",
    layout="wide",
)


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

PUBLIC_POWER_BI_URL = (
    "https://app.powerbi.com/view?"
    "r=eyJrIjoiYTA3YjAwYTItYzc3MS00ODljLWEzOTgtNGE2YWE4ZWVmNWU2IiwidCI6ImVkNzZmY2RmLThjMTMtNDEyOS05MTdjLTkwODhmODE5Y2ZkOCJ9"
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


# ---------------------------------------------------------
# Management Flags
# ---------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=3600)
def load_management_flags(as_of_month: str):
    """
    Run the certified Management Flags pipeline once per month
    and cache the validated response.
    """
    return get_management_flags(as_of_month)


def normalize_flags(payload):
    """
    Support either a direct list response or a dictionary wrapper.
    """

    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in (
            "flags",
            "management_flags",
            "commentary",
            "stories",
        ):
            value = payload.get(key)

            if isinstance(value, list):
                return value

    return []


def render_commentary(flags):
    """Display validated flags as one cohesive executive brief."""
    if not flags:
        st.info("No material management flags for this period.")
        return

    sections = []
    severity_colors = {
        "positive": "#12B76A",
        "negative": "#F04438",
        "mixed": "#F79009",
        "neutral": "#98A2B3",
    }
    for flag in flags[:4]:
        category = html.escape(str(flag.get("category", "")).replace("_", " ").title())
        severity = str(flag.get("severity", "neutral")).lower()
        color = severity_colors.get(severity, severity_colors["neutral"])
        headline = html.escape(str(flag.get("headline", "Management observation")).replace("`", ""))
        detail = html.escape(str(flag.get("detail", "")).replace("`", ""))
        sections.append(
            '<section style="padding:18px 0;border-top:1px solid #EAECF0">'
            f'<div style="font-size:.72rem;font-weight:700;letter-spacing:.07em;'
            f'text-transform:uppercase;color:#667085;margin-bottom:8px">'
            f'<span style="color:{color};font-size:.9rem">●</span> {category}</div>'
            f'<div style="font-size:1.06rem;font-weight:650;color:#172033;'
            f'margin-bottom:7px">{headline}</div>'
            f'<div style="font-size:.94rem;line-height:1.6;color:#475467">{detail}</div>'
            '</section>'
        )

    st.markdown("".join(sections), unsafe_allow_html=True)

    with st.expander("Source metrics"):
        for flag in flags[:4]:
            metrics = flag.get("source_metrics", [])
            if isinstance(metrics, list):
                label = str(flag.get("category", "Flag")).replace("_", " ").title()
                st.caption(f"{label}: {', '.join(map(str, metrics))}")


# ---------------------------------------------------------
# Header
# ---------------------------------------------------------

st.markdown(
    """<div style="font-size:0.75rem;font-weight:700;letter-spacing:0.09em;
    color:#667085;">STRATUM | STRATEGIC FINANCE</div>
    <h1 style="margin-bottom:0.15rem;color:#172033;font-size:2rem;">
    Executive Finance Dashboard</h1>""",
    unsafe_allow_html=True,
)
st.caption("Interactive Power BI reporting with AI-assisted management commentary.")


# Keep the Power BI canvas at full width so its controls and labels stay readable.
st.markdown("#### Executive finance report")
st.iframe(PUBLIC_POWER_BI_URL, height=820)
st.caption("Use the filters inside Power BI to explore the report.")

st.divider()

# The month control belongs to the commentary section alone.
with st.container(border=True):
    st.caption("STRATUM INTELLIGENCE")
    st.markdown("## Management Commentary")
    st.caption(
        "Generated from certified finance metrics. The month below changes "
        "commentary only; Power BI uses its own filters."
    )

    controls_left, controls_right = st.columns([3, 1])
    with controls_left:
        commentary_month = st.selectbox(
            "Commentary month",
            options=MONTHS,
            format_func=lambda month: MONTH_LABELS[month],
            key="executive_commentary_month",
        )
    with controls_right:
        st.write("")
        if st.button("Refresh commentary", use_container_width=True):
            load_management_flags.clear()
            st.rerun()

    try:
        with st.spinner("Generating commentary..."):
            flags = normalize_flags(load_management_flags(commentary_month))
    except Exception as exc:
        st.error("Management commentary did not pass validation.")
        st.exception(exc)
    else:
        render_commentary(flags)
