#!/usr/bin/env bash
# run.sh — reproduce all figures and tables from committed data
#
# Requirements: Python 3.12+, Quarto 1.9+
#   pip install pandas numpy matplotlib pyfixest
#
# The pre-processed panel CSVs (out/panel_full.csv, out/change_events.csv,
# out/expectations.csv) are committed to the repo. Scraping and AI
# classification do NOT need to be re-run to reproduce the report.

set -euo pipefail

echo "=== Rendering report (all figures and tables reproduced inline) ==="
quarto render report.qmd

echo ""
echo "Done. Output: report.html"
echo ""
echo "── Optional: rebuild panel from raw match data (turkey-data branch) ──"
echo "  python analysis/build_panel_full.py   # requires git fetch origin turkey-data"
echo "  python analysis/did_analysis.py       # saves standalone figures to out/figures/"
