.PHONY: all report expectations panel test clean

# Reproduce everything from committed raw data
# Usage: make all
all: out/expectations.csv report.html

# ── Step 1: aggregate classified articles → expectations panel ────────────────
# Input:  news/articles_classified.csv  (committed raw input)
# Output: out/expectations.csv
out/expectations.csv: news/articles_classified.csv
	python news/build_expectations.py

# ── Step 2: render report (all regressions + figures run inline) ──────────────
# Input:  out/panel_full.csv, out/change_events.csv, out/expectations.csv
# Output: report.html
report.html: out/panel_full.csv out/change_events.csv out/expectations.csv
	quarto render report.qmd
	@echo "→ report.html"

# ── Optional: rebuild panel from match data on turkey-data branch ─────────────
panel:
	@echo "Fetching turkey-data branch..."
	git fetch origin turkey-data
	python analysis/build_panel_full.py

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	pytest tests/test_data.py -v

# ── Clean generated outputs ───────────────────────────────────────────────────
clean:
	rm -f report.html
	rm -f out/expectations.csv
	@echo "Removed report.html and out/expectations.csv"
	@echo "Run 'make all' to regenerate."
