# Stratum on Replit

## Runtime

- Working directory: repository root.
- Entry point: `public_app.py`.
- Development and production command:
  `python -m streamlit run public_app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true`
- Required packaged runtime data: `database/stratum_finance.duckdb`.
- Required secret for AI commentary: `OPENAI_API_KEY`.
- Configuration files live in lowercase `config/` because Replit uses a case-sensitive filesystem.

The DuckDB file and secrets are intentionally excluded from Git. Confirm the database exists in the development workspace before publishing so it is included in the published application bundle.

## Update procedure

1. Keep local deployment work on a review branch and pull the latest changes from the connected GitHub repository.
2. Confirm `database/stratum_finance.duckdb` is present and `OPENAI_API_KEY` is configured in Replit Secrets.
3. Install dependencies from `requirements.txt` when they change.
4. Run the test suite with `python -m pytest`.
5. Start the Streamlit service and verify the Power BI report and management commentary.
6. Review and merge the deployment branch without rewriting Git history.
7. Republish from Replit, then verify the production URL.