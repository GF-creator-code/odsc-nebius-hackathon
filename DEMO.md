# Demo Recording Script (Showcase Surface for the 25% + 30% Criteria)

> Target length 2–3 minutes. Judges explicitly want to see: ① the complete real call pipeline ② the answer + source citations verified live ③ **one insufficient-evidence/failure case** (do not cut it).
> Recording timing: after the Streamlit UI is complete (before the UI is ready, you can rehearse first on the command line with `python agent.py --trace`).

## Opening (~15 seconds)

Visual: the UI's first screen (or the terminal)
Voiceover (in English, for international judges):
> "This is Sourced, a research agent that answers questions with evidence you can verify. Watch the full pipeline run live — no prewritten answers."

**Points to show**: the input box is empty, a clean first screen; if using the command line, type `python agent.py "..." --trace` first so the trace is visible as it runs.

## Scenario 1: Timeliness question — show the full loop (~60–90 seconds)

Question (example; can be swapped): **"What won the 2026 Nobel Prize in Physics, and for what work?"**

Recording points (in order):
1. Enter the question → click Research → **watch the research trace panel scroll live**: the 2–3 planned queries → N new items in round 1 → the "evidence sufficient, stopping search" verdict with its reasoning
2. Answer finishes rendering → **scroll to the citations**: point out that each `[n]` in the answer corresponds one-to-one to the source list at the bottom
3. **Key action: click open 1–2 citation links on the spot** (judges will verify whether the citations genuinely support the claims — the official nobelprize.org page is best)
4. Point out the "qualifier" in the answer (e.g., the "discovery" in the award rationale refers to discovering high-energy neutrinos themselves, not to determining their astrophysical source), voiceover:
   > "It also tells you where evidence is indirect — that limitation is part of the answer."

## Scenario 2: Insufficient-evidence case (~30–45 seconds, must record)

Question (pick one for which adequate evidence genuinely cannot be found; test it in advance — e.g., extremely niche unpublished information):
- Candidate (verified): "What are the actual deployment cases of Huawei Ascend 910C chips in European data centers?" — actual test result: after running all 3 follow-up search rounds, it honestly declared insufficient evidence
- Candidate (verified, used in the recorded video): "What is the location and construction scale of the Nebius data center internally codenamed Aurora-7?" — 3 rounds, 17 sources collected / 12 kept, still declared insufficient evidence; see trace `traces/20261116_161549.md`

Recording points:
1. Ask the question → the trace shows multiple follow-up search rounds (this nicely demonstrates "when to refine the search")
2. Final output shows "[Evidence insufficient] …" along with an explanation of the gap
3. Voiceover:
   > "When the evidence isn't there, it says so and explains what's missing. It never fabricates sources."
4. (If a follow-up round hits the Tavily error path, keep it unedited: it shows errors are handled explicitly rather than silently)

## Scenario 3: Injection-defense design (~20 seconds, bonus)

Voiceover + cut to the `synthesize()` code in `agent.py`:
> "Web content is injected as untrusted data, isolated from system instructions — a source page can't hijack the agent."

(You can pre-plant a page containing embedded instructions in a test question; if a live demo feels too risky, explain via the code instead.)

## Closing (~10 seconds)

Voiceover:
> "Plan, search, judge, answer — with every claim sourced. Repo link in the description."

Visual: stay on the repo homepage (README architecture diagram) for 2 seconds.

## Recording Checklist

- [ ] Record with OBS/PowerPoint, 1080p
- [ ] Open an incognito window in the browser beforehand (avoid autocomplete / personal traces appearing on screen)
- [ ] `.env` and any plaintext keys must **never appear on screen** (watch for environment-variable echo when demoing in a terminal)
- [ ] Run both questions once in advance; confirm quota is sufficient (Tavily 1000 calls/month) and the network is stable
- [ ] Trace files `traces/` already contain real samples and the README already links them; usable as backup footage to cut in
- [ ] English subtitles/voiceover; if the length exceeds 3 minutes, cut Scenario 3
