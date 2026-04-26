"""
news/classify_validate.py
==========================
Validate the classifier prompt against 10 hand-labelled articles.
Prints a comparison table and agreement rate.
Writes: news/validation_results.csv  news/validation_interpretation.md

Usage:
    export GROQ_API_KEY=gsk_...
    python news/classify_validate.py
"""

import json
import os
import time
import groq
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent

HAND_SCORES = [
    # (team, date, title, human_score, human_relevant)
    ("Fenerbahce",     "2025-08-07", "Jose Mourinho'dan transfer ve ayrılık yanıtı!",                                                                    1, True),
    ("Konyaspor",      "2025-10-19", "Taraftardan 'Recep Uçar istifa' sesleri!",                                                                         3, True),
    ("Antalyaspor",    "2025-07-03", "Emre Belözoğlu'ndan hiç beklenmedik karar! Antalyaspor'dan istifa etmişti, her şey 1 hafta sürdü...",               1, True),
    ("Genclerbirligi", "2025-12-07", "Gençlerbirliği Teknik Direktörü Volkan Demirel istifa etti",                                                        4, True),
    ("Galatasaray",    "2026-04-21", "Okan Buruk'tan kupada sürpriz hamle: Gençlerbirliği maçı rotasyon sinyali",                                         0, False),
    ("Trabzonspor",    "2026-04-21", "Trabzonspor teknik direktörü Fatih Tekke'den beraberlik sonrası oyunculara mesaj! 'Kaldırın kafanızı bırakmak yok'", 0, False),
    ("Besiktas",       "2025-08-29", "Beşiktaş'ın yeni teknik direktörü Sergen Yalçın",                                                                   0, False),
    ("Fenerbahce",     "2025-09-09", "Fenerbahçe'nin yeni teknik direktörü Domenico Tedesco kimdir?",                                                      0, True),
    ("Trabzonspor",    "2025-07-01", "Trabzonspor'da ayrılık! Attığı golle hafızalara kazınmıştı",                                                         0, False),
    ("Kayserispor",    "2025-10-07", "Markus Gisdol'den sonra Kayserispor'un yeni hocası belli oldu mu? Jakirovic etkisi yaratacak...",                    1, True),
]

SYSTEM = """You are a football analyst scoring Turkish Süper Lig news articles for a research project.

TASK: Score each article on how strongly it signals a manager change is COMING. Return ONLY JSON.

SCORE SCALE (0–4):
0 = No signal: routine quote, tactics, player news, OR new-manager appointment (change already done)
1 = Mild signal: manager fielding departure questions, reversed rumour, post-dismissal replacement search
2 = Moderate signal: explicit board/media criticism, poor results blamed on manager
3 = Strong signal: fan protests demanding change, named replacement candidates, board meeting reports
4 = Confirmed change: firing/resignation confirmed as happening NOW in this article

CRITICAL RULES:
- "yeni teknik direktör X" / "X is the new coach" / "Who is X?" → score=0 (post-change appointment)
- Resignation reversed/lasted 1 week → score=1 (change did not happen)
- Searching for new coach AFTER previous was fired → score=1
- Score=4 ONLY when the headline itself confirms the departure is happening right now

OUTPUT: return exactly this JSON object, no other text:
{"score": <0-4>, "is_relevant": <true/false>, "reason": "<one sentence in English>"}

EXAMPLES:
"Jose Mourinho'dan transfer ve ayrılık yanıtı!" → {"score": 1, "is_relevant": true, "reason": "Manager answering departure questions — mild signal."}
"Taraftardan 'Recep Uçar istifa' sesleri!" → {"score": 3, "is_relevant": true, "reason": "Fans demanding manager resignation — strong signal."}
"Emre Belözoğlu'ndan hiç beklenmedik karar! istifa etmişti, her şey 1 hafta sürdü..." → {"score": 1, "is_relevant": true, "reason": "Resignation reversed after one week — mild signal."}
"Gençlerbirliği Teknik Direktörü Volkan Demirel istifa etti" → {"score": 4, "is_relevant": true, "reason": "Confirmed resignation of head coach."}
"Okan Buruk'tan kupada sürpriz hamle: rotasyon sinyali" → {"score": 0, "is_relevant": false, "reason": "Tactical decision — no managerial pressure."}
"Beşiktaş'ın yeni teknik direktörü Sergen Yalçın" → {"score": 0, "is_relevant": false, "reason": "New manager appointed — post-change article, score=0."}
"Fenerbahçe'nin yeni teknik direktörü Domenico Tedesco kimdir?" → {"score": 0, "is_relevant": true, "reason": "Profile of newly appointed manager — post-change, score=0."}
"Trabzonspor'da ayrılık! Attığı golle hafızalara kazınmıştı" → {"score": 0, "is_relevant": false, "reason": "Player departure, not about manager."}
"Markus Gisdol'den sonra Kayserispor'un yeni hocası belli oldu mu?" → {"score": 1, "is_relevant": true, "reason": "Replacement search after previous manager left — mild signal."}"""

SCALE      = {0: 0.0, 1: 0.25, 2: 0.5, 3: 0.75, 4: 1.0}
USER_TMPL  = "Article headline: {title}\nTeam: {team}\nDate: {date}\n\nScore this article."
MODEL      = "llama-3.3-70b-versatile"


def classify(client: groq.Groq, title: str, team: str, date: str) -> dict:
    r = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": USER_TMPL.format(title=title, team=team, date=date)},
        ],
        max_tokens=200,
        temperature=0.0,
    )
    raw = r.choices[0].message.content.strip().strip("`").strip()
    if raw.lower().startswith("json"):
        raw = raw[4:].strip()
    return json.loads(raw)


def write_results_csv(results: list[dict]) -> None:
    pd.DataFrame(results).to_csv(ROOT / "news" / "validation_results.csv", index=False)


def write_interpretation_md(results: list[dict], score_matches: int, rel_matches: int) -> None:
    n     = len(HAND_SCORES)
    s_pct = score_matches / n * 100
    r_pct = rel_matches   / n * 100
    both  = sum(1 for r in results if r["score_match"] and r["rel_match"]) / n * 100
    ok    = both >= 80

    lines = [
        "# Classifier Validation — Interpretation", "",
        "## Summary", "",
        "| Metric | Result |", "|--------|--------|",
        f"| Articles hand-labelled | {n} |",
        f"| Score agreement (±1)   | {score_matches}/{n} = {s_pct:.0f}% |",
        f"| is_relevant agreement  | {rel_matches}/{n} = {r_pct:.0f}% |",
        f"| Both agree             | {both:.0f}% |",
        f"| Target                 | ≥ 80% |",
        f"| Status | {'✅ PASS — ready to scale' if ok else '❌ FAIL — revise prompt'} |",
        "", "## Score normalisation", "",
        "Raw 0–4 → 0–1: 0→0.0, 1→0.25, 2→0.50, 3→0.75, 4→1.0",
        "", "## Article-level results", "",
        "| # | Team | Date | Human | LLM | Score ✓ | Rel ✓ | Reason |",
        "|---|------|------|-------|-----|---------|-------|--------|",
    ]
    for r in results:
        h = f"{r['human_score']}({'Y' if r['human_relevant'] else 'N'})"
        l = f"{r['llm_score']}({'Y' if r['llm_relevant'] else 'N'})"
        lines.append(
            f"| {r['article']} | {r['team']} | {r['date']} | {h} | {l} | "
            f"{'✅' if r['score_match'] else '❌'} | {'✅' if r['rel_match'] else '❌'} | {r['reason'][:80]} |"
        )
    disagree = [r for r in results if not (r["score_match"] and r["rel_match"])]
    lines += ["", "## Disagreements", ""]
    if not disagree:
        lines.append("None — perfect agreement.")
    else:
        for r in disagree:
            lines += [f"**#{r['article']} {r['team']} {r['date']}** — Human {r['human_score']}, LLM {r['llm_score']}: {r['reason']}", ""]
    lines += ["", "## Next step", "",
              "Proceed to classify_articles.py." if ok else "Agreement < 80% — revise SYSTEM prompt."]
    (ROOT / "news" / "validation_interpretation.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not set. Get a free key at console.groq.com")

    client = groq.Groq(api_key=api_key)
    print(f"Validating {len(HAND_SCORES)} hand-labelled articles via {MODEL}...\n")
    print(f"{'#':<3} {'Team':<18} {'Date':<12} {'Human':>6} {'LLM':>4} {'':>5}  Reason")
    print("-" * 95)

    results, score_matches, rel_matches = [], 0, 0
    for i, (team, date, title, human_score, human_rel) in enumerate(HAND_SCORES, 1):
        try:
            out       = classify(client, title, team, date)
            llm_score = int(out.get("score", -1))
            llm_rel   = bool(out.get("is_relevant", False))
            reason    = out.get("reason", "")
            sm = abs(llm_score - human_score) <= 1
            rm = llm_rel == human_rel
            score_matches += sm
            rel_matches   += rm
            icon = "✓" if (sm and rm) else ("~" if sm else "✗")
            print(f"{i:<3} {team:<18} {date:<12} {human_score:>3}({'Y' if human_rel else 'N'})  "
                  f"{llm_score:>2}({'Y' if llm_rel else 'N'})  {icon:<5}  {reason[:65]}")
            results.append({"article": i, "team": team, "date": date,
                            "human_score": human_score, "human_relevant": human_rel,
                            "llm_score": llm_score, "llm_relevant": llm_rel,
                            "score_match": sm, "rel_match": rm, "reason": reason})
        except Exception as e:
            print(f"{i:<3} {team:<18} {date:<12}  ERROR: {e}")
        time.sleep(2)

    print("-" * 95)
    both = sum(1 for r in results if r["score_match"] and r["rel_match"])
    print(f"\nAgreement (score ±1):    {score_matches}/{len(HAND_SCORES)} = {score_matches/len(HAND_SCORES)*100:.0f}%")
    print(f"Agreement (is_relevant): {rel_matches}/{len(HAND_SCORES)} = {rel_matches/len(HAND_SCORES)*100:.0f}%")
    print(f"Agreement (both):        {both/len(HAND_SCORES)*100:.0f}%")
    write_results_csv(results)
    write_interpretation_md(results, score_matches, rel_matches)
    print("\nSaved → news/validation_results.csv  news/validation_interpretation.md")


if __name__ == "__main__":
    main()
