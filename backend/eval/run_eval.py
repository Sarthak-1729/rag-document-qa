"""Evaluate retrieval and answering on the fixed question set.

Usage (from backend/):
  python -m eval.fetch_docs                      # once: download + verify the PDFs
  python -m eval.run_eval --skip-llm             # retrieval + score analysis only (no API key)
  python -m eval.run_eval                        # full run with the LLM_PROVIDER from .env
  python -m eval.run_eval --resume results/<run>.partial.json   # continue after quota stops

The eval uses its own index in eval/.index and never touches the app's data directory.
The relevance threshold is OFF during the LLM run, so the model's behavior is measured on
its own; the threshold's effect is computed afterwards from the recorded scores.
"""

import argparse
import hashlib
import json
import logging
import platform
import shutil
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.ingestion.pdf_loader import extract_pages
from app.llm.base import LLMError
from app.llm.factory import build_provider
from app.qa import AskService
from app.retrieval.embeddings import SentenceTransformerEmbedder
from app.services import DocumentService
from eval import metrics
from eval.fetch_docs import DOCUMENTS, ensure_documents

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = EVAL_DIR / "questions.json"
RESULTS_DIR = EVAL_DIR / "results"
INDEX_DIR = EVAL_DIR / ".index"
RETRIEVAL_K = 5
RETRYABLE = {503, 504}  # quota / unavailable / timeout: worth waiting and retrying

log = print  # results go to stdout; kept as a name so it's easy to swap for logging


# --- Setup ------------------------------------------------------------------------------------


def load_settings(skip_llm: bool) -> Settings:
    overrides: dict = {"data_dir": INDEX_DIR, "min_relevance_score": None}
    if skip_llm:
        overrides["llm_provider"] = "ollama"  # never built; avoids requiring an API key
    return Settings(**overrides)


def file_sha256(path: Path) -> str:
    # Normalize line endings so the hash is the same on Windows (CRLF) and Linux (LF) checkouts.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def git_state() -> dict:
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], capture_output=True, text=True, check=True, cwd=EVAL_DIR
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    # Saved results are this script's output, not an input, so they don't make a run dirty.
    changes = run("status", "--porcelain", "--", ":/", ":(top,exclude)backend/eval/results")
    return {"commit": run("rev-parse", "HEAD") or None, "dirty": bool(changes)}


def build_index(settings: Settings) -> DocumentService:
    """Index the eval PDFs once; rebuild automatically if chunking or the model changes."""
    fingerprint = {
        "embedding_model": settings.embedding_model,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "documents": {d.filename: d.sha256 for d in DOCUMENTS},
    }
    marker = INDEX_DIR / "fingerprint.json"
    if INDEX_DIR.exists() and (
        not marker.exists() or json.loads(marker.read_text()) != fingerprint
    ):
        log("Index settings changed: rebuilding eval index.")
        shutil.rmtree(INDEX_DIR)

    service = DocumentService(settings, SentenceTransformerEmbedder(settings.embedding_model))
    for doc, path in zip(DOCUMENTS, ensure_documents(), strict=True):
        if service.registry.find_by_hash(doc.sha256):
            continue
        log(f"Indexing {doc.filename} ...")
        prepared = service.prepare(doc.filename, path.read_bytes(), set())
        service.commit(prepared)
    marker.write_text(json.dumps(fingerprint, indent=2))
    return service


def validate_questions(questions: list[dict]) -> dict[str, list[int]]:
    """Every supporting phrase must appear on its expected page. Returns other pages it's on."""
    page_text = {
        d.filename: {p.page: p.text for p in extract_pages(path)}
        for d, path in zip(DOCUMENTS, ensure_documents(), strict=True)
    }
    errors, elsewhere = [], {}
    for q in questions:
        if not q["answerable"]:
            continue
        found = metrics.pages_containing(q["supporting_phrase"], page_text[q["doc"]])
        if q["page"] not in found:
            errors.append(f"{q['id']}: phrase not on page {q['page']} (found on {found or 'none'})")
        others = [p for p in found if p != q["page"]]
        if others:
            elsewhere[q["id"]] = others
    if errors:
        raise SystemExit("questions.json failed validation:\n  " + "\n  ".join(errors))
    return elsewhere


# --- Measurements -------------------------------------------------------------------------------


def accepted_pages(q: dict, elsewhere: dict[str, list[int]]) -> set[int]:
    """Lenient match: the expected page plus any page containing the supporting phrase."""
    return {q["page"], *elsewhere.get(q["id"], [])}


def run_retrieval(
    service: DocumentService, questions: list[dict], elsewhere: dict[str, list[int]]
) -> list[dict]:
    rows = []
    for q in questions:
        hits = service.search(q["question"], RETRIEVAL_K)
        row = {
            "id": q["id"],
            "answerable": q["answerable"],
            "top1_score": hits[0].score if hits else None,
            "top_hits": [{"doc": h.doc, "page": h.page, "score": h.score} for h in hits],
        }
        if q["answerable"]:
            found = [(h.doc, h.page) for h in hits]
            row["rank"] = metrics.first_hit_rank(found, q["doc"], {q["page"]})
            row["rank_lenient"] = metrics.first_hit_rank(
                found, q["doc"], accepted_pages(q, elsewhere)
            )
        rows.append(row)
    return rows


def ask_with_retries(ask: AskService, question: str, k: int, delay: float, retries: int):
    for attempt in range(retries + 1):
        try:
            return ask.ask(question, k), None
        except LLMError as exc:
            if exc.status_code in RETRYABLE and attempt < retries:
                wait = delay * 2 ** (attempt + 1)
                log(f"    provider {exc.status_code}: {exc.detail} -> retrying in {wait:.0f}s")
                time.sleep(wait)
                continue
            return None, exc
    raise AssertionError("unreachable")


def run_llm(
    service: DocumentService,
    settings: Settings,
    questions: list[dict],
    elsewhere: dict[str, list[int]],
    records: dict[str, dict],
    save,
    delay: float,
    retries: int,
) -> None:
    ask = AskService(service, build_provider(settings), min_relevance_score=None)
    todo = [q for q in questions if q["id"] not in records]
    log(f"LLM run: {len(todo)} questions to go ({len(records)} already done), {delay}s apart.")
    for i, q in enumerate(todo, start=1):
        result, error = ask_with_retries(ask, q["question"], settings.ask_top_k, delay, retries)
        if error is not None and error.status_code in RETRYABLE:
            save()
            raise SystemExit(
                f"Stopped at {q['id']}: {error.detail}\nProgress saved. Resume later with:\n"
                f"  python -m eval.run_eval --resume {save.path.relative_to(EVAL_DIR.parent)}"
            )
        if error is not None:
            records[q["id"]] = {"error": {"status": error.status_code, "detail": error.detail}}
        else:
            sources = [{"doc": s.doc, "page": s.page} for s in result.sources]
            record = {
                "refused": result.refused,
                "refusal_reason": result.refusal_reason,
                "answer": result.answer,
                "sources": sources,
            }
            if q["answerable"]:
                expected = {"doc": q["doc"], "page": q["page"]}
                record["cited_expected_page"] = expected in sources
                record["first_source_is_expected"] = bool(sources) and sources[0] == expected
                accepted = accepted_pages(q, elsewhere)
                record["cited_accepted_page"] = any(
                    s["doc"] == q["doc"] and s["page"] in accepted for s in sources
                )
            records[q["id"]] = record
        status = "error" if error else ("refused" if records[q["id"]]["refused"] else "answered")
        log(f"  [{i}/{len(todo)}] {q['id']}: {status}")
        save()
        if i < len(todo):
            time.sleep(delay)


# --- Summaries --------------------------------------------------------------------------------


def summarize_retrieval(questions: list[dict], rows: list[dict]) -> dict:
    by_id = {q["id"]: q for q in questions}
    answerable = [r for r in rows if r["answerable"]]

    def hits_for(subset: list[dict], key: str = "rank") -> dict:
        ranks = [r[key] for r in subset]
        return {
            "n": len(subset),
            **{f"hit@{k}": round(metrics.hit_at_k(ranks, k), 4) for k in (1, 3, 5)},
        }

    groups: dict[str, dict] = {
        "all (strict: expected page)": hits_for(answerable),
        "all (lenient: any page with the phrase)": hits_for(answerable, "rank_lenient"),
    }
    for key in ("doc", "phrasing"):
        for value in sorted({by_id[r["id"]][key] for r in answerable}):
            subset = [r for r in answerable if by_id[r["id"]][key] == value]
            groups[f"{key}={value}"] = hits_for(subset)
    return groups


def score_stats(scores: list[float]) -> dict:
    return {
        "n": len(scores),
        "min": round(min(scores), 4),
        "median": round(statistics.median(scores), 4),
        "max": round(max(scores), 4),
        "values": [round(s, 4) for s in scores],
    }


def summarize_threshold(rows: list[dict]) -> dict:
    pos = [r["top1_score"] for r in rows if r["answerable"]]
    neg = [r["top1_score"] for r in rows if not r["answerable"]]
    fit = metrics.choose_threshold(pos, neg)
    return {
        "top1_score_answerable": score_stats(pos),
        "top1_score_unanswerable": score_stats(neg),
        "in_sample": {
            "note": "Threshold chosen AND scored on the same 30 questions (optimistic).",
            "threshold": fit.threshold,
            "answerable_kept": fit.answerable_kept,
            "answerable_total": fit.answerable_total,
            "unanswerable_refused": fit.unanswerable_refused,
            "unanswerable_total": fit.unanswerable_total,
        },
        "leave_one_out": {
            "note": "Each question scored with a threshold chosen on the other 29.",
            **metrics.leave_one_out(pos, neg),
        },
        "caveat": f"Only {len(neg)} unanswerable questions: treat refusal estimates as rough.",
    }


def summarize_llm(questions: list[dict], records: dict, rows: list[dict], threshold) -> dict:
    ok = {qid: r for qid, r in records.items() if "error" not in r}
    pos = [q for q in questions if q["answerable"] and q["id"] in ok]
    neg = [q for q in questions if not q["answerable"] and q["id"] in ok]
    answered = [q for q in pos if not ok[q["id"]]["refused"]]
    top1 = {r["id"]: r["top1_score"] for r in rows}

    def pipeline_refused(q: dict) -> bool:  # threshold gate + model, as the app would behave
        gated = threshold is not None and top1[q["id"]] < threshold
        return gated or ok[q["id"]]["refused"]

    reasons: dict[str, int] = {}
    for r in ok.values():
        if r["refused"]:
            reasons[r["refusal_reason"]] = reasons.get(r["refusal_reason"], 0) + 1
    return {
        "completed": len(ok),
        "errors": {qid: r["error"] for qid, r in records.items() if "error" in r},
        "model_only": {
            "unanswerable_refused": sum(ok[q["id"]]["refused"] for q in neg),
            "unanswerable_total": len(neg),
            "answerable_falsely_refused": sum(ok[q["id"]]["refused"] for q in pos),
            "answerable_total": len(pos),
            "refusal_reasons": reasons,
        },
        "citations": {
            "answered": len(answered),
            "cited_expected_page": sum(ok[q["id"]]["cited_expected_page"] for q in answered),
            "cited_accepted_page": sum(ok[q["id"]]["cited_accepted_page"] for q in answered),
            "first_source_is_expected": sum(
                ok[q["id"]]["first_source_is_expected"] for q in answered
            ),
        },
        "with_in_sample_threshold": {
            "threshold": threshold,
            "unanswerable_refused": sum(pipeline_refused(q) for q in neg),
            "unanswerable_total": len(neg),
            "answerable_falsely_refused": sum(pipeline_refused(q) for q in pos),
            "answerable_total": len(pos),
        },
    }


def print_summary(result: dict) -> None:
    r, t = result["retrieval"], result["threshold"]
    log("\n=== Retrieval (25 answerable questions, top-5 search over all 3 PDFs) ===")
    log(f"{'group':28s} {'n':>3s} {'hit@1':>7s} {'hit@3':>7s} {'hit@5':>7s}")
    for name, g in r.items():
        log(f"{name:28s} {g['n']:3d} {g['hit@1']:7.1%} {g['hit@3']:7.1%} {g['hit@5']:7.1%}")
    a, u = t["top1_score_answerable"], t["top1_score_unanswerable"]
    log("\n=== Top-1 similarity scores ===")
    log(
        f"answerable   (n={a['n']}): min {a['min']:.3f}  "
        f"median {a['median']:.3f}  max {a['max']:.3f}"
    )
    log(
        f"unanswerable (n={u['n']}): min {u['min']:.3f}  "
        f"median {u['median']:.3f}  max {u['max']:.3f}"
    )
    ins, loo = t["in_sample"], t["leave_one_out"]
    log(
        f"in-sample threshold {ins['threshold']}: keeps {ins['answerable_kept']}/"
        f"{ins['answerable_total']} answerable, refuses {ins['unanswerable_refused']}/"
        f"{ins['unanswerable_total']} unanswerable (chosen and scored on the same set)"
    )
    log(
        f"leave-one-out: keeps {loo['answerable_kept']}/{loo['answerable_total']} answerable, "
        f"refuses {loo['unanswerable_refused']}/{loo['unanswerable_total']} unanswerable"
    )
    log(t["caveat"])
    if "llm" in result:
        m, c, w = (
            result["llm"]["model_only"],
            result["llm"]["citations"],
            result["llm"]["with_in_sample_threshold"],
        )
        log(
            f"\n=== LLM: {result['meta']['llm']['provider']} / {result['meta']['llm']['model']} ==="
        )
        log(f"unanswerable refused       {m['unanswerable_refused']}/{m['unanswerable_total']}")
        log(
            f"answerable falsely refused {m['answerable_falsely_refused']}/{m['answerable_total']}"
            f"  reasons: {m['refusal_reasons']}"
        )
        log(f"cited the expected page    {c['cited_expected_page']}/{c['answered']} answered")
        log(f"expected page cited first  {c['first_source_is_expected']}/{c['answered']} answered")
        log(f"cited a page with the phrase {c['cited_accepted_page']}/{c['answered']} (lenient)")
        log(
            f"with threshold {w['threshold']}: unanswerable refused {w['unanswerable_refused']}/"
            f"{w['unanswerable_total']}, answerable falsely refused "
            f"{w['answerable_falsely_refused']}/{w['answerable_total']}"
        )
        if result["llm"]["errors"]:
            log(f"errors (excluded from rates): {result['llm']['errors']}")


# --- Main ---------------------------------------------------------------------------------------


class Saver:
    def __init__(self, path: Path, result: dict) -> None:
        self.path, self.result = path, result

    def __call__(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.result, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-llm", action="store_true", help="retrieval + scores only")
    parser.add_argument("--delay", type=float, default=6.0, help="seconds between LLM calls")
    parser.add_argument("--retries", type=int, default=5, help="retries on quota/timeout")
    parser.add_argument("--resume", type=Path, help="a results/*.partial.json to continue")
    args = parser.parse_args(argv)

    logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings are noise here
    questions_doc = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    questions = questions_doc["questions"]
    questions_sha = file_sha256(QUESTIONS_PATH)
    settings = load_settings(args.skip_llm)

    log("Validating questions.json against the PDFs ...")
    elsewhere = validate_questions(questions)
    service = build_index(settings)

    if args.resume:
        result = json.loads(args.resume.read_text(encoding="utf-8"))
        if result["meta"]["questions_sha256"] != questions_sha:
            raise SystemExit("questions.json changed since this run started; start a new run.")
        path = args.resume
    else:
        run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        suffix = "-retrieval" if args.skip_llm else ""
        RESULTS_DIR.mkdir(exist_ok=True)
        path = RESULTS_DIR / f"{run_id}{suffix}.partial.json"
        llm_meta = None
        if not args.skip_llm:
            gemini = settings.llm_provider == "gemini"
            llm_meta = {
                "provider": settings.llm_provider,
                "model": settings.gemini_model if gemini else settings.ollama_model,
                "thinking_level": settings.gemini_thinking_level if gemini else None,
                "max_tokens": settings.llm_max_tokens,
                "min_relevance_score_during_run": None,
                "delay_seconds": args.delay,
            }
        result = {
            "meta": {
                "run_id": run_id,
                "date_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "mode": "retrieval-only" if args.skip_llm else "full",
                "git": git_state(),
                "questions_sha256": questions_sha,
                "questions_status": questions_doc["status"],
                "questions_verified": sum(q.get("verified", False) for q in questions),
                "questions_total": len(questions),
                "documents": [
                    {"file": d.filename, "sha256": d.sha256, "url": d.url} for d in DOCUMENTS
                ],
                "embedding_model": settings.embedding_model,
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "retrieval_k": RETRIEVAL_K,
                "ask_top_k": settings.ask_top_k,
                "llm": llm_meta,
                "python": platform.python_version(),
            },
            "phrase_also_found_on_pages": elsewhere,
        }

    rows = run_retrieval(service, questions, elsewhere)
    result["retrieval_rows"] = rows
    result["retrieval"] = summarize_retrieval(questions, rows)
    result["threshold"] = summarize_threshold(rows)
    save = Saver(path, result)
    save()

    if result["meta"]["mode"] == "full":
        records = result.setdefault("llm_records", {})
        run_llm(service, settings, questions, elsewhere, records, save, args.delay, args.retries)
        threshold = result["threshold"]["in_sample"]["threshold"]
        result["llm"] = summarize_llm(questions, records, rows, threshold)

    final = path.with_name(path.name.replace(".partial.json", ".json"))
    save()
    path.replace(final)
    print_summary(result)
    log(f"\nSaved {final.relative_to(EVAL_DIR.parent)}")
    log(
        "Markdown for the README:  python -m eval.report " + str(final.relative_to(EVAL_DIR.parent))
    )


if __name__ == "__main__":
    sys.exit(main())
