import json
import os
from pathlib import Path

import msal
import requests
import streamlit as st
import json
import streamlit.components.v1 as components


st.set_page_config(
    page_title="Stratum | Strategic Finance",
    layout="wide",
)

TENANT_ID = os.environ["POWERBI_TENANT_ID"]
CLIENT_ID = os.environ["POWERBI_CLIENT_ID"]
CLIENT_SECRET = os.environ["POWERBI_CLIENT_SECRET"]
REPORT_ID = os.environ["POWERBI_REPORT_ID"]
REDIRECT_URI = os.environ["POWERBI_REDIRECT_URI"]

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://analysis.windows.net/powerbi/api/Report.Read.All"]

FLOW_FILE = Path(".auth_flow.json")


def get_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )


def save_flow(flow):
    with open(FLOW_FILE, "w", encoding="utf-8") as f:
        json.dump(flow, f)


def load_flow():
    if not FLOW_FILE.exists():
        return None

    with open(FLOW_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_flow():
    if FLOW_FILE.exists():
        FLOW_FILE.unlink()


st.title("Stratum Strategic Finance")
st.caption("Power BI authentication test")

app = get_msal_app()

# Microsoft has redirected back with an authorization code
if "code" in st.query_params:
    flow = load_flow()

    if not flow:
        st.error("Authentication flow state was not found.")
        st.stop()

    try:
        result = app.acquire_token_by_auth_code_flow(
            flow,
            dict(st.query_params),
        )
    except ValueError as exc:
        st.error(f"Authentication state validation failed: {exc}")
        st.stop()

    if "access_token" in result:
        st.session_state["powerbi_access_token"] = result["access_token"]
        delete_flow()
        st.query_params.clear()
        st.rerun()
    else:
        st.error("Microsoft authentication failed.")
        st.json(result)
        st.stop()


# Signed-in state
if "powerbi_access_token" in st.session_state:
    st.success("Microsoft authentication successful.")

    token = st.session_state["powerbi_access_token"]

    response = requests.get(
        f"https://api.powerbi.com/v1.0/myorg/reports/{REPORT_ID}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )

    if response.ok:
        report = response.json()

        embed_url = report["embedUrl"]

        st.success("Power BI connected.")

        embed_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <script src="https://cdn.jsdelivr.net/npm/powerbi-client/dist/powerbi.min.js"></script>
            <style>
                html, body {{
                    margin: 0;
                    padding: 0;
                    width: 100%;
                    height: 100%;
                    overflow: hidden;
                }}

                #reportContainer {{
                    width: 100%;
                    height: 850px;
                }}
            </style>
        </head>

        <body>
            <div id="reportContainer"></div>

            <script>
                const models = window['powerbi-client'].models;

                const config = {{
                    type: 'report',
                    id: {json.dumps(REPORT_ID)},
                    embedUrl: {json.dumps(embed_url)},
                    accessToken: {json.dumps(token)},
                    tokenType: models.TokenType.Aad,

                    permissions: models.Permissions.Read,

                    settings: {{
                        panes: {{
                            filters: {{
                                visible: false
                            }},
                            pageNavigation: {{
                                visible: false
                            }}
                        }},
                        bars: {{
                            statusBar: {{
                                visible: false
                            }}
                        }}
                    }}
                }};

                const container = document.getElementById('reportContainer');

                const report = powerbi.embed(container, config);

                report.on("loaded", function() {{
                    console.log("Stratum Power BI report loaded.");
                }});

                report.on("rendered", function() {{
                    console.log("Stratum Power BI report rendered.");
                }});

                report.on("error", function(event) {{
                    console.error(event.detail);
                }});
            </script>
        </body>
        </html>
        """

        components.html(
            embed_html,
            height=870,
            scrolling=False,
        )
    else:
            st.error(f"Power BI API returned {response.status_code}")
            st.code(response.text)

else:
    flow = app.initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    save_flow(flow)

    st.link_button(
        "Sign in with Microsoft",
        flow["auth_uri"],
        type="primary",
    )