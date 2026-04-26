# Classifier Validation — Interpretation

## Summary

| Metric | Result |
|--------|--------|
| Articles hand-labelled | 10 |
| Score agreement (±1)   | 10/10 = 100% |
| is_relevant agreement  | 10/10 = 100% |
| Both agree             | 100% |
| Target                 | ≥ 80% |
| Status | ✅ PASS — ready to scale |

## Score normalisation

Raw 0–4 → 0–1: 0→0.0, 1→0.25, 2→0.50, 3→0.75, 4→1.0

## Article-level results

| # | Team | Date | Human | LLM | Score ✓ | Rel ✓ | Reason |
|---|------|------|-------|-----|---------|-------|--------|
| 1 | Fenerbahce | 2025-08-07 | 1(Y) | 1(Y) | ✅ | ✅ | Manager answering departure questions — mild signal. |
| 2 | Konyaspor | 2025-10-19 | 3(Y) | 3(Y) | ✅ | ✅ | Fans demanding manager resignation — strong signal. |
| 3 | Antalyaspor | 2025-07-03 | 1(Y) | 1(Y) | ✅ | ✅ | Resignation reversed after one week — mild signal. |
| 4 | Genclerbirligi | 2025-12-07 | 4(Y) | 4(Y) | ✅ | ✅ | Confirmed resignation of head coach. |
| 5 | Galatasaray | 2026-04-21 | 0(N) | 0(N) | ✅ | ✅ | Tactical decision — no managerial pressure. |
| 6 | Trabzonspor | 2026-04-21 | 0(N) | 0(N) | ✅ | ✅ | Manager's post-match message to players — no signal of managerial change. |
| 7 | Besiktas | 2025-08-29 | 0(N) | 0(N) | ✅ | ✅ | New manager appointed — post-change article, score=0. |
| 8 | Fenerbahce | 2025-09-09 | 0(Y) | 0(Y) | ✅ | ✅ | Profile of newly appointed manager — post-change, score=0. |
| 9 | Trabzonspor | 2025-07-01 | 0(N) | 0(N) | ✅ | ✅ | Player departure, not about manager. |
| 10 | Kayserispor | 2025-10-07 | 1(Y) | 1(Y) | ✅ | ✅ | Replacement search after previous manager left — mild signal. |

## Disagreements

None — perfect agreement.

## Next step

Proceed to classify_articles.py.