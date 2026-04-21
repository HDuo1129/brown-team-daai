"""
news/classify_validate.py
==========================
Validate the classifier prompt against 10 hand-labelled articles.
Prints a comparison table and agreement rate.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python news/classify_validate.py
"""

import json
import os
import time
import anthropic
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Hand labels (your scores)
# ---------------------------------------------------------------------------

HAND_LABELS = {
    # news_uid -> (score, is_relevant)
}

# 10 hand-labelled articles (loaded from hand_label_sample.csv + your scores)
HAND_SCORES = [
    # (team, date, body_text, your_score, your_relevant)
    ("Fenerbahce",     "2025-08-07", "Jose Mourinho'dan transfer ve ayrılık yanıtı!",                                                                                    1, True),
    ("Konyaspor",      "2025-10-19", "Taraftardan 'Recep Uçar istifa' sesleri!",                                                                                         3, True),
    ("Antalyaspor",    "2025-07-03", "Emre Belözoğlu'ndan hiç beklenmedik karar! Antalyaspor'dan istifa etmişti, her şey 1 hafta sürdü...",                               1, True),
    ("Genclerbirligi", "2025-12-07", "Gençlerbirliği Teknik Direktörü Volkan Demirel istifa etti",                                                                        4, True),
    ("Galatasaray",    "2026-04-21", "Okan Buruk'tan kupada sürpriz hamle: Gençlerbirliği maçı rotasyon sinyali",                                                         0, False),
    ("Trabzonspor",    "2026-04-21", "Trabzonspor teknik direktörü Fatih Tekke'den beraberlik sonrası oyunculara mesaj! 'Kaldırın kafanızı bırakmak yok'",                0, False),
    ("Besiktas",       "2025-08-29", "Beşiktaş'ın yeni teknik direktörü Sergen Yalçın",                                                                                  0, False),
    ("Fenerbahce",     "2025-09-09", "Fenerbahçe'nin yeni teknik direktörü Domenico Tedesco kimdir?",                                                                     0, True),
    ("Trabzonspor",    "2025-07-01", "Trabzonspor'da ayrılık! Attığı golle hafızalara kazınmıştı",                                                                        0, False),
    ("Kayserispor",    "2025-10-07", "Markus Gisdol'den sonra Kayserispor'un yeni hocası belli oldu mu? Jakirovic etkisi yaratacak...",                                   1, True),
]

# ---------------------------------------------------------------------------
# Prompt (from prompt_classifier.md)
# ---------------------------------------------------------------------------

SYSTEM = """You are a football analyst scoring Turkish Süper Lig news articles for a research project.
Your task: assess how strongly each article signals that a manager change is imminent or has just been confirmed.
Focus only on the manager's job security. Ignore player transfers, match results, and tactical content unless they directly relate to pressure on the manager.
Always return a single JSON object with keys: score (0–4), is_relevant (true/false), reason (one sentence in English)."""

def build_user_prompt(title: str, team: str, date: str) -> str:
    return f"""Article headline: {title}
Team: {team}
Date: {date}

Score this article for manager-change expectation signal."""

# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def classify(client: anthropic.Anthropic, title: str, team: str, date: str) -> dict:
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",   # fast + cheap for validation
        max_tokens=150,
        system=SYSTEM,
        messages=[{"role": "user", "content": build_user_prompt(title, team, date)}],
    )
    raw = msg.content[0].text.strip()
    # Strip markdown fences if present
    raw = raw.strip('`').strip()
    if raw.startswith('json'):
        raw = raw[4:].strip()
    return json.loads(raw)

# ---------------------------------------------------------------------------
# Validation run
# ---------------------------------------------------------------------------

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: set ANTHROPIC_API_KEY environment variable")
        return

    client = anthropic.Anthropic(api_key=api_key)

    print("Running 10 hand-labelled articles through the classifier...\n")
    print(f"{'#':<3} {'Team':<18} {'Date':<12} {'Human':>6} {'LLM':>4} {'Match':>5}  Reason")
    print("-" * 95)

    results = []
    score_matches = 0
    rel_matches   = 0

    for i, (team, date, title, human_score, human_rel) in enumerate(HAND_SCORES, 1):
        try:
            out = classify(client, title, team, date)
            llm_score = int(out.get("score", -1))
            llm_rel   = bool(out.get("is_relevant", False))
            reason    = out.get("reason", "")[:70]

            score_match = abs(llm_score - human_score) <= 1  # allow ±1
            rel_match   = llm_rel == human_rel

            score_matches += score_match
            rel_matches   += rel_match

            match_icon = "✓" if (score_match and rel_match) else ("~" if score_match else "✗")

            print(f"{i:<3} {team:<18} {date:<12} {human_score:>3}({'Y' if human_rel else 'N'})  {llm_score:>2}({'Y' if llm_rel else 'N'})  {match_icon:<5}  {reason}")
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

    pd.DataFrame(results).to_csv(ROOT / 'news' / 'validation_results.csv', index=False)
    print(f"\nResults saved → news/validation_results.csv")

if __name__ == "__main__":
    main()
