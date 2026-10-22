# Decisions: why each piece exists

Every piece below has a cost. For each one: what made it necessary (the trigger), what it costs (the
trade-off) and what it gives back (the benefit). If a piece had no trigger, it is not in the repository.
The last table lists what I left out on purpose.

## Pieces in the repository

| piece | trigger | trade-off | benefit |
|---|---|---|---|
| Python standard library only, no packages | "It must run from a clean checkout." Every package is an install step that can fail on the reviewer's machine. | Schema validation and the bootstrap are hand-written (about 60 lines). No pandas, no pydantic. | `python3 run.py --offline` is the whole setup. |
| Synthetic data instead of Plaid Sandbox (`fundo/generate.py`) | Sandbox users do not carry the cases that cost a funder money: stacked advances, R01 returns at a bank with no NSF fee, a funder that writes to the reviewer. I had to write those cases anyway. | I wrote both the data and the prompt, so the results flatter the reviewer. The holdout split limits this. It does not remove it. | Every case has a known truth and a scenario tag, so each error can be traced to a cause. |
| Two splits, dev and holdout | I wrote the prompt while I looked at dev results. A score on the same data cannot tell a better prompt from a prompt fitted to that data. | 5 businesses are a small holdout. Its intervals are wide. | Stage 3 of the gate has data that no prompt decision used. |
| A legacy engine that is wrong on purpose (`fundo/engine.py`) | The brief asks for one. | None. The keyword lists were written once and never tuned. | The reviewer is tested against real keyword failure modes: punctuation, collisions, missing words. |
| Patterns: one model call per (business, direction, template, keyword label) | 1,854 dev transactions, most of them repeats (daily payouts, daily repayments). One call per transaction is 10 times the calls and lets two copies of the same payment get two answers. | One answer covers every member of a pattern. A credit above 4 times its template's median becomes its own pattern, so a loan inside small payments is still seen. | 188 calls for 1,854 transactions, consistent labels, and an underwriter queue of patterns, not of rows. |
| No keyword prefilter: every pattern goes to the model | A prefilter that picks "suspicious" transactions is a second keyword list. It misses what the first list misses (an unknown sportsbook, a new funder). | More calls, and more chances for a false flag. U1 in EVAL.md measures this cost. | Recall does not depend on a word list. |
| Own-account transfers paired in code | A model sees one transaction. The two legs of a transfer are a join on amount, date and account. | The rule needs both legs in the file, within one day. | Exact, free and auditable. It uses day numbers, so a transfer across a 30-day month end pairs. |
| Personal data removed before the prompt (`redact`) | Counterparty memos carry emails and phone numbers. The model does not need them. | A regex can miss a format. Hard rule H1 checks the prompts against the tagged values, independently of the regex. | Less personal data at a third party. |
| Untrusted text: a named field, a code tripwire, a model flag, and a policy | Part of each description is written by the counterparty. | The tripwire (`INJECTION_RE`) has false positives: a customer memo "IGNORE PREV INVOICE" goes to a person. | A followed injection cannot raise an offer: flagged text never auto-applies a change in the business's favour. One call per pattern, so one injection cannot touch other transactions. |
| Revenue derived in code, never by the model | Revenue is arithmetic over (direction, group, business flag). | None. | The model cannot set revenue, even when it is fooled. |
| JSON schema, validation in code, one retry, then the keyword label | Models return invalid output, and providers go down. | A pattern with two invalid replies keeps its keyword label (`unreviewed`). | No decision waits for the model, and no invalid reply reaches a label. |
| Asymmetric policy: 0.90 to raise an offer, 0.70 to lower it, provisional apply for doubts that lower it | Part 2: a false revenue dollar costs principal; a false risk label costs margin. | Thresholds are a risk order, not calibrated probabilities. | The cautious label is in force while a person decides. |
| Committed response cache (`cache/llm_responses.jsonl`) | The brief asks for it. It is also the store that Part 3 needs to replay a decision. | The file grows with every prompt change. | Byte-identical output with no key, and an audit trail of every reply with model, tokens, cost and time. |
| Claude through the Claude Code CLI | I had a Claude subscription and no API key for a hosted model. | The CLI adds a preamble to the prompt (more tokens), starts a process per call, and has no temperature setting. The cache removes the nondeterminism from replays. | Haiku and Sonnet compared on the same prompt with no extra spend. With `ANTHROPIC_API_KEY` the same code bills an API key. |
| DeepSeek Flash as a second-provider challenger, thinking off and on | Sonnet showed that a larger Claude model does not win. The open question was whether a cheaper model from another provider, or more reasoning per call, does. | A second code path (HTTP, about 20 lines, standard library). Its JSON mode does not enforce the schema, so validation and the retry carry more weight. The API reports tokens, not dollars, so `llm.py` holds a price table that can go stale. | The gate compares a model from another provider on the same contract for USD 0.16. Thinking turns an under-confident model into the best challenger on cost and queue, and the gate still names the one pattern that keeps it out. |
| 4 calls in flight (`ThreadPoolExecutor`) | About 290 calls per model at 3 to 5 s each: 20 minutes per model one at a time. | A lock around the cache. | About 5 minutes per model. |
| `manifest` in every `metrics.json` | Part 3: "Can you reproduce the original decision?" | A few hashes per run. | A run names its inputs, keyword lists, prompt, schema, policy, served model and replies. |
| The release gate (`gate.py`, EVAL.md) | The brief asks for "the gate that decides when it may change a live decision". A prompt or model change needs a rule that is written down before the results. | About 150 lines and a bootstrap that runs in seconds. | A change is merged, blocked or marked inconclusive by numbers set in advance. |
| CI workflow (`.github/workflows/gate.yml`) | A gate protects only if it runs on every change without a person remembering it. | One YAML file. | Every push proves the outputs reproduce. Every pull request runs the gate. |
| `review.py` for a file of your own | The debrief runs the code on transactions that the reviewers bring. | It tolerates missing Plaid fields with warnings, which is extra code. | One command reviews any `/transactions/get` response. |

## Left out on purpose

| not used | why not |
|---|---|
| Agent framework, LangChain and similar | One prompt, one call per pattern, a fixed pipeline. A framework adds dependencies and hides the prompt. |
| Vector database, embeddings, retrieval | No document collection to search. The context of a pattern fits in one prompt. |
| Fine-tuning | No labelled production data. Underwriter corrections become keyword fixes first (Part 3). |
| A larger model for every call | Sonnet is in the comparison. The gate decides from the numbers (SOLUTION.md, model choice). |
| Batching all patterns of a business into one call | Fewer calls, but one injected description could change the labels of other transactions. |
| Unit tests | The full run against ground truth is the end-to-end test. Its output is committed and CI regenerates it byte for byte. |
