"""Stratum home page. Save as app/Home.py in SAAS-Finance-Portfolio.

Local launch from the repository root:
    python -m streamlit run app/Home.py

Use public_app.py at the repository root for the public executive-only embed.
"""

from pathlib import Path
import sys

import streamlit as st
from dotenv import load_dotenv


# Make src imports and local settings independent of the shell's working folder.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Optional local settings for the commentary service. Deployment secrets take
# precedence; no Power BI credentials are required to open the public report.
load_dotenv(REPO_ROOT / ".env", override=False)

st.set_page_config(
    page_title="Stratum | Strategic Finance",
    page_icon="📊",
    layout="wide",
)

st.caption("STRATUM | STRATEGIC FINANCE")
st.title("A clearer view of recurring revenue.")
st.write(
    "Explore the executive finance dashboard and management commentary "
    "for Stratum, a synthetic B2B SaaS company."
)

with st.container(border=True):
    st.subheader("Executive Dashboard")
    st.write(
        "Review revenue, growth and retention in Power BI, then explore "
        "management commentary grounded in the finance metrics."
    )
    st.page_link(
        "pages/1_Executive_Dashboard.py",
        label="Open Executive Dashboard",
        icon="📊",
    )
    st.caption(
        "Power BI has its own filters. The commentary month selector controls "
        "company-wide commentary separately."
    )

st.caption("Independent portfolio project by Chase Barber. Uses synthetic data.")
