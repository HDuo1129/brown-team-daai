# ============================================================
# analysis/estimate_did.R
# Turkish Süper Lig — Manager Change & Performance
# DiD / event-study estimation pipeline
# ============================================================
# NOTE: This script uses R + fixest. Python equivalent: pyfixest
# (pip install pyfixest), which accepts identical formula syntax.
# ============================================================

# ── 0. PACKAGES ───────────────────────────────────────────────────────────────
if (!requireNamespace("pacman", quietly = TRUE)) install.packages("pacman")
pacman::p_load(fixest, data.table, ggplot2, stringr)
setDTthreads(0)

# Set ROOT to the repo root. Adjust if not running from RStudio.
ROOT <- tryCatch(
  normalizePath(file.path(dirname(rstudioapi::getSourceEditorContext()$path), "..")),
  error = function(e) normalizePath(".")
)
# ROOT <- "/Users/macbook/Desktop/brown-team-daai"   # or set manually

# ── 1. LOAD DATA ──────────────────────────────────────────────────────────────
panel    <- fread(file.path(ROOT, "out/panel_full.csv"))
changes  <- fread(file.path(ROOT, "out/change_events.csv"))
exp_raw  <- fread(file.path(ROOT, "out/expectations.csv"))
team_ha  <- fread(file.path(ROOT, "features/team_home_away.csv"))
mgr_char <- fread(file.path(ROOT, "managers/manager_characteristics.csv"))
# manager_characteristics.csv cols used:
#   football_data_name, trainer_id, nationality, start_date, end_date,
#   age_at_appointment, experience_clubs_before, experience_years_before

panel[,    match_date := as.IDate(match_date)]
panel[,    fire_date  := as.IDate(fire_date)]   # fire_date of whichever change Python assigned
changes[,  fire_date  := as.IDate(fire_date)]
mgr_char[, start_date := as.IDate(start_date)]
mgr_char[, end_date   := as.IDate(end_date)]
setnames(mgr_char, "football_data_name", "team")

# Convert goals to integer (stored as float in CSV)
panel[, gf := as.integer(gf)]
panel[, ga := as.integer(ga)]


# ── 2. FEATURE ENGINEERING ────────────────────────────────────────────────────

## 2.1  Opponent strength: opponent's cumulative points BEFORE this match -------
# Panel has exactly one row per (team, match) → cumsum by (team, season) is correct.
setorder(panel, team, season, match_date)
panel[, cum_pts_before := cumsum(points) - points, by = .(team, season)]

opp_lookup <- panel[, .(opponent = team, season, match_date,
                          opponent_strength = cum_pts_before)]
panel <- merge(panel, opp_lookup,
               by = c("opponent", "season", "match_date"), all.x = TRUE)

## 2.2  Previous-season team quality -------------------------------------------
season_year <- function(s) as.integer(substr(s, 1L, 4L))

team_ha[, ppg  := (home_points + away_points) / (home_games + away_games)]
team_ha[, year := season_year(season)]
panel[,   year := season_year(season)]

# Shift team_ha by one year so that (team, year) matches season s-1
prev_q <- team_ha[, .(team,
                        prev_year          = year + 1L,
                        prev_season_ppg    = ppg,
                        prev_home_away_gap = home_away_gap)]

panel <- merge(panel, prev_q,
               by.x = c("team", "year"),
               by.y = c("team", "prev_year"),
               all.x = TRUE)
# NOTE: prev_season_ppg and prev_home_away_gap are constant within a (team, season).
# They are collinear with team×season FE and will be absorbed without identification.
# Use them only in models with team + season FE (Section 11, Model 8e).

## 2.3  is_foreign: current manager is non-Turkish -----------------------------
# Nationality is "Türkiye" for Turkish managers in this dataset.
TURKISH_RE <- "(?i)(t[\\u00fc]rkiye|turkey|t[\\u00fc]rk$)"
panel[, is_foreign := fifelse(
  is.na(nationality), NA_integer_,
  as.integer(!grepl(TURKISH_RE, nationality, perl = TRUE))
)]

## 2.4  First change per team-season -------------------------------------------
# change_events.csv has one row per change event (team, season, fire_date, ...).
# The Python build script may assign event_time relative to the LAST change when
# a team-season has multiple changes. We always use the FIRST change.
setorder(changes, team, season, fire_date)
first_ch <- changes[, .SD[1L], by = .(team, season)]

## 2.5  Recalculate event_time relative to the FIRST change --------------------
panel[, event_time := NA_real_]   # reset Python's version

panel <- merge(panel,
               first_ch[, .(team, season, first_post_n)],
               by = c("team", "season"), all.x = TRUE)

panel[!is.na(first_post_n),
      event_time := match_n - first_post_n]

## 2.6  PostChange binary -------------------------------------------------------
# = 1 for the post period of treated team-seasons; = 0 everywhere else
# (control team-seasons are always 0, not NA)
panel[, treated_ts  := !is.na(first_post_n)]
panel[, post_change := fifelse(treated_ts, as.integer(event_time >= 0L), 0L)]

## 2.7  NewManagerDomestic + incoming manager characteristics ------------------
# Incoming manager = the manager whose start_date is the first one AFTER fire_date
# for that (team, season) pair.
incoming <- merge(
  first_ch[, .(team, season, fire_date)],
  mgr_char[, .(team,
                start_date,
                new_nationality  = nationality,
                new_age          = age_at_appointment,
                new_exp_clubs    = experience_clubs_before,
                new_exp_years    = experience_years_before)],
  by = "team"
)[start_date > fire_date]

setorder(incoming, team, season, start_date)
incoming <- incoming[, .SD[1L], by = .(team, season)]

incoming[, new_mgr_domestic := as.integer(
  grepl(TURKISH_RE, new_nationality, perl = TRUE)
)]

panel <- merge(panel,
               incoming[, .(team, season,
                             new_mgr_domestic,
                             new_age,
                             new_exp_clubs,
                             new_exp_years)],
               by = c("team", "season"), all.x = TRUE)

## 2.8  expected_change (2025-26 only) -----------------------------------------
# = 1 if mean(avg_grade) >= 0.5 in the 4 ISO weeks immediately before firing
exp_raw[, week_monday := as.IDate(
  sprintf("%s-1", date), format = "%G-W%V-%u"
)]

ec <- merge(
  first_ch[season == "2025-2026", .(team, season, fire_date)],
  exp_raw[, .(team, week_monday, avg_grade)],
  by = "team"
)[week_monday < fire_date & week_monday >= (fire_date - 35L)]

ec <- ec[order(team, week_monday)][
  , .(pre_avg = mean(tail(avg_grade, 4L))),
  by = .(team, season)
][, expected_change := as.integer(pre_avg >= 0.5)]

panel <- merge(panel,
               ec[, .(team, season, expected_change)],
               by = c("team", "season"), all.x = TRUE)

# exp_lag1 is in panel for 2025-26 rows only; NA elsewhere
panel[season != "2025-2026", exp_lag1 := NA_real_]

## 2.9  Auxiliary outcomes and IDs ---------------------------------------------
panel[, win   := as.integer(points == 3L)]
panel[, ts_id := paste(team, season, sep = " | ")]


# ── 3. BUILD ANALYSIS PANELS ──────────────────────────────────────────────────

treated_ts_ids <- first_ch[, paste(team, season, sep = " | ")]
panel[, control_ts := !(ts_id %in% treated_ts_ids)]

# Event panel: treated ±10 window  +  ALL matches from untreated team-seasons.
# Control rows have event_time = NA; i() in fixest handles NA rows correctly
# (they contribute to FE estimation but not to event-time coefficients).
treated_win <- panel[!is.na(event_time) & event_time >= -10L & event_time <= 10L]
control_all <- panel[control_ts == TRUE]
event_panel <- rbindlist(list(treated_win, control_all), fill = TRUE)


# ── 4. MODEL 1: BASE DiD ──────────────────────────────────────────────────────
# Y_isw = α_i + μ_s + β PostChange + γ₁ home + γ₂ opponent_strength + ε
# Cluster SE at team level throughout.

m1_pts <- feols(points    ~ post_change + home + opponent_strength | team + season,
                data = panel, cluster = ~team)
m1_win <- feols(win        ~ post_change + home + opponent_strength | team + season,
                data = panel, cluster = ~team)
m1_gd  <- feols(goal_diff  ~ post_change + home + opponent_strength | team + season,
                data = panel, cluster = ~team)
m1_gf  <- feols(gf         ~ post_change + home + opponent_strength | team + season,
                data = panel, cluster = ~team)
m1_ga  <- feols(ga         ~ post_change + home + opponent_strength | team + season,
                data = panel, cluster = ~team)

etable(m1_pts, m1_win, m1_gd, m1_gf, m1_ga,
       title   = "Model 1 — Base DiD (team + season FE)",
       headers = c("Points", "Win", "Goal diff", "Goals for", "Goals against"))


# ── 5. MODEL 2: PREFERRED EVENT-STUDY ─────────────────────────────────────────
# Y_isw = α_{is} + λ_{sw} + δ_o
#       + Σ_{k≠-1} β_k 1[event_time=k]
#       + γ₁ home + γ₂ opponent_strength + ε
# FE: team×season | season×match_n | opponent
# Event window: -10 to +10, reference period = -1

m2 <- feols(
  points ~ i(event_time, ref = -1) + home + opponent_strength |
    team^season + season^match_n + opponent,
  data    = event_panel,
  cluster = ~team
)
summary(m2)
iplot(m2,
      main = "Event-study: manager change effect on points per match (ref = -1)",
      xlab = "Matchweeks relative to first manager change",
      ylab = "Coefficient (points per match)")
abline(v = -0.5, lty = 2, col = "tomato"); abline(h = 0, col = "grey60")


# ── 6. MODEL 3: EXTENDED — INCOMING MANAGER CHARACTERISTICS ──────────────────
# CAUTION: new_age, new_exp_clubs, new_exp_years are post-treatment by construction
# (only defined for post-change spell; NA in pre-period).
# They pick up correlation within treated observations, not a clean causal effect.
# Prefer Section 9 (heterogeneity interactions) for the rigorous version.

m3 <- feols(
  points ~ i(event_time, ref = -1) + home + opponent_strength +
           new_age + new_exp_clubs + new_exp_years |
    team^season + season^match_n + opponent,
  data    = event_panel[!is.na(new_age)],
  cluster = ~team
)

etable(m2, m3,
       title   = "Models 2-3: Preferred event-study vs extended",
       headers = c("Baseline", "+ Incoming manager controls (post-treatment by construction)"))


# ── 7. MODEL 4: ANTICIPATION / EXPECTATION (2025-26 ONLY) ────────────────────
# Expectation variables are available only for the 2025-26 season.
# Do NOT include in the main 30-season specification.

panel_26 <- panel[season == "2025-2026" & !is.na(post_change)]

# 4a. Continuous expectation signal (lagged 1 ISO week)
m4a <- feols(
  points ~ post_change + exp_lag1 + home + opponent_strength | team + match_n,
  data    = panel_26,
  cluster = ~team
)

# 4b. Binary expected_change indicator
m4b <- feols(
  points ~ post_change + expected_change + home + opponent_strength | team + match_n,
  data    = panel_26[!is.na(expected_change)],
  cluster = ~team
)

# 4c. Interaction: PostChange × expected_change
# β        = effect of an UNEXPECTED manager change (expected_change = 0)
# θ        = differential for an EXPECTED change
# β + θ    = total effect of an EXPECTED manager change
m4c <- feols(
  points ~ post_change * expected_change + home + opponent_strength | team + match_n,
  data    = panel_26[!is.na(expected_change)],
  cluster = ~team
)

b4  <- coef(m4c)[["post_change"]]
th4 <- coef(m4c)[["post_change:expected_change"]]
cat(sprintf(
  "\nModel 4c — β (unexpected) = %.3f | θ (diff for expected) = %.3f | β+θ (expected) = %.3f\n",
  b4, th4, b4 + th4
))

etable(m4a, m4b, m4c,
       title   = "Model 4 — Anticipation effects (2025-26 only)",
       headers = c("Continuous exp_lag1", "Binary expected_change", "Interaction"))


# ── 8. MODEL 5: DOMESTIC MANAGER HETEROGENEITY ────────────────────────────────
# β        = effect of a change where the INCOMING manager is foreign
# θ        = additional effect when the incoming manager is domestic/Turkish
# β + θ    = total effect when the incoming manager is domestic

m5 <- feols(
  points ~ post_change + post_change:new_mgr_domestic + home + opponent_strength |
    team^season + season^match_n + opponent,
  data    = event_panel[!is.na(new_mgr_domestic)],
  cluster = ~team
)

b5  <- coef(m5)[["post_change"]]
th5 <- coef(m5)[["post_change:new_mgr_domestic"]]
cat(sprintf(
  "\nModel 5 — β (foreign new mgr) = %.3f | θ = %.3f | β+θ (domestic new mgr) = %.3f\n",
  b5, th5, b5 + th5
))

etable(m5, title = "Model 5 — Domestic/foreign incoming manager heterogeneity")


# ── 9. MODEL 6: OTHER MANAGER CHARACTERISTIC HETEROGENEITY ───────────────────
# These interactions test whether the effect of a change depends on the
# characteristics of the incoming manager.

m6_age <- feols(
  points ~ post_change + post_change:new_age + home + opponent_strength |
    team^season + season^match_n + opponent,
  data = event_panel[!is.na(new_age)], cluster = ~team
)
m6_for <- feols(
  points ~ post_change + post_change:is_foreign + home + opponent_strength |
    team^season + season^match_n + opponent,
  data = event_panel[!is.na(is_foreign)], cluster = ~team
)
m6_ec <- feols(
  points ~ post_change + post_change:new_exp_clubs + home + opponent_strength |
    team^season + season^match_n + opponent,
  data = event_panel[!is.na(new_exp_clubs)], cluster = ~team
)
m6_ey <- feols(
  points ~ post_change + post_change:new_exp_years + home + opponent_strength |
    team^season + season^match_n + opponent,
  data = event_panel[!is.na(new_exp_years)], cluster = ~team
)

etable(m6_age, m6_for, m6_ec, m6_ey,
       title   = "Model 6 — Manager characteristic interactions",
       headers = c("× Age", "× Foreign (current)", "× Exp clubs", "× Exp years"))


# ── 10. MODEL 7: DOMESTIC vs FOREIGN EVENT-STUDY ──────────────────────────────

# Approach A: Single interacted model.
# i(event_time, ref=-1) coefficients    = foreign manager path   (new_mgr_domestic = 0)
# i(event_time, new_mgr_domestic, ref=-1) = DIFFERENTIAL for domestic path
# Domestic path = sum of both coefficient sets.
m7_int <- feols(
  points ~ i(event_time, ref = -1) +
           i(event_time, new_mgr_domestic, ref = -1) +
           home + opponent_strength |
    team^season + season^match_n + opponent,
  data    = event_panel[!is.na(new_mgr_domestic)],
  cluster = ~team
)

# Approach B: Two separate event-studies (cleaner plots, same identification).
m7_for <- feols(
  points ~ i(event_time, ref = -1) + home + opponent_strength |
    team^season + season^match_n + opponent,
  data    = event_panel[!is.na(new_mgr_domestic) & new_mgr_domestic == 0L],
  cluster = ~team
)
m7_dom <- feols(
  points ~ i(event_time, ref = -1) + home + opponent_strength |
    team^season + season^match_n + opponent,
  data    = event_panel[!is.na(new_mgr_domestic) & new_mgr_domestic == 1L],
  cluster = ~team
)


# ── 11. MODEL 8: ROBUSTNESS ───────────────────────────────────────────────────

## 8a. Single-change team-seasons only ----------------------------------------
single_ts <- changes[, .(n = .N), by = .(team, season)][
  n == 1L, paste(team, season, sep = " | ")
]
ep_single <- event_panel[control_ts == TRUE | ts_id %in% single_ts]

m8a <- feols(
  points ~ i(event_time, ref = -1) + home + opponent_strength |
    team^season + season^match_n + opponent,
  data = ep_single, cluster = ~team
)

## 8b. Alternative outcomes ----------------------------------------------------
alt_out <- function(outcome_col) {
  feols(
    reformulate(c("i(event_time, ref = -1)", "home", "opponent_strength"),
                response = outcome_col),
    data    = event_panel,
    cluster = ~team,
    fixef   = ~ team^season + season^match_n + opponent
  )
}
m8b_win <- feols(win       ~ i(event_time,ref=-1)+home+opponent_strength | team^season+season^match_n+opponent, data=event_panel, cluster=~team)
m8b_gd  <- feols(goal_diff ~ i(event_time,ref=-1)+home+opponent_strength | team^season+season^match_n+opponent, data=event_panel, cluster=~team)
m8b_gf  <- feols(gf        ~ i(event_time,ref=-1)+home+opponent_strength | team^season+season^match_n+opponent, data=event_panel, cluster=~team)
m8b_ga  <- feols(ga        ~ i(event_time,ref=-1)+home+opponent_strength | team^season+season^match_n+opponent, data=event_panel, cluster=~team)

## 8c. Alternative event windows -----------------------------------------------
mk_ep <- function(w) {
  rbindlist(list(
    panel[!is.na(event_time) & event_time >= -w & event_time <= w],
    panel[control_ts == TRUE]
  ), fill = TRUE)
}
m8c_6 <- feols(points ~ i(event_time,ref=-1)+home+opponent_strength | team^season+season^match_n+opponent, data=mk_ep(6L),  cluster=~team)
m8c_8 <- feols(points ~ i(event_time,ref=-1)+home+opponent_strength | team^season+season^match_n+opponent, data=mk_ep(8L),  cluster=~team)

etable(m8c_6, m8c_8, m2,
       title   = "Robustness: event window width",
       headers = c("±6 matches", "±8 matches", "±10 matches"))

## 8d. Placebo treatment for control team-seasons ------------------------------
set.seed(42)
ctrl_ts_list <- panel[control_ts == TRUE, unique(ts_id)]
fake_fire_dt <- data.table(
  ts_id       = ctrl_ts_list,
  fake_post_n = sample(10L:25L, length(ctrl_ts_list), replace = TRUE)
)
pan_plac <- merge(panel, fake_fire_dt, by = "ts_id", all.x = TRUE)
pan_plac[!is.na(fake_post_n), event_time := match_n - fake_post_n]

ep_plac <- pan_plac[!is.na(event_time) & event_time >= -10L & event_time <= 10L]
m8d_plac <- feols(
  points ~ i(event_time, ref = -1) + home + opponent_strength |
    team^season + season^match_n + opponent,
  data = ep_plac, cluster = ~team
)
# Expect: no significant pre- or post-coefficients (falsification check).

## 8e. FE specification comparison: team+season FE (allows quality controls) ---
# With team×season FE (Model 2), prev_season_ppg and prev_home_away_gap are
# perfectly absorbed (same value all 34 matches in a team-season → collinear).
# Replacing with team FE + season FE allows identification of γ₃ and γ₄.
m8e <- feols(
  points ~ i(event_time, ref = -1) + home + opponent_strength +
           prev_season_ppg + prev_home_away_gap |
    team + season + opponent,
  data    = event_panel[!is.na(prev_season_ppg)],
  cluster = ~team
)

etable(m2, m8e,
       title   = "Robustness: FE specification",
       headers = c("team×season + season×week FE (preferred)",
                   "team + season FE + quality controls"),
       notes   = paste("prev_season_ppg and prev_home_away_gap are collinear with",
                       "team-season FE in col.1; identifiable in col.2 which uses",
                       "team FE + season FE instead."))

## 8f. Mechanism analysis: in-game stats (2017-18 onward) ----------------------
# HS and HST are NOT in panel_full.csv (build_panel_full.py drops them).
# Add them by rebuilding or by loading raw match CSVs from the turkey-data branch.
# Template:
#
#   load_shots <- function(s) {
#     raw_bytes <- system(
#       paste0("git -C ", ROOT, " show origin/turkey-data:data/", s, ".csv"),
#       intern = TRUE
#     )
#     df <- fread(text = paste(raw_bytes, collapse = "\n"))
#     if (!"HS" %in% names(df)) return(NULL)
#     df[, match_date := as.IDate(Date, tryFormats = c("%d/%m/%Y", "%d/%m/%y"))]
#     home_rows <- df[, .(match_date, team=HomeTeam, opponent=AwayTeam, shots=HS, sot=HST)]
#     away_rows <- df[, .(match_date, team=AwayTeam, opponent=HomeTeam, shots=AS, sot=AST)]
#     rbindlist(list(home_rows, away_rows))
#   }
#   seasons_2017 <- panel[as.integer(substr(season,1,4)) >= 2017, unique(season)]
#   shots_panel  <- rbindlist(lapply(seasons_2017, load_shots), fill=TRUE)
#   ep_mech <- merge(event_panel[as.integer(substr(season,1,4)) >= 2017],
#                    shots_panel, by=c("team","opponent","match_date"), all.x=TRUE)
#   m8f_shots <- feols(shots ~ i(event_time,ref=-1)+home+opponent_strength |
#                        team^season+season^match_n+opponent, data=ep_mech, cluster=~team)
#   m8f_sot   <- feols(sot   ~ i(event_time,ref=-1)+home+opponent_strength |
#                        team^season+season^match_n+opponent, data=ep_mech, cluster=~team)
#
# LABEL AS DESCRIPTIVE/MECHANISM ONLY — shots are a potential mechanism,
# not a causal control. Including them in the main specification would
# over-control and block the treatment effect.


# ── 12. SUN & ABRAHAM (STAGGERED DiD) ────────────────────────────────────────
# sunab() implements Sun & Abraham (2021): each cohort is compared only to
# never-treated units, avoiding "contaminated" comparisons with already-treated
# units from other cohorts that plague standard TWFE under heterogeneous effects.
#
# Cohort definition: first_post_n (matchweek of first post-change match, 1-34).
# Period:           match_n (1-34 within each season).
# Never-treated:    cohort = Inf.
#
# Assumption: cohorts defined by within-season timing. Teams that changed at
# match 15 in 2005 and at match 15 in 2020 are in the same cohort. Season FEs
# and season×week FEs absorb cross-season baseline differences. For a fully
# cross-season staggered estimator, see the `did` package (Callaway & Sant'Anna).

panel[, cohort_sa := fifelse(!is.na(first_post_n),
                              as.numeric(first_post_n),
                              Inf)]

m_sunab <- feols(
  points ~ sunab(cohort_sa, match_n) + home + opponent_strength |
    team^season + season^match_n + opponent,
  data    = panel,
  cluster = ~team
)

summary(m_sunab, agg = "ATT")
iplot(m_sunab,
      main = "Sun & Abraham event-study (staggered DiD, within-season cohorts)",
      xlab = "Matchweeks relative to first manager change",
      ylab = "Points per match")

etable(m2, m_sunab,
       title   = "Standard TWFE vs Sun & Abraham (2021)",
       headers = c("TWFE event-study", "Sun-Abraham"),
       notes   = paste("SA estimator weights cohort-specific ATTs by cohort size.",
                       "Cohort = first post-change matchweek within season.",
                       "For cross-season staggering, use Callaway-Sant'Anna (did package)."))


# ── 13. PUBLICATION-QUALITY PLOTS ─────────────────────────────────────────────

# Helper: tidy event-study coefficients from a feols model
extract_es <- function(mod, label, ref_k = -1L) {
  ct  <- as.data.table(coeftable(mod), keep.rownames = "term")
  es  <- ct[grepl("^event_time::", term)]
  es[, k := as.integer(sub("^event_time::([^:]+).*", "\\1", term))]
  ref <- data.table(term = "ref", Estimate = 0, `Std. Error` = 0,
                    `t value` = NA_real_, `Pr(>|t|)` = NA_real_,
                    k = as.integer(ref_k))
  es  <- rbindlist(list(es, ref), fill = TRUE)
  es[, ci_lo := Estimate - 1.96 * `Std. Error`]
  es[, ci_hi := Estimate + 1.96 * `Std. Error`]
  es[, label := label]
  setorder(es, k)
  es
}

# Figure 1: Main event-study
es_main <- extract_es(m2, "All manager changes")

fig1 <- ggplot(es_main, aes(x = k, y = Estimate)) +
  geom_hline(yintercept = 0,    colour = "grey50", linetype = "dashed") +
  geom_vline(xintercept = -0.5, colour = "tomato",  linetype = "dashed", linewidth = 0.7) +
  geom_ribbon(aes(ymin = ci_lo, ymax = ci_hi), alpha = 0.18, fill = "steelblue") +
  geom_line(colour = "steelblue", linewidth = 0.9) +
  geom_point(colour = "steelblue", size = 2.2) +
  annotate("text", x = -0.2, y = max(es_main$ci_hi, na.rm = TRUE) * 0.95,
           label = "Change", colour = "tomato", size = 3.5, hjust = 0) +
  scale_x_continuous(breaks = -10:10) +
  labs(
    title    = "Manager change and points per match — Turkish Süper Lig (1994–2026)",
    subtitle = "team-season + season-week + opponent FE | 95% CI | team-clustered SE | ref = -1",
    x        = "Matchweeks relative to first manager change",
    y        = "Points per match (coefficient)"
  ) +
  theme_bw(base_size = 12) +
  theme(panel.grid.minor = element_blank())

ggsave(file.path(ROOT, "out/fig1_event_study_main.pdf"), fig1, width = 9, height = 5)
ggsave(file.path(ROOT, "out/fig1_event_study_main.png"), fig1, width = 9, height = 5, dpi = 300)

# Figure 2: Domestic vs foreign incoming manager
es_dom <- extract_es(m7_dom, "New manager: domestic (Turkish)")
es_for <- extract_es(m7_for, "New manager: foreign")
es_nat <- rbindlist(list(es_dom, es_for))

COLS <- c("New manager: domestic (Turkish)" = "#C0392B",
          "New manager: foreign"            = "#2980B9")

fig2 <- ggplot(es_nat, aes(x = k, y = Estimate, colour = label, fill = label)) +
  geom_hline(yintercept = 0,    colour = "grey50", linetype = "dashed") +
  geom_vline(xintercept = -0.5, colour = "grey30", linetype = "dashed", linewidth = 0.7) +
  geom_ribbon(aes(ymin = ci_lo, ymax = ci_hi), alpha = 0.15, colour = NA) +
  geom_line(linewidth = 0.9) +
  geom_point(size = 2.2) +
  scale_colour_manual(values = COLS) +
  scale_fill_manual(  values = COLS) +
  scale_x_continuous(breaks = -10:10) +
  labs(
    title    = "Manager change by nationality of incoming manager",
    subtitle = "Separate event-studies | 95% CI | team-clustered SE | ref = -1",
    x        = "Matchweeks relative to first manager change",
    y        = "Points per match (coefficient)",
    colour   = NULL, fill = NULL
  ) +
  theme_bw(base_size = 12) +
  theme(legend.position = "bottom", panel.grid.minor = element_blank())

ggsave(file.path(ROOT, "out/fig2_domestic_vs_foreign.pdf"), fig2, width = 9, height = 5)
ggsave(file.path(ROOT, "out/fig2_domestic_vs_foreign.png"), fig2, width = 9, height = 5, dpi = 300)

# Figure 3: Placebo test — pre and post should be flat
es_plac <- extract_es(m8d_plac, "Placebo (fake treatment)")
es_real <- extract_es(m2,       "Real treatment")
es_chk  <- rbindlist(list(es_real, es_plac))

COLS3 <- c("Real treatment" = "steelblue", "Placebo (fake treatment)" = "grey50")

fig3 <- ggplot(es_chk, aes(x = k, y = Estimate, colour = label, fill = label)) +
  geom_hline(yintercept = 0,    colour = "grey40", linetype = "dashed") +
  geom_vline(xintercept = -0.5, colour = "tomato",  linetype = "dashed", linewidth = 0.7) +
  geom_ribbon(aes(ymin = ci_lo, ymax = ci_hi), alpha = 0.15, colour = NA) +
  geom_line(linewidth = 0.9) +
  geom_point(size = 2.2) +
  scale_colour_manual(values = COLS3) +
  scale_fill_manual(  values = COLS3) +
  scale_x_continuous(breaks = -10:10) +
  labs(
    title    = "Real treatment vs placebo check",
    subtitle = "Placebo assigns random fire week to never-treated team-seasons | ref = -1",
    x        = "Matchweeks relative to (first/fake) manager change",
    y        = "Points per match (coefficient)",
    colour   = NULL, fill = NULL
  ) +
  theme_bw(base_size = 12) +
  theme(legend.position = "bottom", panel.grid.minor = element_blank())

ggsave(file.path(ROOT, "out/fig3_placebo.pdf"), fig3, width = 9, height = 5)
ggsave(file.path(ROOT, "out/fig3_placebo.png"), fig3, width = 9, height = 5, dpi = 300)

cat("\nDone. All models estimated. Figures saved to out/\n")
