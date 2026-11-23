# Known limits

What the model does not do, or does in a simplified way. The “Assumptions & evidence” drawer shows this list as it is.

- Swiss figures marked “[to be verified]” are not verified (AVS, unemployment insurance, 2nd pillar, health insurance, university fee, purchase costs, imputed rental value).
- Income tax: an illustrative scale, not the scale of the canton of Vaud; no instalments; married couples are not modelled.
- Unemployment: the length of the benefit is not capped; the scheme for people coming out of their studies is not modelled.
- 2nd pillar: no ceiling on the coordinated salary; the withdrawal for a home is not taxed separately.
- Housing: no resale; imputed rental value, whose abolition was voted in 2025 (date to be verified).
- Investments in CHF only; GBP and SGD are approximated by EUR.
- Amounts are in today's CHF (zero inflation by convention, real salary increases).
- Seven named worlds: the reference world, five crises taken from the catalogue and the loss of the student job (a crisis of the team, 6 months long by assumption, with no benefit). The age of each crisis can be set from 21 to 29. No Monte Carlo and no crises calibrated on real data; the franc shock of the 2015 kind is not written.
- Combined crises: a world holds two crises at most (“krach@24+chomage_long@25”), never three. Where both act on the same quantity in the same month, their gaps to the reference world are added: this is a convention, not a measured law; two job losses that overlap count as one. Nothing says how often two crises come together. A combined world is only tested when it is asked for: it is not among the seven worlds shown by default, its ages cannot be set on screen, and the value table keeps one crisis per world.
- Abroad, income tax is part of the single 22% deduction, whereas in Switzerland it comes on top of the net salary: this slightly favours the line abroad.
- Blocks not translated: PhD, internship, self-employment, company, break, Zurich, Geneva. No borrowing ceiling.
- Observed savings: one junction at a time; the same value is applied in every tested world; the gap with the simulated savings is a line of the ledger, with no explanation of its cause. The threshold of the signpost stays the one of the simulated route.
- The value of a degree beyond the age of 30 is not measured by the six goals; comparing at 30 penalises the master's. At 30, in every tested world, the master's lowers the financial results: with no shock, 3 goals out of 6 and 96'749 CHF with the master's of the demo story, 6 out of 6 and 175'904 CHF without it.
- Policies: a single threshold, on a single quantity (what Alexia has set aside), at a single date. A shock that comes after the last decision date does not show in the savings (twelve months of unemployment at 27: the three policies follow the plan, 1 goal out of 6). The thresholds are calibrated on four worlds, for a single goal (“Career change”); the working zones are narrow (2'600 CHF at 26). The randomly drawn variants are counts, not expected frequencies.
- Three bands: the “worst tested world” only holds for the tested worlds; the “cautious” world only changes the return on investments (one point less per year), which weighs little as long as Alexia has few investments. No band is a promise.
- Fragile Alexia only differs by her starting savings (2'000 CHF instead of 8'000): same income, same expenses, same thresholds, calibrated on Alexia.
- Widespread rule put to the test: the cushion is counted on the account alone, with no investments to sell; “holding” means not going into the red for 24 months; current expenses are housing, living costs and health, without tuition. Two states only, at a single age (25).
- AI layer: the model proposes worlds or settings and writes sentences; it computes nothing. The checker verifies that every figure of a text comes from the engine and from the right world, and for three quantities (goals kept, goals lost, peak borrowing) that it stands in the right place. It does not verify the reasoning of the words around the figures.
- “Find what breaks my plan”: the search tests 40 worlds out of 49'140, so it can miss the hardest one. The engine simulates the 315 single crises itself and says when one of them is harder; the full scan of the 49'140 worlds exists for three routes only, with unchanged assumptions.
- “Ask in your own words”: one sentence at a time, read into the settings Doors already has. A number is looked for in the sentence, not its role in it: this is why every setting is shown before anything is computed.
- Outside the live mode, the answers of the model are recordings, played again and checked again on the engine: a route or a sentence with no recording has no answer. The AI layer has not yet been evaluated with a real model in this repository: no answer is recorded, and the benchmark of the search has only been run with a stand-in.
- Synthetic data: they do not represent the Swiss population.
