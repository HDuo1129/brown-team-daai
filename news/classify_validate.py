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
import re
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
Your task: assess how strongly each article signals that a manager change is IMMINENT or HAS JUST BEEN CONFIRMED (firing or resignation only).

SCORING SCALE:
0 = No signal: routine post-match quote, tactical discussion, player transfer, OR new-manager appointment article (change already happened — post-change period, not a pre-change signal)
1 = Mild signal: manager asked about his future, brief/unresolved departure rumours, speculation about replacement after a previous manager already left
2 = Moderate signal: explicit criticism of manager, poor results blamed on him, board dissatisfaction mentioned
3 = Strong signal: fans publicly demanding change (protests, chants), credible reports of board meeting about the manager, named replacement candidates
4 = Confirmed change: firing, resignation, or mutual termination explicitly stated

CRITICAL RULE — APPOINTMENTS SCORE 0:
Articles that announce WHO the new manager is ("X is the new coach", "who is X?", "X appointed") must receive score=0.
These describe the post-change period. Score 4 is ONLY for firing/resignation articles, never for appointment articles.

is_relevant — INDEPENDENT of score. Use these distinctions:
- true: manager's job security, pressure, departure, firing/resignation; OR "who is the new manager?" profile articles; OR articles asking/speculating whether a new coach has been decided; OR manager answering questions about his own future
- false: ONLY articles with no manager-change connection at all — player transfers, match tactics, cup draws, match results with zero managerial angle; OR brief one-line appointment announcements ("X is the new coach" with no further content)

THREE APPOINTMENT CASES — distinguish carefully:
1. "X is the new coach" (pure statement) → score=0, is_relevant=false (no content beyond the fact)
2. "Who is X? / What will X bring?" (new-manager profile) → score=0, is_relevant=true (manager-focused content)
3. "Has the new coach been decided yet? / Will X be appointed?" (question/speculation) → score=1, is_relevant=true (still in the expectation window, change not yet confirmed)

Return ONLY a single JSON object — no markdown, no extra text:
{"score": <0-4>, "is_relevant": <true|false>, "reason": "<one sentence in English>"}"""

def build_user_prompt(title: str, team: str, date: str, body: str = "") -> str:
    if body and body.strip():
        text_section = f"Article headline: {title}\nArticle body:\n{body.strip()[:1500]}"
    else:
        text_section = f"Article headline: {title}"
    return f"""{text_section}
Team: {team}
Date: {date}

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

def classify(client: anthropic.Anthropic, title: str, team: str, date: str, body: str = "") -> dict:
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",   # fast + cheap for validation
        max_tokens=150,
        system=SYSTEM,
        messages=[{"role": "user", "content": build_user_prompt(title, team, date, body)}],
    )
    raw = msg.content[0].text.strip()
    # Extract first JSON object, ignoring any extra text before/after
    match = re.search(r'\{.*?\}', raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(raw)


def write_results_csv(results: list[dict]) -> None:
    pd.DataFrame(results).to_csv(ROOT / "news" / "validation_results.csv", index=False)


    # Load body text lookup from articles_text.csv (keyed by cleaned title)
    text_csv = ROOT / 'news' / 'articles_text.csv'
    body_lookup: dict[str, str] = {}
    if text_csv.exists():
        df_text = pd.read_csv(text_csv)
        for _, row in df_text.iterrows():
            if row.get('body_available') and str(row.get('body', '')).strip():
                body_lookup[str(row['title']).strip()] = str(row['body'])

    print("Running 10 hand-labelled articles through the classifier...\n")
    print(f"{'#':<3} {'Team':<18} {'Date':<12} {'Human':>6} {'LLM':>4} {'Match':>5} {'Src':<5}  Reason")
    print("-" * 100)

    results = []
    score_matches = 0
    rel_matches   = 0

    for i, (team, date, title, human_score, human_rel) in enumerate(HAND_SCORES, 1):
        try:
            body = body_lookup.get(title.strip(), "")
            out = classify(client, title, team, date, body)
            llm_score = int(out.get("score", -1))
            llm_rel   = bool(out.get("is_relevant", False))
            reason    = out.get("reason", "")[:70]

            score_match = abs(llm_score - human_score) <= 1  # allow ±1
            rel_match   = llm_rel == human_rel

            score_matches += score_match
            rel_matches   += rel_match

            match_icon = "✓" if (score_match and rel_match) else ("~" if score_match else "✗")
            src_tag = "body" if body else "title"

            print(f"{i:<3} {team:<18} {date:<12} {human_score:>3}({'Y' if human_rel else 'N'})  {llm_score:>2}({'Y' if llm_rel else 'N'})  {match_icon:<5} {src_tag:<5}  {reason}")
            results.append({
                "article": i, "team": team, "date": date,
                "human_score": human_score, "human_relevant": human_rel,
                "llm_score": llm_score, "llm_relevant": llm_rel,
                "score_match": score_match, "rel_match": rel_match,
                "reason": out.get("reason",""),
            })
        except Exception as e:
            print(f"{i:<3} {team:<18} {date:<12}  ERROR: {e}")
        time.sleep(0.5)

    print("-" * 95)
    score_agree = score_matches / len(HAND_SCORES) * 100
    rel_agree   = rel_matches   / len(HAND_SCORES) * 100
    both_agree  = sum(1 for r in results if r['score_match'] and r['rel_match']) / len(HAND_SCORES) * 100

    print(f"\nAgreement (score ±1):     {score_matches}/{len(HAND_SCORES)} = {score_agree:.0f}%")
    print(f"Agreement (is_relevant):  {rel_matches}/{len(HAND_SCORES)} = {rel_agree:.0f}%")
    print(f"Agreement (both):         {both_agree:.0f}%")

    if both_agree >= 80:
        print("\n✓  Agreement ≥ 80% — prompt is ready for full classification run.")
    else:
        print("\n✗  Agreement < 80% — review disagreements above and revise the prompt.")

    results_df = pd.DataFrame(results)
    csv_path = ROOT / 'news' / 'validation_results.csv'
    results_df.to_csv(csv_path, index=False)
    print(f"\nResults saved → news/validation_results.csv")

    # ── Write interpretation report ───────────────────────────────────────
    md_path = ROOT / 'news' / 'validation_interpretation.md'

    disagreements = [r for r in results if not (r['score_match'] and r['rel_match'])]

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
