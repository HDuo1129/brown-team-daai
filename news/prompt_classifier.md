# Prompt Classifier — Manager Change Expectation Signal

## Purpose

Score each news article on how strongly it signals that a Turkish Süper Lig manager
change is **coming or has just been confirmed**. This score will be used as a
pre-change expectation variable in a differences-in-differences analysis.

---

## Scale

| Score | Label | Definition |
|-------|-------|------------|
| 0 | No signal | Routine post-match quote, tactical discussion, team news, player transfer, or appointment of a *new* manager (change already done — not a pre-change signal) |
| 1 | Mild signal | Manager asked about his future, brief/unresolved departure rumours, speculation about replacement after a *previous* manager already left |
| 2 | Moderate signal | Explicit criticism of the manager, poor results framed as his responsibility, board dissatisfaction mentioned |
| 3 | Strong signal | Fans publicly demanding change (protests, chants), credible media reports of board meeting about the manager, named replacement candidates |
| 4 | Confirmed change | Firing, resignation, or mutual termination explicitly confirmed |

**Critical rule:** Appointment articles ("X is the new coach", "who is X?") score **0** because they describe the post-change period, not the pre-change expectation. The variable we want measures how much the press *anticipated* the change, not who replaced the fired manager.

---

## is_relevant

- **true** — Article is about a manager's job security, performance pressure, departure, or the change event itself
- **false** — Article is about player transfers, match tactics, cup draws, squad injuries, or the new appointment (change already happened)

---

## Output format

Always return a single JSON object — no markdown, no prose:

```json
{
  "score": <integer 0–4>,
  "is_relevant": <true|false>,
  "reason": "<one sentence in English explaining the score>"
}
```

---

## Examples (hand-labelled)

```
Article: "Jose Mourinho'dan transfer ve ayrılık yanıtı!"
Team: Fenerbahce | Date: 2025-08-07
→ {"score": 1, "is_relevant": true, "reason": "Manager is answering questions about a potential departure — mild pre-change signal."}

Article: "Taraftardan 'Recep Uçar istifa' sesleri!"
Team: Konyaspor | Date: 2025-10-19
→ {"score": 3, "is_relevant": true, "reason": "Fans publicly demanding the manager's resignation — strong pre-change pressure signal."}

Article: "Emre Belözoğlu'ndan hiç beklenmedik karar! Antalyaspor'dan istifa etmişti, her şey 1 hafta sürdü..."
Team: Antalyaspor | Date: 2025-07-03
→ {"score": 1, "is_relevant": true, "reason": "Brief resignation that was quickly reversed — mild signal, change did not materialise."}

Article: "Gençlerbirliği Teknik Direktörü Volkan Demirel istifa etti"
Team: Genclerbirligi | Date: 2025-12-07
→ {"score": 4, "is_relevant": true, "reason": "Confirmed resignation of the head coach — maximum change signal."}

Article: "Okan Buruk'tan kupada sürpriz hamle: Gençlerbirliği maçı rotasyon sinyali"
Team: Galatasaray | Date: 2026-04-21
→ {"score": 0, "is_relevant": false, "reason": "Tactical rotation decision — no managerial pressure or change signal."}

Article: "Fatih Tekke'den beraberlik sonrası oyunculara mesaj! 'Kaldırın kafanızı bırakmak yok'"
Team: Trabzonspor | Date: 2026-04-21
→ {"score": 0, "is_relevant": false, "reason": "Routine post-match motivational quote — no job security signal."}

Article: "Beşiktaş'ın yeni teknik direktörü Sergen Yalçın"
Team: Besiktas | Date: 2025-08-29
→ {"score": 0, "is_relevant": false, "reason": "Appointment of new manager after change already occurred — post-change, not a pre-change expectation signal."}

Article: "Fenerbahçe'nin yeni teknik direktörü Domenico Tedesco kimdir?"
Team: Fenerbahce | Date: 2025-09-09
→ {"score": 0, "is_relevant": true, "reason": "Profile of newly appointed manager — manager-relevant but no pre-change expectation signal."}

Article: "Trabzonspor'da ayrılık! Attığı golle hafızalara kazınmıştı"
Team: Trabzonspor | Date: 2025-07-01
→ {"score": 0, "is_relevant": false, "reason": "Player departure, not about the manager's job security."}

Article: "Markus Gisdol'den sonra Kayserispor'un yeni hocası belli oldu mu? Jakirovic etkisi yaratacak..."
Team: Kayserispor | Date: 2025-10-07
→ {"score": 1, "is_relevant": true, "reason": "Speculation about replacement after the previous manager left — mild signal for the new managerial period."}
```

---

## System prompt (use as system message)

```
You are a football analyst scoring Turkish Süper Lig news articles for a research project.
Your task: assess how strongly each article signals that a manager change is imminent or has just been confirmed.
Focus only on the manager's job security. Ignore player transfers, match results, and tactical content unless they directly relate to pressure on the manager.
Always return a single JSON object with keys: score (0–4), is_relevant (true/false), reason (one sentence in English).
```

## User prompt template

```
Article headline: {title}
Team: {team}
Date: {date}

Score this article for manager-change expectation signal.
```
