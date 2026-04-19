# Capstone Plan — Manager Changes & Team Performance, Süper Lig

## Research question

Does a mid-season manager change improve a team's results, and does the effect
vary by manager characteristics (nationality, experience, age)?

## Identification strategy

Difference-in-differences (DiD): compare a team's points-per-game in a window
before vs. after a sacking, using teams that did NOT change manager in the same
window as controls. Later: staggered-DiD (Callaway–Sant'Anna) to handle
multiple treatment dates.

## Unit of observation

One row = one match × one team (team-match panel).
Outcome: points earned (0/1/3), goals scored, goals conceded.

## Primary key

`match_id` = {season}_{week}_{game_number}  e.g. `2019_12_3`
Join key for manager assignment: (team, match_date) → look up manager_spells.

## Data sources

| Table | Source | Method |
|---|---|---|
| matches_raw | football-data.co.uk | CSV download |
| manager_spells | Transfermarkt | Scrape |
| manager_chars | Transfermarkt | Scrape (per manager page) |
| team_seasons | Transfermarkt | Scrape (squad value, season) |

## Coverage target

- Seasons: 2013/14 – 2024/25 (11 seasons)
- League: Süper Lig only
- Teams: all clubs that appeared in the top flight

## Key join (hardest step)

For each match row, assign home_manager and away_manager by finding the
manager_spell where spell.team = team AND spell.start_date ≤ match_date ≤
spell.end_date. This is a date-range merge — NOT a simple key join.
Use pandas merge_asof or an explicit interval lookup. Test with 5 mock rows.

## Manager change definition

- Sacking or resignation during the season = treatment event
- End-of-season departure = NOT a treatment event (exclude from DiD window)
- Caretaker spells: include if ≥ 3 games, mark with flag `is_caretaker = True`

## Known gaps / limitations

- Small clubs in early seasons (pre-2015) may have incomplete manager data on
  Transfermarkt — document coverage in DATA.md
- Match week numbers not always reliable; derive from match_date if needed
- Some manager birthdate/nationality fields may be missing for lesser-known
  managers — note in DATA.md, do not drop rows silently

## Owners (fill in your team)

| Task | Owner |
|---|---|
| football-data.co.uk download + clean | |
| Transfermarkt manager_spells scrape | |
| Transfermarkt manager_chars scrape | |
| team_seasons scrape | |
| Date-range join + test | |
| Data-describe notebook | |
