#!/usr/bin/env bash
# run.sh — reproduce all outputs from a clean clone
# Usage: bash run.sh
# Requirements: Python 3.12+, Quarto 1.9+, pip install -r requirements.txt
# Match data is read from the turkey-data git branch (no manual download needed).

set -euo pipefail

echo "=== Step 1: Build analysis panel ==="
python analysis/build_panel_full.py

echo ""
echo "=== Step 2: Run econometric analysis ==="
python analysis/did_analysis.py

echo ""
echo "=== Step 3: Render report ==="
quarto render report.qmd

echo ""
echo "Done. Outputs:"
echo "  out/panel_full.csv        — full (team, match) panel"
echo "  out/panel_full_events.csv — ±10 match event window panel"
echo "  out/change_events.csv     — one row per treatment event"
echo "  out/figures/              — fig1–fig5 event-study and robustness plots"
echo "  report.html               — self-contained HTML report"
