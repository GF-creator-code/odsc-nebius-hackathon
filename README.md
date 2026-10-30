# Sourced · A Research Agent That Brings Its Sources

> Turning a question into a **sourced, verifiable answer** — every claim carries a citation you can open and check.

ODSC × Nebius Hackathon 2026 · Team **KK_yuanqu** · Oct 28 – Nov 20

**Sourced** is a research agent for anyone who needs answers they can defend — students writing papers, analysts briefing clients, engineers comparing technologies. Search engines give you links; chatbots give you confident prose. Sourced gives you a synthesized answer where **every factual claim is tied to a numbered, clickable source**, and when the evidence isn't there, it says so instead of inventing.

## How it works

```mermaid
flowchart TD
    Q[User question] --> P[Plan: LLM generates 2-3 complementary queries<br/>zh + en coverage]
    P --> S[Search: Tavily real-time web search<br/>dedupe by URL, cap pool at 12]
    S --> J{Judge: LLM evaluates<br/>is the evidence sufficient?}
    J -- "insufficient" --> F[Refine: 1-2 targeted follow-up queries<br/>max 3 rounds total]
    F --> S
    J -- sufficient --> A[Synthesize: evidence injected as UNTRUSTED data,<br/>separate from trusted system instructions]
    A --> R[Answer with inline [n] citations<br/>+ numbered source list]
    J -- "search failed / empty" --> X[Honestly report insufficient evidence<br/>never fabricate]
```

**The research loop is visible.** Every run prints (and with `--trace` saves) its full decision trace: what queries were planned, how many sources each round added, why the agent stopped searching, and what the final answer cites. See [a real trace](traces/20261029_201654.md).

### Design decisions, mapped to what good research looks like

| Decision | Why |
|---|---|
| Citations `[n]` must resolve to a real URL in the source list — no dangling refs | A citation that can't be opened is decoration, not evidence |
| Judge step decides *continue vs stop* searching (max 3 rounds) | More searches ≠ better answers; stop when evidence converges |
| Web content is injected as **untrusted data**, never merged into system instructions | Source pages may contain prompt-injection attempts |
| Search failures, empty pools, and thin evidence are **reported, never smoothed over** | "I couldn't verify this" is a valid research output; hallucinated certainty is not |
| Conflicting sources are surfaced in the answer, not averaged away | Reviewers need to know where evidence disagrees |

## Quick start

Requirements: Python 3.10+, a [Tavily](https://app.tavily.com) API key (free tier: 1,000 calls/month), and any OpenAI-compatible inference key.

```bash
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
# edit .env:
#   TAVILY_API_KEY=tvly-...                          (from app.tavily.com)
#   LLM_BASE_URL=https://api.tokenfactory.nebius.com/v1
#   LLM_API_KEY=...                                  (Nebius Token Factory)
#   LLM_MODEL=MiniMaxAI/MiniMax-M3

python test_tavily.py       # verifies the search path end-to-end
```

**Web UI** (recommended):

```bash
streamlit run app.py        # or: python -m streamlit run app.py
```

Type a question, watch the live research trace (planning → search rounds → sufficiency judgment → source ranking), get an answer with **clickable inline citations**, and an honest warning when evidence is insufficient.

**CLI** (same core, thin adapter):

```bash
python agent.py "What won the 2026 Nobel Prize in Physics, and for what work?"
python agent.py "..." --trace      # also saves the research trace to traces/
```

The inference layer is deliberately pluggable (`llm.py`): switching providers — e.g. to Nebius Token Factory — is a three-line `.env` change, no code edits. API keys live only in `.env`, which is git-ignored.

### Example output (real run)

> **结论：**2026年诺贝尔物理学奖授予弗朗西斯·哈尔岑（Francis Halzen），获奖理由是"对冰立方中微子天文台（IceCube Neutrino Observatory）的决定性贡献，以及发现具有天体物理起源的高能中微子"[5][8]。……
> **一点必要的限定：**委员会同时指出，这些超高能中微子目前尚未有确定的源被证认，只有很强的迹象[7]。因此，获奖理由中的"发现"指的是发现这些高能中微子本身，而非确定其具体天体源[7]。
>
> 来源：[1] RFI … [5] Nobel Prize official announcement … [7] nobelprize.org/prizes/physics/2026/prize-announcement …

Notice the shape of the answer: conclusion first, claims cited, and an explicit limitation where the evidence is indirect — that paragraph is the product.

### Verified runs — three real traces

Every run below is a saved trace in [`traces/`](traces/), produced by an unmodified `agent.py` against live Tavily + LLM endpoints.

| Trace | Question | Rounds (pool size) | Sources cited | Outcome |
|---|---|---|---|---|
| [`20261030_163023`](traces/20261030_163023.md) | China vs India 2026 GDP | 3 (8 → 11 → 14) | 12 | Converged — coverage checklist fully satisfied |
| [`20261030_150405`](traces/20261030_150405.md) | Current policy rates of major central banks | 3 (5 → 9 → 11) | 11 | Answered **with an explicit conflict warning** |
| [`20261030_204806`](traces/20261030_204806.md) | Huawei Ascend 910C deployments in European data centres | 3 (9 → 11 → 14) | 12 | **Insufficient evidence — stated, not invented** |

**What each run demonstrates**

1. **Targeted follow-up, not blind re-searching.** In the GDP run the judge decomposed the question into sub-questions, found *India's 2026 GDP level* unsupported after round 1, and issued a query aimed at exactly that gap; round 2 filled it. Rounds are driven by per-sub-question coverage, not a fixed schedule.
2. **Source ranking is observable, never silent.** The GDP trace demoted 3 social-platform sources to the tail, then capped the pool 14 → 12 and recorded **which** entries were dropped (two Facebook posts). The Ascend run dropped two `cn.investing.com` pages the same way. Discards are named in the trace.
3. **"I couldn't verify this" is a valid output.** The Ascend 910C question exhausted all 3 rounds without a single European deployment case. The agent said so, explained why each source failed to qualify ([1][2] are China-domestic, [5][6] don't mention the 910C), and listed what evidence would settle it.
4. **Conflicts are surfaced, not averaged away.** The central-bank run found rates spanning Sept 2025 – Oct 2026 with contradictory figures for the same bank, and reported the spread instead of picking one number.

> **Why some questions take longer.** A slower run is the agent gathering more rounds of evidence, not a performance problem: each extra round is one more search plus one sufficiency evaluation. English questions on well-documented facts often converge in 1 round (~40 s); sparse or region-specific topics typically run the full 3 (~2 min).


## Repository layout

The core loop is a single event-stream generator (`agent.research_events`); CLI and Web UI are thin adapters over the same events — swap either without touching the core.

| File | Role |
|---|---|
| `agent.py` | Core research loop (plan → search → judge → rank → synthesize) emitting events; CLI adapter; citation linkify |
| `quality.py` | Source-quality ranking: demotes social/aggregator domains (never deletes) |
| `websearch.py` | Tavily client with retries, explicit failure modes (auth / quota / network) |
| `llm.py` | Pluggable OpenAI-compatible inference client |
| `app.py` | Streamlit UI: live trace, clickable citations, honest insufficient-evidence state |
| `tests/test_pure.py` | Offline unit tests (JSON tolerance, ranking, linkify, caps) — no API spend |
| `traces/` | Saved research traces from real runs, used as demo material |

## Error handling policy

The agent never silently degrades: auth errors, quota exhaustion, malformed responses, and empty result pools each raise a specific, actionable error; when searches fail or evidence is thin, the final output says so plainly and identifies what's missing. Fabricated facts or citations are treated as the worst possible failure mode.

## Status & roadmap

- [x] Core loop: multi-round search with sufficiency judging, citation discipline, trace files
- [x] Robustness: retries with backoff, response validation, UTF-8 console, prompt-size caps
- [x] Source-quality ranking (social/aggregator demotion, never silent deletion)
- [x] Web UI (Streamlit): clickable citations, live research trace
- [x] Offline test suite
- [x] **Inference on Nebius Token Factory** — live on `https://api.tokenfactory.nebius.com/v1` with `MiniMaxAI/MiniMax-M3`; three-line `.env` switch (see `.env.example`)
- [ ] Demo video

## Team

KK_yuanqu — [GF-creator-code](https://github.com/GF-creator-code) · [Hkate777](https://github.com/Hkate777)

---

### 中文速览（团队内部）

研究型 Agent：问题 → 规划查询 → Tavily 实时搜索（去重）→ 证据充分性评估（不足则定向补搜，最多 3 轮）→ 带行内 `[n]` 引用的综合回答 + 编号来源列表。证据不足时如实声明，绝不编造；网页内容作为不可信数据与系统指令隔离（防提示注入）。运行 `python agent.py "问题" --trace` 可保存完整研究轨迹。开发规范见 [AGENTS.md](AGENTS.md)。
