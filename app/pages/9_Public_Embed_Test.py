import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(layout="wide")

PUBLIC_URL = "https://app.powerbi.com/view?r=eyJrIjoiYTA3YjAwYTItYzc3MS00ODljLWEzOTgtNGE2YWE4ZWVmNWU2IiwidCI6ImVkNzZmY2RmLThjMTMtNDEyOS05MTdjLTkwODhmODE5Y2ZkOCJ9"

month = st.selectbox(
    "As of month",
    ["2026-06", "2026-05", "2026-04"],
)

components.iframe(
    PUBLIC_URL,
    height=800,
    scrolling=False,
)