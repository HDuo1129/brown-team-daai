# Individual Reflections — Brown Team

**Course:** Data Analysis with AI: Research Support  
**Team:** Duo Huang · Semih Tosun · Farangiz Jurakhonova

---

## Duo Huang (MA, 2nd year)

This project was my first experience using AI as a genuine research collaborator rather than a simple search tool. Having designed the full data pipeline — from Transfermarkt scraping to the final DiD panel — I found that Claude Code dramatically compressed the time needed to translate a design decision into working code. Tasks like building the manager stint overlap join, constructing the event-time index, or generating the expectations panel from raw RSS articles, which would each have taken half a day to debug from scratch, were completed in a fraction of the time. The AI acted as a skilled junior programmer who could read my intent and produce a first draft, leaving me free to focus on whether the logic was economically correct.

That said, I learned quickly that speed without vigilance is dangerous in empirical research. On multiple occasions the AI produced code that ran without errors but was subtly wrong: the `expected_change` threshold was set at 0.5 by default, leaving only one treated observation and making the heterogeneity analysis meaningless — the AI never flagged this as a problem. The pre-trend pattern in the event study (strongly positive coefficients before the manager change) was identified correctly by the model, but the AI's initial framing of it as a "positive finding" had to be pushed back on; what we observe is almost certainly mean reversion, a threat to identification, not evidence that changes work. These moments reminded me that AI assistance raises the technical ceiling but does not replace the researcher's responsibility to think clearly about causal logic.

Looking back, the most valuable shift this course produced in my workflow is the habit of treating AI output as a draft hypothesis rather than a final answer. I now review code with the same skepticism I would apply to a collaborator's first submission: checking the join keys, inspecting the distributions, reading the coefficients against economic priors. The AI is a force multiplier only when the human using it understands what success looks like. For a project of this complexity — 30 seasons, staggered treatment, a novel expectations measure built from Turkish-language news — that understanding cannot be outsourced.

---

## Semih Tosun (MA, 1st year)

My primary contribution to this project was domain validation: bringing football-specific knowledge to bear on decisions that purely data-driven methods would have missed. When the team debated how to define a "mid-season manager change," I was able to provide context on why caretaker appointments are structurally different from strategic replacements — a distinction that directly shaped the 14-day exclusion rule in our treatment definition. Similarly, during the manual validation of the LLM-classified articles, I reviewed Turkish-language headlines to check whether the assigned expectation scores aligned with how Turkish football media actually frames managerial pressure. Several misclassifications that appeared reasonable in English translation were identifiable as errors only with knowledge of Turkish press conventions.

Working alongside AI tools for the first time in a research context, I was struck by how confidently the system produced outputs in domains where it had limited ground truth. The article classifier assigned scores to Turkish headlines with no apparent uncertainty signal, yet on closer inspection several edge cases — ironic tabloid framing, references to rumours that were widely understood to be plant stories — were scored as though the language were straightforward. This experience reinforced for me that human annotation, even a small validation sample, is not a formality but a genuine quality gate. The ≥80% agreement threshold we required before scaling the classifier was the right call, and I would set it higher in future work.

The broader lesson I take from this project is about the division of labour between human and machine in research. AI tools excel at processing volume and generating syntactically correct code; they are much weaker at knowing when a result is implausible given domain context. My role — providing that context for Turkish football — was not glamorous compared to the coding work, but it was where errors were most likely to go undetected. I think this is an underappreciated form of contribution in AI-assisted research, and one that requires genuine expertise to do well.

---

## Farangiz Jurakhonova (MSBA, 1st year)

My engagement with this project was concentrated in the first session, where I contributed to the initial data exploration and descriptive analysis. Reviewing the match-level dataset and the manager stint data at the outset helped the team establish a shared understanding of the data quality issues we would need to address — the mixed date formats across seasons, the clubs with missing Transfermarkt profiles, and the coverage gaps in the earliest seasons. This groundwork, while less visible than the later modelling, was important for setting realistic expectations about what the data could support.

My involvement in Sessions 2 and 3 was limited due to other course commitments, and I am aware that this placed a disproportionate burden on my teammates, particularly Duo Huang, who carried the majority of the implementation work. Reflecting on this, one thing I take from the course is a sharper understanding of how much invisible infrastructure underlies an empirical research project — the scraping, cleaning, validation, and pipeline construction that must happen before any analysis is possible. Watching that process unfold, even partially, gave me a much more grounded appreciation of what "data work" actually involves in practice.

The component of the project I found most intellectually interesting was the design of the LLM classification system for news articles. The decision to validate the classifier against hand-labelled examples before scaling, and the iterative prompt revision that followed, was a concrete illustration of how AI tools require active oversight rather than passive deployment. I intend to carry this principle forward: that using AI in research means building in explicit checks, not assuming that a fluent output is a correct one.

---
