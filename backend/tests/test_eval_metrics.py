import json
from pathlib import Path

import pytest

from eval import metrics
from eval.report import render

QUESTIONS = Path(__file__).resolve().parents[1] / "eval" / "questions.json"


def test_normalize_matches_across_line_breaks_and_quotes():
    page = "the organization’s readiness\n  to bear   the risk"
    assert metrics.pages_containing("organization's readiness to bear", {3: page}) == [3]
    assert metrics.pages_containing("not here", {3: page}) == []


def test_first_hit_rank_requires_doc_and_page_to_match():
    hits = [("a.pdf", 2), ("b.pdf", 5), ("a.pdf", 5)]
    assert metrics.first_hit_rank(hits, "a.pdf", {5}) == 2
    assert metrics.first_hit_rank(hits, "b.pdf", {2}) is None
    assert metrics.first_hit_rank(hits, "a.pdf", {5, 2}) == 0  # lenient: any accepted page


def test_hit_at_k():
    ranks = [0, 2, None, 4]
    assert metrics.hit_at_k(ranks, 1) == 0.25
    assert metrics.hit_at_k(ranks, 3) == 0.5
    assert metrics.hit_at_k(ranks, 5) == 0.75
    assert metrics.hit_at_k([], 5) == 0.0


def test_choose_threshold_separates_clean_groups_at_the_lowest_best_cutoff():
    result = metrics.choose_threshold([0.6, 0.7, 0.8], [0.1, 0.2])
    assert result.threshold == 0.4  # midpoint between 0.2 and 0.6
    assert result.balanced_accuracy == 1.0


def test_choose_threshold_keeps_no_threshold_when_it_cannot_help():
    # Unanswerable questions score HIGHER than answerable ones: any cutoff only hurts.
    result = metrics.choose_threshold([0.2, 0.3], [0.8, 0.9])
    assert result.threshold is None
    assert result.answerable_kept == 2


def test_leave_one_out_is_never_better_than_in_sample():
    pos, neg = [0.55, 0.6, 0.62, 0.7, 0.35], [0.3, 0.4, 0.58]
    fit = metrics.choose_threshold(pos, neg)
    loo = metrics.leave_one_out(pos, neg)
    in_sample_correct = fit.answerable_kept + fit.unanswerable_refused
    assert loo["answerable_kept"] + loo["unanswerable_refused"] <= in_sample_correct


def test_rate():
    assert metrics.rate(1, 3) == 0.3333
    assert metrics.rate(1, 0) is None


def test_question_file_is_well_formed():
    data = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    questions = data["questions"]
    assert data["status"] in {"UNVERIFIED", "VERIFIED"}
    assert len(questions) == 30
    assert len({q["id"] for q in questions}) == 30
    answerable = [q for q in questions if q["answerable"]]
    assert len(answerable) == 25
    for q in answerable:
        assert q["page"] >= 1 and q["supporting_phrase"] and q["doc"].endswith(".pdf")
    assert all(q["why_unanswerable"] for q in questions if not q["answerable"])


@pytest.fixture
def fake_result():
    stats = {"n": 1, "min": 0.5, "median": 0.5, "max": 0.5, "values": [0.5]}
    return {
        "meta": {
            "run_id": "r1",
            "date_utc": "2026-10-30T00:00:00+00:00",
            "git": {"commit": "abcdef123", "dirty": False},
            "questions_status": "UNVERIFIED",
            "questions_verified": 0,
            "questions_total": 30,
            "embedding_model": "m",
            "chunk_size": 800,
            "chunk_overlap": 150,
            "llm": {"provider": "gemini", "model": "g", "max_tokens": 1024},
        },
        "retrieval": {"all": {"n": 25, "hit@1": 0.6, "hit@3": 0.8, "hit@5": 0.9}},
        "threshold": {
            "top1_score_answerable": stats,
            "top1_score_unanswerable": stats,
            "in_sample": {
                "threshold": 0.4,
                "answerable_kept": 24,
                "answerable_total": 25,
                "unanswerable_refused": 3,
                "unanswerable_total": 5,
            },
            "leave_one_out": {
                "answerable_kept": 23,
                "answerable_total": 25,
                "unanswerable_refused": 2,
                "unanswerable_total": 5,
            },
            "caveat": "Only 5 unanswerable questions.",
        },
        "llm": {
            "errors": {},
            "model_only": {
                "unanswerable_refused": 5,
                "unanswerable_total": 5,
                "answerable_falsely_refused": 2,
                "answerable_total": 25,
            },
            "citations": {
                "answered": 23,
                "cited_expected_page": 20,
                "cited_accepted_page": 21,
                "first_source_is_expected": 18,
            },
            "with_in_sample_threshold": {
                "threshold": 0.4,
                "unanswerable_refused": 5,
                "unanswerable_total": 5,
                "answerable_falsely_refused": 3,
                "answerable_total": 25,
            },
        },
    }


def test_report_renders_numbers_from_the_result_file(fake_result):
    markdown = render(fake_result)
    assert "| all | 25 | 60% | 80% | 90% |" in markdown
    assert "(lenient) | 21/23 (91%) |" in markdown
    assert "UNVERIFIED (0/30 verified)" in markdown
    assert "| Unanswerable questions refused | 5/5 (100%) |" in markdown
    assert "| Answers citing the expected page | 20/23 (87%) |" in markdown
    assert "commit `abcdef1`" in markdown
