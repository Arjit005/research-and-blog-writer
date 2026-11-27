# PDF report generators

These scripts generate the archived verification and test reports in `reports/`.
Run each command from the repository root because the scripts use root-relative output paths.

```powershell
uv run python scripts/report_generation/generate_final_report.py
uv run python scripts/report_generation/generate_hardening_pdf.py
uv run python scripts/report_generation/generate_pdf_report.py
uv run python scripts/report_generation/generate_test_cases_pdf.py
uv run python scripts/report_generation/generate_verification_pdf.py
```

The scripts preserve the existing report filenames and overwrite the matching PDF when run.
