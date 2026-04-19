# Project rules — Turkey Capstone

## Preferences

- Python only. pandas for data, statsmodels/pyfixest for regressions.
- All outputs (CSVs, parquet, HTML notebooks) go to /out — never scattered
  in the project root.
- Raw data files are immutable. Never edit a source CSV in place.
  Write cleaned versions to /out with a new name.
- Functions under 40 lines. If one grows larger, stop and split it.
- Use pathlib.Path for all file paths, not raw strings.

## Good practices for this project

### Primary key

match_id format: {season}_{week}_{game_n}  e.g. "2019_12_3"
Never create a row without a valid match_id.

### Manager assignment join

The join from matches → manager_spells is a DATE RANGE join, not a key join.
Always use the helper function `get_manager_on_date(team, date, spells_df)`.
Never inline this logic. Test it before using it anywhere.

### Scraping

All scraping functions must:

1. Return a DataFrame with an explicit documented schema.
2. Raise ValueError (not silently return empty) if 0 rows are scraped.
3. Log: URL fetched, row count returned, timestamp.
4. Use exponential backoff on 429 / 503 responses.
5. Respect robots.txt — check before adding a new source.

### Naming conventions

- Raw tables:       matches_raw, manager_spells, manager_chars, team_seasons
- Clean tables:     matches_clean, manager_clean
- Analysis panel:   analysis_panel
- File format:      parquet for anything > 50k rows, CSV otherwise

### Tests (run before every commit)

- data tests:  tests/test_data.py  — schema, PK uniqueness, no nulls on key cols
- code tests:  tests/test_funcs.py — mock DataFrames, known outputs
- describe:    notebooks/01_describe.ipynb — run top-to-bottom, no errors

### What NOT to do

- Do not hardcode season strings — derive from match_date.
- Do not drop rows for missing manager_chars without logging the count.
- Do not commit API keys or session cookies.
- Do not push raw scraped HTML to the repo — only parsed DataFrames.
