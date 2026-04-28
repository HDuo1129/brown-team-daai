# ============================================================
# analysis/did_analysis.R
# Event-study DiD: Does changing a manager improve performance?
# Turkish Süper Lig, 1994–2026
#
# METHODOLOGICAL NOTES
# - Unit is team-season to reset treatment across seasons (staggered adoption).
# - Team-season FE absorb all time-invariant team-season quality.
# - Season-week FE absorb common shocks within each matchweek of a season.
# - Opponent FE (δ_o) control for fixture strength beyond the running tally.
# - Standard TWFE can be biased under staggered, heterogeneous treatment;
#   Sun & Abraham (2021) is estimated as a robustness check.
# - In-game controls (shots, cards) are post-treatment mechanisms and must
#   NOT be included in causal specifications — only in descriptive analyses.
# - Expectation variables (exp_lag1, expected_change) are available only for
#   the 2025-26 season and are analysed in a separate subsample.
# ============================================================

library(data.table)
library(fixest)
library(ggplot2)
library(modelsummary)
library(stringr)

# ── 0. Working directory ──────────────────────────────────────────────────────
# Set to repo root (adjust if running from a different location)
# setwd("~/Desktop/brown-team-daai")

# ── 1. Load data ──────────────────────────────────────────────────────────────
panel    <- fread("out/panel_full.csv")
changes  <- fread("out/change_events.csv")
mgr_char <- fread("managers/manager_characteristics.csv")
team_ha  <- fread("features/team_home_away.csv")
team_loc <- fread("features/team_location.csv")

# ── 2. Parse dates ─────────────────────────────────────────────────────────────
panel[, match_date := as.Date(match_date)]

# ── 3. Team-season identifier ──────────────────────────────────────────────────
panel[,   team_season := paste(team, season, sep = "__")]
changes[, team_season := paste(team, season, sep = "__")]

# ── 4. Keep only the FIRST in-season manager change per team-season ────────────
# Multiple changes per team-season (Antalya, Genclerbirligi, etc.) would
# create overlapping treatment windows.  We anchor on the first change so that
# the pre-period is clean.
first_ch <- changes[
  order(team_season, first_post_n),
  .SD[1L],
  by = team_season
][, .(team_season, first_post_n)]

# ── 5. Merge treatment timing onto panel ──────────────────────────────────────
# Drop the event_time already in the CSV (computed from all changes in Python).
panel[, c("event_time", "change_index", "fire_date", "manager_out") := NULL]
panel <- merge(panel, first_ch, by = "team_season", all.x = TRUE)

# Treatment indicators
panel[, PostChange    := as.integer(!is.na(first_post_n) & match_n >= first_post_n)]
panel[, relative_week := fifelse(!is.na(first_post_n),
                                  as.integer(match_n - first_post_n),
                                  NA_integer_)]

# ── 6. Build the event panel ──────────────────────────────────────────────────
# Keep: treated observations within ±10 window, OR all never-treated (controls)
EVENT_WIN <- 10L
panel_ev <- panel[
  is.na(relative_week) |
    (relative_week >= -EVENT_WIN & relative_week <= EVENT_WIN)
]

# For fixest i(): never-treated get rw = -999 (excluded by keep = argument)
panel_ev[, rw := fifelse(is.na(relative_week), -999L, as.integer(relative_week))]

# Season × matchweek fixed effect (absorbs common shocks per matchweek)
panel_ev[, season_week := paste0(season, "_W", sprintf("%02d", match_n))]

# ── 7. Opponent strength ──────────────────────────────────────────────────────
# Cumulative league points BEFORE the current match (lagged running total).
# Captures fixture difficulty beyond a simple opponent fixed effect.
setorder(panel, team, season, match_n)
panel[, cum_pts_before := shift(cumsum(points), n = 1L, fill = 0L),
      by = .(team, season)]

opp_str <- panel[, .(opponent = team, season, match_n,
                      opponent_strength = cum_pts_before)]
panel_ev <- merge(panel_ev, opp_str,
                  by  = c("opponent", "season", "match_n"),
                  all.x = TRUE)

# ── 8. is_foreign (current manager in each match) ────────────────────────────
turkish_nat <- c("Türkiye", "Turkey", "Turkish", "Türk", "Turkiye")
panel_ev[, is_foreign := as.integer(!is.na(nationality) &
                                       !(nationality %in% turkish_nat))]

# ── 9. NewManagerDomestic (incoming manager at the change) ───────────────────
# = nationality of the FIRST post-change manager in each treated team-season
new_mgr <- panel_ev[
  PostChange == 1L & !is.na(nationality),
  .(new_mgr_nat = nationality[which.min(relative_week)]),
  by = team_season
]
panel_ev <- merge(panel_ev, new_mgr, by = "team_season", all.x = TRUE)
panel_ev[, NewManagerDomestic := as.integer(!is.na(new_mgr_nat) &
                                               new_mgr_nat %in% turkish_nat)]

# ── 10. Manager experience (join for each match's manager) ───────────────────
mgr_xp <- unique(mgr_char[, .(trainer_id,
                                experience_clubs_before,
                                experience_years_before)])
panel_ev <- merge(panel_ev, mgr_xp, by = "trainer_id", all.x = TRUE)

# ── 11. Previous-season team stats ───────────────────────────────────────────
# prev_season_ppg and prev_home_away_gap: constant within a team-season,
# so they are collinear with team-season FE and will be dropped in the
# preferred spec.  They are useful when using team FE + season FE instead.
team_ha[, ppg := (home_points + away_points) / (home_games + away_games)]
team_ha[, season_prev := {
  y1 <- as.integer(str_sub(season, 1L, 4L))
  paste0(y1 - 1L, "-", y1)
}]
prev_stats <- team_ha[, .(team, season_prev,
                            prev_season_ppg      = ppg,
                            prev_home_away_gap   = home_away_gap)]
panel_ev <- merge(panel_ev,
                  prev_stats,
                  by.x  = c("team", "season"),
                  by.y  = c("team", "season_prev"),
                  all.x = TRUE)

# ── 12. Geographic region ────────────────────────────────────────────────────
panel_ev <- merge(panel_ev,
                  team_loc[, .(team = football_data_name, region)],
                  by = "team", all.x = TRUE)

# ── 13. expected_change (2025-26 only) ───────────────────────────────────────
# Binary: mean exp_lag1 in the four pre-change matchweeks >= 0.5
exp_thr <- panel_ev[
  season == "2025-2026" & !is.na(relative_week) &
    relative_week %between% c(-4L, -1L),
  .(pre_avg_grade = mean(exp_lag1, na.rm = TRUE)),
  by = team_season
][, expected_change := as.integer(pre_avg_grade >= 0.5)]

panel_ev <- merge(panel_ev,
                  exp_thr[, .(team_season, expected_change)],
                  by = "team_season", all.x = TRUE)

# ── 14. Additional binary outcomes ───────────────────────────────────────────
panel_ev[, win  := as.integer(points == 3L)]
panel_ev[, loss := as.integer(points == 0L)]

cat(sprintf(
  "Panel ready: %d rows | %d treated team-seasons | %d control team-seasons\n",
  nrow(panel_ev),
  uniqueN(panel_ev[!is.na(relative_week), team_season]),
  uniqueN(panel_ev[is.na(relative_week),  team_season])
))

# =============================================================================
# MODEL 1 — Base DiD
# Y_isw = α_i + μ_s + β PostChange + γ home + γ opp_strength + ε
# Simple two-way FE with a single post indicator.
# =============================================================================
m1 <- feols(
  points ~ PostChange + home + opponent_strength | team + season,
  data    = panel_ev[!is.na(PostChange)],
  cluster = ~team
)

# =============================================================================
# MODEL 2 — Preferred Event-Study (main specification)
# Y_isw = α_is + λ_sw + δ_o + Σ β_k 1[rw=k] + γ home + γ opp_strength + ε
# ref = -1 (week before firing is the baseline).
# =============================================================================
m2 <- feols(
  points ~ i(rw, ref = -1L, keep = -EVENT_WIN:EVENT_WIN) +
    home + opponent_strength |
    team_season + season_week + opponent,
  data    = panel_ev,
  cluster = ~team
)

# =============================================================================
# MODEL 3 — Extended Controls
# Adds prev_season_ppg and prev_home_away_gap.
# NOTE: These are constant within a team-season, so they are absorbed by
# team-season FE (m3_ts will drop them).  m3_alt uses team + season FE
# instead to retain their identifying variation.
# =============================================================================
m3_ts <- feols(                        # with team-season FE (controls dropped)
  points ~ i(rw, ref = -1L, keep = -EVENT_WIN:EVENT_WIN) +
    home + opponent_strength + prev_season_ppg + prev_home_away_gap |
    team_season + season_week + opponent,
  data    = panel_ev,
  cluster = ~team
)
m3_alt <- feols(                       # with team + season FE (controls retained)
  points ~ PostChange + home + opponent_strength +
    prev_season_ppg + prev_home_away_gap |
    team + season + opponent,
  data    = panel_ev[!is.na(PostChange)],
  cluster = ~team
)

# =============================================================================
# MODEL 4 — Anticipation Model (2025-26 season only)
# Expectation variables are available only for 2025-26.
# β = average effect of a change; ρ = role of pre-existing pressure.
# In m4c, β = effect when change was NOT expected (expected_change = 0),
#         β + θ = effect when change WAS expected (expected_change = 1).
# =============================================================================
panel_26 <- panel_ev[season == "2025-2026"]

m4a <- feols(                          # continuous expectation signal
  points ~ PostChange + exp_lag1 + home + opponent_strength | team + match_n,
  data    = panel_26[!is.na(PostChange) & !is.na(exp_lag1)],
  cluster = ~team
)
m4b <- feols(                          # binary expected_change
  points ~ PostChange + expected_change + home + opponent_strength | team + match_n,
  data    = panel_26[!is.na(PostChange) & !is.na(expected_change)],
  cluster = ~team
)
m4c <- feols(                          # interaction: heterogeneity by expectation
  points ~ PostChange * expected_change + home + opponent_strength | team + match_n,
  data    = panel_26[!is.na(PostChange) & !is.na(expected_change)],
  cluster = ~team
)
cat(sprintf(
  "\nModel 4c (2025-26 anticipation):\n  β (unexpected): %.4f\n  θ (additional for expected): %.4f\n  β+θ (expected): %.4f\n",
  coef(m4c)["PostChange"],
  coef(m4c)["PostChange:expected_change"],
  coef(m4c)["PostChange"] + coef(m4c)["PostChange:expected_change"]
))

# =============================================================================
# MODEL 5 — Domestic Manager Heterogeneity (main heterogeneity spec)
# β     = effect when the new manager is foreign/non-Turkish
# θ     = additional effect when the new manager is domestic/Turkish
# β + θ = total effect of replacing with a domestic manager
# =============================================================================
m5 <- feols(
  points ~ PostChange + PostChange:NewManagerDomestic +
    home + opponent_strength |
    team_season + season_week + opponent,
  data    = panel_ev[!is.na(NewManagerDomestic)],
  cluster = ~team
)
cat(sprintf(
  "\nModel 5 (domestic vs foreign):\n  β (foreign):    %.4f\n  θ (domestic Δ): %.4f\n  β+θ (domestic): %.4f\n",
  coef(m5)["PostChange"],
  coef(m5)["PostChange:NewManagerDomestic"],
  coef(m5)["PostChange"] + coef(m5)["PostChange:NewManagerDomestic"]
))

# =============================================================================
# MODEL 6 — Other Manager-Characteristic Heterogeneity
# Same interaction structure as M5 but with continuous characteristics.
# Caution: age_at_appointment and experience are constant within a manager
# spell, so they are best interpreted as cross-sectional moderators.
# =============================================================================
m6_for  <- feols(points ~ PostChange + PostChange:is_foreign +
                   home + opponent_strength |
                   team_season + season_week + opponent,
                 data = panel_ev[!is.na(is_foreign)], cluster = ~team)

m6_age  <- feols(points ~ PostChange + PostChange:age_at_appointment +
                   home + opponent_strength |
                   team_season + season_week + opponent,
                 data = panel_ev[!is.na(age_at_appointment)], cluster = ~team)

m6_clubs <- feols(points ~ PostChange + PostChange:experience_clubs_before +
                    home + opponent_strength |
                    team_season + season_week + opponent,
                  data = panel_ev[!is.na(experience_clubs_before)], cluster = ~team)

m6_yrs  <- feols(points ~ PostChange + PostChange:experience_years_before +
                   home + opponent_strength |
                   team_season + season_week + opponent,
                 data = panel_ev[!is.na(experience_years_before)], cluster = ~team)

# =============================================================================
# MODEL 7 — Domestic vs Foreign: Separate Event-Studies
# Estimate the full event-study trajectory for each group.
# Never-treated observations serve as controls in both regressions.
# =============================================================================
m7_dom <- feols(
  points ~ i(rw, ref = -1L, keep = -EVENT_WIN:EVENT_WIN) +
    home + opponent_strength |
    team_season + season_week + opponent,
  data    = panel_ev[is.na(relative_week) | NewManagerDomestic == 1L],
  cluster = ~team
)
m7_for <- feols(
  points ~ i(rw, ref = -1L, keep = -EVENT_WIN:EVENT_WIN) +
    home + opponent_strength |
    team_season + season_week + opponent,
  data    = panel_ev[is.na(relative_week) | NewManagerDomestic == 0L],
  cluster = ~team
)

# =============================================================================
# SUN & ABRAHAM (2021) — Staggered Treatment Robustness
# Addresses the negative-weight bias in TWFE under heterogeneous treatment
# timing.  Cohort = first_post_n (match number of first change); 0 = never.
# =============================================================================
panel_ev[, cohort := fifelse(is.na(first_post_n), 0L, as.integer(first_post_n))]

m_sunab <- feols(
  points ~ sunab(cohort, rw) + home + opponent_strength |
    team_season + season_week,
  data    = panel_ev,
  cluster = ~team
)

# =============================================================================
# ROBUSTNESS CHECKS
# =============================================================================

# R1: Restrict to team-seasons with exactly ONE manager change
n_ch      <- changes[, .N, by = team_season]
single_ts <- n_ch[N == 1L, team_season]
m_r1 <- feols(
  points ~ i(rw, ref = -1L, keep = -EVENT_WIN:EVENT_WIN) +
    home + opponent_strength |
    team_season + season_week + opponent,
  data    = panel_ev[is.na(relative_week) | team_season %in% single_ts],
  cluster = ~team
)

# R2: Alternative outcomes
outcomes <- c("win", "goal_diff", "gf", "ga")
m_r_out  <- lapply(setNames(outcomes, outcomes), function(y) {
  feols(
    as.formula(paste0(y, " ~ i(rw, ref=-1L, keep=-10:10) + home + opponent_strength",
                      " | team_season + season_week + opponent")),
    data    = panel_ev,
    cluster = ~team
  )
})

# R3: Narrower event windows (±6 and ±8)
mk_window <- function(w) {
  panel_ev[is.na(relative_week) | (relative_week >= -w & relative_week <= w)]
}
m_r6 <- feols(points ~ i(rw, ref=-1L, keep=-6:6)  + home + opponent_strength |
                team_season + season_week + opponent, data=mk_window(6L), cluster=~team)
m_r8 <- feols(points ~ i(rw, ref=-1L, keep=-8:8)  + home + opponent_strength |
                team_season + season_week + opponent, data=mk_window(8L), cluster=~team)

# R4: TWFE (team + season FE) vs preferred (team-season + season-week FE)
m_r_twfe <- feols(
  points ~ PostChange + home + opponent_strength +
    prev_season_ppg + prev_home_away_gap |
    team + season,
  data    = panel_ev[!is.na(PostChange)],
  cluster = ~team
)

# =============================================================================
# TABLES
# =============================================================================
dir.create("out/tables", showWarnings = FALSE, recursive = TRUE)

# Table 1: Main specifications
etable(
  m1, m2, m3_ts, m3_alt,
  title   = "Main DiD Specifications — Outcome: Points per Match",
  headers = c("(1) Base DiD", "(2) Event-Study", "(3) Extended (TS FE)", "(4) Extended (T+S FE)"),
  notes   = paste(
    "Preferred spec is (2): team-season FE, season-week FE, opponent FE.",
    "In (3), prev_season_ppg and prev_home_away_gap are collinear with team-season FE and dropped.",
    "In (4), team + season FE allow identification of team-level controls.",
    "SEs clustered at team level throughout."
  ),
  cluster = ~team,
  tex     = TRUE,
  file    = "out/tables/table1_main.tex"
)

# Table 2: Heterogeneity — manager characteristics
etable(
  m5, m6_for, m6_age, m6_clubs, m6_yrs,
  title   = "Manager Heterogeneity — Outcome: Points per Match",
  headers = c("(1) Domestic", "(2) Foreign", "(3) Age", "(4) Clubs", "(5) Years exp."),
  notes   = paste(
    "All models include home, opponent_strength, team-season FE, season-week FE, opponent FE.",
    "β = effect for foreign manager; β+θ = effect for domestic manager (col 1).",
    "Cols 3–5: manager characteristics are constant within spell; interpret as cross-sectional moderators."
  ),
  cluster = ~team,
  tex     = TRUE,
  file    = "out/tables/table2_heterogeneity.tex"
)

# Table 3: Anticipation (2025-26 only)
etable(
  m4a, m4b, m4c,
  title   = "Anticipation Analysis (2025-26) — Outcome: Points per Match",
  headers = c("(1) exp_lag1", "(2) expected_change", "(3) Interaction"),
  notes   = paste(
    "2025-26 subsample only (N = 18 teams). Team and matchweek FE.",
    "In (3): β = effect when change was unexpected; β+θ = effect when change was expected.",
    "exp_lag1 = avg_grade from the week before the match (Groq/Llama classifier).",
    "expected_change = 1 if mean exp_lag1 ≥ 0.5 in the four weeks before firing."
  ),
  cluster = ~team,
  tex     = TRUE,
  file    = "out/tables/table3_anticipation.tex"
)

# Table 4: Robustness
etable(
  m2, m_r1, m_r6, m_r8, m_r_twfe,
  title   = "Robustness Checks — Outcome: Points per Match",
  headers = c("(1) Preferred", "(2) Single change", "(3) ±6 window", "(4) ±8 window", "(5) TWFE"),
  notes   = paste(
    "(1) preferred: team-season + season-week + opponent FE, ±10 window.",
    "(2) team-seasons with only one manager change.",
    "(3)-(4) alternative event windows.",
    "(5) TWFE with team + season FE and team-level controls; PostChange only."
  ),
  cluster = ~team,
  tex     = TRUE,
  file    = "out/tables/table4_robustness.tex"
)

# Table 5: Alternative outcomes
etable(
  m2, m_r_out[["win"]], m_r_out[["goal_diff"]],
  m_r_out[["gf"]],      m_r_out[["ga"]],
  title   = "Alternative Outcomes — Event-Study (preferred FE)",
  headers = c("(1) Points", "(2) Win", "(3) Goal diff", "(4) Goals for", "(5) Goals against"),
  cluster = ~team,
  tex     = TRUE,
  file    = "out/tables/table5_outcomes.tex"
)

cat("Tables saved to out/tables/\n")

# =============================================================================
# FIGURES
# =============================================================================
dir.create("out/figures", showWarnings = FALSE, recursive = TRUE)

# Figure 1: Main event-study plot (base R via iplot)
png("out/figures/fig1_event_study_main.png", width = 960, height = 600, res = 130)
iplot(
  m2,
  main     = "Event-Study: Effect of Manager Change on Points per Match",
  xlab     = "Matchweeks Relative to Manager Change",
  ylab     = "Effect on Points (ref: week −1)",
  zero.par = list(col = "firebrick", lty = 2),
  pt.join  = TRUE
)
abline(v = -0.5, lty = 2, col = "grey40")
dev.off()
cat("Saved: out/figures/fig1_event_study_main.png\n")

# Figure 2: Domestic vs Foreign event-study (ggplot)
extract_es <- function(model, label) {
  ct <- as.data.table(coeftable(model), keep.rownames = "term")
  ct <- ct[str_detect(term, "^rw::")]
  ct[, rw := as.integer(str_remove(term, "^rw::"))]
  ct[, .(rw,
         estimate = Estimate,
         se       = `Std. Error`,
         group    = label)]
}

es_dt <- rbind(
  extract_es(m7_dom, "Domestic (Turkish) manager"),
  extract_es(m7_for, "Foreign manager"),
  # Reference point (week −1 = 0 by construction)
  data.table(rw = -1L, estimate = 0, se = 0,
             group = c("Domestic (Turkish) manager", "Foreign manager"))
)
setorder(es_dt, group, rw)

pal <- c("Domestic (Turkish) manager" = "#2166ac",
         "Foreign manager"            = "#d6604d")

p2 <- ggplot(es_dt, aes(rw, estimate, colour = group, fill = group)) +
  geom_hline(yintercept = 0, linetype = "dashed", colour = "grey50") +
  geom_vline(xintercept = -0.5, linetype = "dashed", colour = "grey40") +
  geom_ribbon(aes(ymin = estimate - 1.96 * se,
                  ymax = estimate + 1.96 * se),
              alpha = 0.15, colour = NA) +
  geom_line(linewidth = 0.8) +
  geom_point(size = 2.2) +
  scale_colour_manual(values = pal) +
  scale_fill_manual(values = pal) +
  scale_x_continuous(breaks = seq(-10, 10, 2)) +
  labs(
    title    = "Manager Change: Domestic vs Foreign New Manager",
    subtitle = "95 % confidence intervals, SEs clustered at team level",
    x        = "Matchweeks Relative to Manager Change",
    y        = "Effect on Points per Match",
    colour   = NULL, fill = NULL
  ) +
  theme_minimal(base_size = 13) +
  theme(legend.position = "bottom", panel.grid.minor = element_blank())

ggsave("out/figures/fig2_domestic_foreign.png", p2,
       width = 9, height = 5.5, dpi = 150)
cat("Saved: out/figures/fig2_domestic_foreign.png\n")

# Figure 3: Alternative outcomes comparison
png("out/figures/fig3_alt_outcomes.png", width = 960, height = 700, res = 120)
iplot(
  list("Points" = m2,
       "Win"    = m_r_out[["win"]],
       "Goal Δ" = m_r_out[["goal_diff"]]),
  main     = "Event-Study: Alternative Outcomes",
  xlab     = "Matchweeks Relative to Manager Change",
  ylab     = "Estimated Effect",
  zero.par = list(col = "firebrick", lty = 2),
  pt.join  = TRUE
)
dev.off()
cat("Saved: out/figures/fig3_alt_outcomes.png\n")

# Figure 4: Robustness — event-window comparison
png("out/figures/fig4_robustness_windows.png", width = 960, height = 600, res = 120)
iplot(
  list("±10 (preferred)" = m2, "±8" = m_r8, "±6" = m_r6),
  main     = "Robustness: Alternative Event Windows",
  xlab     = "Matchweeks Relative to Manager Change",
  ylab     = "Effect on Points",
  zero.par = list(col = "firebrick", lty = 2),
  pt.join  = TRUE
)
dev.off()
cat("Saved: out/figures/fig4_robustness_windows.png\n")

# Figure 5: Sun & Abraham vs TWFE comparison
png("out/figures/fig5_sunab_vs_twfe.png", width = 960, height = 600, res = 120)
iplot(
  list("TWFE (preferred)" = m2, "Sun & Abraham" = m_sunab),
  main     = "TWFE vs Sun & Abraham (2021) Estimator",
  xlab     = "Matchweeks Relative to Manager Change",
  ylab     = "Effect on Points",
  zero.par = list(col = "firebrick", lty = 2),
  pt.join  = TRUE
)
dev.off()
cat("Saved: out/figures/fig5_sunab_vs_twfe.png\n")

cat("\n=== All models estimated. Tables in out/tables/, figures in out/figures/ ===\n")
