# Turkey Capstone Data Collection

This repo is structured as a reproducible data-collection project for the
Turkish Super Lig manager-change capstone.

## Project outputs

- Raw source tables go to `data/raw/`
- Cleaned and merged tables go to `data/processed/`
- Summary outputs go to `out/`

## Core tables

- `matches_raw`: match results by game
- `manager_spells`: manager date ranges by team
- `manager_chars`: manager characteristics
- `team_seasons`: team-season quality information
- `analysis_panel`: processed match-level table with home and away managers

## Run the pipeline

1. Fetch raw data:

```bash
python3 ingestion.py fetch-raw --config config/turkey_sources.json --raw-dir data/raw
```

2. Build cleaned and processed outputs:

```bash
python3 ingestion.py build-processed --raw-dir data/raw --processed-dir data/processed --team-names data/team_names.csv
```

3. Write a quick table summary:

```bash
python3 ingestion.py describe --processed-dir data/processed --out-dir out
```

4. Run the full required pipeline in order:

```bash
python3 run_pipeline.py
```

## Tests

Run the project tests from the repo root:

```bash
python3 -m pytest -q
```

## Validation

Run validation directly:

```bash
python3 validation.py --raw-dir data/raw --processed-dir data/processed --out out/validation_report.json
```

Generate the basic descriptive outputs required for Session 1:

```bash
python3 describe_data.py --raw-dir data/raw --processed-dir data/processed --out-dir out
```

## Notes

- `config/turkey_sources.json` is config-driven so the team can extend or edit
  source URLs without changing code.
- The football-data URLs are prefilled for historical seasons.
- Transfermarkt club history pages for several Turkish clubs are prefilled.
- `manager_chars` URLs can be derived automatically from the manager links found
  on those club history pages.
