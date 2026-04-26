# Classifier Validation — Interpretation

## Summary

| Metric | Result |
|--------|--------|
| Articles hand-labelled | 10 |
| Score agreement (±1)   | 9/10 = 90% |
| is_relevant agreement  | 10/10 = 100% |
| Both agree             | 90% |
| Target                 | ≥ 80% |
| Status                 | ✅ PASS — ready to scale |

## Score normalisation

Raw scores (0–4) are normalised to percentages for downstream use:

| Raw score | Normalised | Meaning |
|-----------|------------|---------|
| 0 | 0% | No signal |
| 1 | 25% | Mild signal |
| 2 | 50% | Moderate signal |
| 3 | 75% | Strong signal |
| 4 | 100% | Confirmed change |

## Article-level results

| # | Team | Date | Human | LLM | Score match | Rel match | Reason |
|---|------|------|-------|-----|-------------|-----------|--------|
| 1 | Fenerbahce | 2025-08-07 | 1(Y) | 0(Y) | ✅ | ✅ | Mourinho answering questions about transfers and departures is routine post-matc |
| 2 | Konyaspor | 2025-10-19 | 3(Y) | 3(Y) | ✅ | ✅ | Fans publicly demanding manager Recep Uçar's resignation through chants/protests |
| 3 | Antalyaspor | 2025-07-03 | 1(Y) | 4(Y) | ❌ | ✅ | Article explicitly states that manager Emre Belözoğlu resigned from Antalyaspor, |
| 4 | Genclerbirligi | 2025-12-07 | 4(Y) | 4(Y) | ✅ | ✅ | Volkan Demirel's resignation as Gençlerbirliği manager has been explicitly confi |
| 5 | Galatasaray | 2026-04-21 | 0(N) | 0(N) | ✅ | ✅ | Routine tactical article about cup match squad rotation decisions by the manager |
| 6 | Trabzonspor | 2026-04-21 | 0(N) | 0(N) | ✅ | ✅ | Routine post-match quote from manager Fatih Tekke addressing his players after a |
| 7 | Besiktas | 2025-08-29 | 0(N) | 0(N) | ✅ | ✅ | Article announces Sergen Yalçın as Beşiktaş's new manager — a post-change appoin |
| 8 | Fenerbahce | 2025-09-09 | 0(Y) | 0(Y) | ✅ | ✅ | This is a new-manager profile article asking 'Who is Domenico Tedesco?' — the ap |
| 9 | Trabzonspor | 2025-07-01 | 0(N) | 0(N) | ✅ | ✅ | Article headline signals a player departure ('ayrılık'), not a managerial change |
| 10 | Kayserispor | 2025-10-07 | 1(Y) | 0(Y) | ✅ | ✅ | Article announces a new manager appointment (Jakirovic) for Kayserispor after Gi |

## Disagreements

**Article 3 — Antalyaspor (2025-07-03)**
- Human: score=1, relevant=True
- LLM:   score=4, relevant=True
- LLM reason: Article explicitly states that manager Emre Belözoğlu resigned from Antalyaspor, confirming a firing/resignation has just occurred.

## Prompt design decisions

- **Scale 0–4** captures the full arc from no signal to confirmed change.
- **Appointment articles score 0 / is_relevant=false** — they describe the post-change period, not pre-change expectation.
- **Score 4 = confirmed exit** (firing or resignation) — marks the end of the expectation window.
- **Score 3 = public pressure** (fan protests, explicit board discussion) — strongest pre-change signal.
- **Score 1 = mild signal** (manager deflecting departure questions, brief resolved departure, post-firing replacement speculation).
- **±1 tolerance** used for agreement rate — adjacent scores reflect genuine ambiguity, not model failure.

## Next step

Prompt passes validation. Proceed to full classification of all 2,524 articles.