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

The set is `UNVERIFIED` until a human checks every entry; results files record the status and
the file's SHA-256, and any change after a run must be logged in its `changelog`.

## What is measured

| Measurement | Definition |
|---|---|
| hit@k (strict) | The expected page is among the top-k retrieved chunks (search over all 3 PDFs). |
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

_No full run recorded yet._

## Limitations

- **Small sample.** 25 answerable and 5 unanswerable questions. One question changes a rate by
  4 points (answerable) or 20 points (unanswerable); the refusal rate in particular is a rough
  signal, not a precise estimate.
- **Author bias.** The questions were written by the same project that built the system.
- **Single run.** LLM output can vary between runs and model versions; the results file
  records the provider, model, settings and git commit.
- **Page-level matching only.** A hit means the right page was retrieved, not that the
  answer text is correct. Answer correctness is not scored automatically.
