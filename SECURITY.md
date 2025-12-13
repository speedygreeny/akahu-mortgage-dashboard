# Security and sensitive data guidance

This repository contains code and example scripts for personal finance analytics. Before publishing or sharing, please follow these guidelines:

- Remove any real secrets (Akahu tokens, API keys) from the repository and history. Use `.env` for local secrets and add `.env` to `.gitignore`.
- Do NOT commit full DuckDB snapshots containing real personal financial data. If you have a sample dataset, reduce it to synthetic or anonymized records.
- If you discover a secret in git history, rotate the secret and remove it from the history (tools: `git filter-repo`, `bfg-repo-cleaner`).
- Limit file permissions for local `data/` files and ensure backups are not publicly exposed.
- For CI, set secrets in the GitHub repository settings (Actions secrets) rather than in the repository files.
- If accepting contributions, encourage contributors to avoid posting screenshots or logs containing PII or tokens.

If you need help anonymizing or stripping sensitive data before publishing, open an issue and I can provide a small script to sanitize local DuckDB files.
