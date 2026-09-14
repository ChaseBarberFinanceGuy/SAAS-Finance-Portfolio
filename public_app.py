"""Public executive-only entry point for SAAS-Finance-Portfolio.

Save this file at the repository root, beside requirements.txt and app/.
Launch from the repository root:
    python -m streamlit run public_app.py --server.address=0.0.0.0 --server.port=8501

The deployed URL serves the existing report AND commentary for website embedding.
Requires a Streamlit version supporting st.Page and st.navigation (1.36+).
"""

from pathlib import Path
import sys

import streamlit as st
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Supports local commentary settings while preserving deployed environment values.
load_dotenv(REPO_ROOT / ".env", override=False)

# Execute the existing page once. Its page config, report, controls and commentary
# stay in that file. Home.py and the other application pages are not imported.
executive_page = st.Page(
    "app/pages/1_Executive_Dashboard.py",
    title="Executive Summary",
    default=True,
)
st.navigation([executive_page], position="hidden").run()
