# Evaluation

A small, fixed benchmark for retrieval quality, refusals and citations. It is meant to be
honest, not impressive: read the limitations before quoting any number.

## Documents

All three are works of the U.S. Government, not subject to copyright in the United States
(17 U.S.C. § 105). They are downloaded from the official sources and checked against pinned
SHA-256 hashes; they are not committed to git.

| File | Document | Source |
|---|---|---|
| `NIST.AI.100-1.pdf` | NIST AI Risk Management Framework 1.0 (Jan 2023), 48 pages | [nvlpubs.nist.gov](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf) (doi:10.6028/NIST.AI.100-1) |
| `NIST.CSWP.29.pdf` | NIST Cybersecurity Framework 2.0 (Feb 2024), 32 pages | [nvlpubs.nist.gov](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf) (doi:10.6028/NIST.CSWP.29) |
| `CDOC-110hdoc50.pdf` | The Constitution of the United States, As Amended (H. Doc. 110-50, 2007), 85 pages | [govinfo.gov](https://www.govinfo.gov/content/pkg/CDOC-110hdoc50/pdf/CDOC-110hdoc50.pdf) |

## Questions

[`questions.json`](questions.json) has 30 questions: 25 answerable (9 / 8 / 8 across the three
documents, half phrased close to the source and half paraphrased) and 5 unanswerable (1
off-topic, 4 near-topic or false-premise). Each answerable question lists the document, the
expected **PDF page index** (the viewer's page box, not the printed number) and the exact
supporting phrase. The runner refuses to start if any phrase is not on its page.

All 30 entries were checked by hand against the PDFs on 2026-11-02 (status `VERIFIED`). Results
files record the status and the file's SHA-256, and any change after a run must be logged in
its `changelog`. The file hash changes with any edit, including the header and `verified`
flags, so newer results files also record `questions_content_sha256`, which covers only the
questions and expected answers. It is the same for every committed version so far, including
the commit behind the reported run.

## What is measured

| Measurement | Definition |
|---|---|
| hit@k (strict) | The expected page is among the top-k retrieved chunks (search over all 3 PDFs). The app sends `ASK_TOP_K` chunks to the model (5 in the reported run), so **hit@5 is the number that matches the app**. |
| hit@k (lenient) | Also accepts any other page containing the supporting phrase (e.g. an executive summary or index). Pages are found automatically, not chosen by hand. |
| Top-1 score | Cosine similarity of the best chunk, for answerable vs unanswerable questions. |
| Threshold | `MIN_RELEVANCE_SCORE` that maximizes balanced accuracy (ties go to the lowest cutoff). Reported **in-sample** (chosen on all 30, optimistic) and with **leave-one-out** (chosen on 29, tested on the 30th). |
| Refusals | With the threshold **off**, so the model is measured on its own: unanswerable refused, answerable falsely refused (by reason). The threshold's effect is then simulated from the recorded scores. |
| Citations | Of the answered answerable questions: cites the expected page; cites any page with the phrase; first citation is the expected page. |

## Run it

From `backend/`:

```bash
python -m eval.fetch_docs
python -m eval.run_eval --skip-llm
python -m eval.run_eval
python -m eval.report eval/results/<run>.json
```

- `--skip-llm` needs no API key and makes no LLM calls.
- The full run uses `LLM_PROVIDER` and the model from `.env`. Calls are paced (`--delay`,
  default 6 s), quota/timeout errors (HTTP 503/504) are retried with backoff, and progress is
  saved after every question. If the quota runs out, the runner stops and prints a
  `--resume` command to continue later.
- The eval builds its own index in `eval/.index` and never touches the app's `data/` folder.

## Results

<!--
Paste the output of `python -m eval.report eval/results/<run>.json` here.
Never type or round numbers by hand; regenerate this block from a results file instead.
-->

_Run `20261102-093423` · 2026-11-02T09:34:23+00:00 · commit `d2dcabe` · questions: VERIFIED (30/30 verified) · embeddings `sentence-transformers/all-MiniLM-L6-v2`, chunks 800/150_

**Retrieval** (25 answerable questions; hit = the expected PDF page is among the top-k chunks; lenient also accepts other pages containing the supporting phrase)

| Questions | n | hit@1 | hit@3 | hit@4 | hit@5 |
|---|---:|---:|---:|---:|---:|
| all (strict: expected page) | 25 | 32% | 68% | 72% | 72% |
| all (lenient: any page with the phrase) | 25 | 36% | 68% | 72% | 72% |
| doc=CDOC-110hdoc50.pdf | 8 | 25% | 62% | 62% | 62% |
| doc=NIST.AI.100-1.pdf | 9 | 56% | 67% | 78% | 78% |
| doc=NIST.CSWP.29.pdf | 8 | 12% | 75% | 75% | 75% |
| phrasing=close | 12 | 33% | 83% | 83% | 83% |
| phrasing=paraphrased | 13 | 31% | 54% | 62% | 62% |

**Relevance threshold** (top-1 cosine similarity)

| | min | median | max |
|---|---:|---:|---:|
| Answerable (n=25) | 0.414 | 0.662 | 0.780 |
| Unanswerable (n=5) | 0.176 | 0.402 | 0.485 |

- Threshold chosen on all 30 (in-sample, optimistic): `0.516`, keeps 23/25 (92%) answerable, refuses 5/5 (100%) unanswerable.
- Leave-one-out (out-of-sample): keeps 23/25 (92%) answerable, refuses 4/5 (80%) unanswerable.
- Only 5 unanswerable questions: treat refusal estimates as rough.

**Answering** with `gemini` / `gemini-3.5-flash-lite` (max tokens 1024, threshold off during the run)

| Metric | Result |
|---|---:|
| Unanswerable questions refused | 5/5 (100%) |
| Answerable questions falsely refused | 4/25 (16%) |
| Answers citing the expected page | 17/21 (81%) |
| Answers citing any page that contains the supporting phrase (lenient) | 18/21 (86%) |
| Answers whose first citation is the expected page | 11/21 (52%) |
| With threshold `0.516`: unanswerable refused | 5/5 (100%) |
| With threshold `0.516`: answerable falsely refused | 5/25 (20%) |

### Run-to-run variance

Three full runs are kept in [`results/`](results/); the last one (`20261102-093423`, clean
commit) is the reported run. Nothing is averaged or selected.

| Run | Commit | Refused (unanswerable / answerable) | Cited expected page | First citation is expected page |
|---|---|---:|---:|---:|
| `20261102-071330` | `7c6104d` (dirty) | 5/5, 4/25 | 17/21 | 10/21 |
| `20261102-073742` | `7c6104d` (dirty) | 5/5, 4/25 | 17/21 | 11/21 |
| `20261102-093423` | `d2dcabe` (clean) | 5/5, 4/25 | 17/21 | 11/21 |

Retrieval was identical in all three runs, and so was every refusal decision. Citations varied
on 3 questions (`rmf-07`, `csf-04`, `con-06`), and the answer wording varied more. The prompts
were the same, so this most likely comes from the model's sampling: the app does not set a
seed. "First citation" is the most sensitive metric because it depends on the order in which
the model mentions its sources. For example, `csf-04` cited the same two pages in every run,
but in a different order in run 2.

### Why `MIN_RELEVANCE_SCORE` stays off

`MIN_RELEVANCE_SCORE` is off by default. On this set, a threshold of `0.516` refused all 5
unanswerable questions, but the model had already refused all 5 on its own, so the threshold
added no correct refusals. It did add one false refusal (5/25 instead of 4/25): `con-06`, which
the model answers when the threshold is off.

The threshold was also tuned on the same 30 questions it is scored on, so that result is
optimistic, and 5 unanswerable questions is a small sample. With a different model that refuses
less reliably, the trade-off could differ. The setting remains available for that case.

## Limitations

- **Small sample.** 25 answerable and 5 unanswerable questions. One question changes a rate by
  4 points (answerable) or 20 points (unanswerable); the refusal rate in particular is a rough
  signal, not a precise estimate.
- **Author bias.** The questions were written by the same project that built the system.
- **LLM variance.** LLM output can vary between runs and model versions (see above); each
  results file records the provider, model, settings and git commit.
- **Page-level matching only.** A hit means the right page was retrieved, not that the
  answer text is correct. Answer correctness is not scored automatically.
- **The lenient match is literal.** It looks for the exact supporting phrase, so it misses
  rewordings of the same fact. For example, the Constitution's index says "twenty-five years"
  where the phrase says "twenty five Years", so `con-01`'s citations of the index count as misses.
