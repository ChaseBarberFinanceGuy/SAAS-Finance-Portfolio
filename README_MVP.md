# Stratum Streamlit MVP

This is the presentation-proof MVP discussed before continuing the full
Management Flags implementation.

## What it proves

- Power BI and native Streamlit components can live on one page.
- Streamlit owns a shared `selected_month` state.
- The chat demo reads that same state.
- The Power BI iframe URL is rebuilt from that same state using a simple
  URL filter attempt.

## Install

Place:

`app/pages/4_Management_Flags.py`

into the matching path in your local repo, replacing the current placeholder
version of that file.

No change to `config/metrics.json` is needed.

## Power BI setup for this MVP

Set an environment variable before launching Streamlit:

### PowerShell

```powershell
$env:POWER_BI_EMBED_URL="PASTE_YOUR_POWER_BI_EMBED_URL_HERE"
streamlit run app/Home.py
```

If your Streamlit entry point is different, run that file instead.

The page defaults to:
- table: `Calendar`
- field: `Year Month`
- value format: `202606`

Optional overrides:

```powershell
$env:POWER_BI_FILTER_TABLE="Calendar"
$env:POWER_BI_FILTER_FIELD="Year Month"
```

## Important Power BI note

The first MVP uses a URL filter because it is lightweight and proves the
page architecture quickly.

Whether the report itself responds to that URL filter depends on the exact
Power BI embed mode and URL you use. If the report renders but does not change
months, do not rebuild the Streamlit page. The next integration layer is simply
to replace the URL-filter helper with the Power BI JavaScript embed API.

The shared Streamlit state pattern remains the same.

## Test

1. Open the Management Flags page.
2. Select `Jun 2026`.
3. Confirm the "Shared context" panel displays Jun 2026.
4. Type: `What month am I looking at?`
5. Confirm chat replies: `You're currently viewing Jun 2026.`
6. Change to another month.
7. Ask again and confirm chat follows the new month.
8. If your Power BI embed honors URL filtering, confirm the report changes too.
