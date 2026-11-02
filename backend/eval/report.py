"""Render a results file as Markdown for the README, so numbers are never typed by hand.

Usage (from backend/):  python -m eval.report eval/results/<run>.json [<llm-run>.json]
"""

import json
import sys
from pathlib import Path

from eval import metrics

QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.json"


def retrieval_groups(result: dict) -> dict:
    """Recompute hit@k from the stored ranks, so older result files also get newer k values."""
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]
    return metrics.summarize_retrieval(questions, result["retrieval_rows"])


def pct(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator} ({numerator / denominator:.0%})" if denominator else "n/a"


def render(result: dict) -> str:
    meta, threshold = result["meta"], result["threshold"]
    retrieval = retrieval_groups(result)
    commit = (meta["git"]["commit"] or "unknown")[:7] + (" (dirty)" if meta["git"]["dirty"] else "")
    lines = [
        f"_Run `{meta['run_id']}` · {meta['date_utc']} · commit `{commit}` · "
        f"questions: {meta['questions_status']} ({meta['questions_verified']}/"
        f"{meta['questions_total']} verified) · embeddings `{meta['embedding_model']}`, "
        f"chunks {meta['chunk_size']}/{meta['chunk_overlap']}_",
        "",
        "**Retrieval** (25 answerable questions; hit = the expected PDF page is among the top-k chunks; lenient also accepts other pages containing the supporting phrase)",
        "",
        "| Questions | n | hit@1 | hit@3 | hit@4 | hit@5 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, g in retrieval.items():
        lines.append(
            f"| {name} | {g['n']} | {g['hit@1']:.0%} | {g['hit@3']:.0%} "
            f"| {g['hit@4']:.0%} | {g['hit@5']:.0%} |"
        )

    a, u = threshold["top1_score_answerable"], threshold["top1_score_unanswerable"]
    ins, loo = threshold["in_sample"], threshold["leave_one_out"]
    lines += [
        "",
        "**Relevance threshold** (top-1 cosine similarity)",
        "",
        "| | min | median | max |",
        "|---|---:|---:|---:|",
        f"| Answerable (n={a['n']}) | {a['min']:.3f} | {a['median']:.3f} | {a['max']:.3f} |",
        f"| Unanswerable (n={u['n']}) | {u['min']:.3f} | {u['median']:.3f} | {u['max']:.3f} |",
        "",
        f"- Threshold chosen on all 30 (in-sample, optimistic): `{ins['threshold']}`, keeps "
        f"{pct(ins['answerable_kept'], ins['answerable_total'])} answerable, refuses "
        f"{pct(ins['unanswerable_refused'], ins['unanswerable_total'])} unanswerable.",
        f"- Leave-one-out (out-of-sample): keeps {pct(loo['answerable_kept'], loo['answerable_total'])}"
        f" answerable, refuses {pct(loo['unanswerable_refused'], loo['unanswerable_total'])} unanswerable.",
        f"- {threshold['caveat']}",
    ]

    if "llm" in result:
        llm, m = meta["llm"], result["llm"]["model_only"]
        c, w = result["llm"]["citations"], result["llm"]["with_in_sample_threshold"]
        lines += [
            "",
            f"**Answering** with `{llm['provider']}` / `{llm['model']}` "
            f"(max tokens {llm['max_tokens']}, threshold off during the run)",
            "",
            "| Metric | Result |",
            "|---|---:|",
            f"| Unanswerable questions refused | {pct(m['unanswerable_refused'], m['unanswerable_total'])} |",
            f"| Answerable questions falsely refused | "
            f"{pct(m['answerable_falsely_refused'], m['answerable_total'])} |",
            f"| Answers citing the expected page | {pct(c['cited_expected_page'], c['answered'])} |",
            f"| Answers citing any page that contains the supporting phrase (lenient) | "
            f"{pct(c['cited_accepted_page'], c['answered'])} |",
            f"| Answers whose first citation is the expected page | "
            f"{pct(c['first_source_is_expected'], c['answered'])} |",
            f"| With threshold `{w['threshold']}`: unanswerable refused | "
            f"{pct(w['unanswerable_refused'], w['unanswerable_total'])} |",
            f"| With threshold `{w['threshold']}`: answerable falsely refused | "
            f"{pct(w['answerable_falsely_refused'], w['answerable_total'])} |",
        ]
        errors = result["llm"]["errors"]
        if errors:
            lines.append(
                f"\n{len(errors)} question(s) failed with provider errors and are excluded."
            )
    return "\n".join(lines)


def main() -> None:
    for name in sys.argv[1:]:
        print(render(json.loads(Path(name).read_text(encoding="utf-8"))))
        print()


if __name__ == "__main__":
    main()
