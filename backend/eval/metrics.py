"""Pure metric functions for the evaluation (no I/O, so they are unit-tested)."""

import re
import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass


def normalize(text: str) -> str:
    """Lowercase, unify quotes/dashes, and collapse whitespace so phrases match page text."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"')
    text = text.replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def pages_containing(phrase: str, pages: dict[int, str]) -> list[int]:
    target = normalize(phrase)
    return [n for n, text in sorted(pages.items()) if target in normalize(text)]


def first_hit_rank(hits: Sequence[tuple[str, int]], doc: str, pages: Collection[int]) -> int | None:
    """0-based rank of the first retrieved (doc, page) with page in `pages`, or None."""
    return next((i for i, (d, p) in enumerate(hits) if d == doc and p in pages), None)


def hit_at_k(ranks: Sequence[int | None], k: int) -> float:
    return sum(1 for r in ranks if r is not None and r < k) / len(ranks) if ranks else 0.0


@dataclass(frozen=True)
class ThresholdResult:
    threshold: float | None  # None means "no threshold" (keep everything)
    answerable_kept: int
    answerable_total: int
    unanswerable_refused: int
    unanswerable_total: int

    @property
    def balanced_accuracy(self) -> float:
        kept = self.answerable_kept / self.answerable_total if self.answerable_total else 0.0
        refused = (
            self.unanswerable_refused / self.unanswerable_total if self.unanswerable_total else 0.0
        )
        return (kept + refused) / 2


def evaluate_threshold(
    threshold: float | None, answerable: Sequence[float], unanswerable: Sequence[float]
) -> ThresholdResult:
    def refused(score: float) -> bool:
        return threshold is not None and score < threshold

    return ThresholdResult(
        threshold=threshold,
        answerable_kept=sum(not refused(s) for s in answerable),
        answerable_total=len(answerable),
        unanswerable_refused=sum(refused(s) for s in unanswerable),
        unanswerable_total=len(unanswerable),
    )


def choose_threshold(answerable: Sequence[float], unanswerable: Sequence[float]) -> ThresholdResult:
    """Pick the cutoff with the best balanced accuracy; ties go to the LOWEST cutoff.

    Candidates are midpoints between neighbouring observed scores (plus "no threshold"),
    so the result never depends on arbitrary grid choices. Preferring the lowest cutoff
    on ties keeps false refusals of real questions to a minimum.
    """
    scores = sorted(set(answerable) | set(unanswerable))
    candidates: list[float | None] = [None]
    candidates += [round((a + b) / 2, 4) for a, b in zip(scores, scores[1:], strict=False)]
    best = None
    for t in sorted(candidates, key=lambda c: -1.0 if c is None else c):
        result = evaluate_threshold(t, answerable, unanswerable)
        if best is None or result.balanced_accuracy > best.balanced_accuracy:
            best = result
    assert best is not None
    return best


def leave_one_out(
    answerable: Sequence[float], unanswerable: Sequence[float]
) -> dict[str, float | int]:
    """Out-of-sample estimate: choose the cutoff without each question, then test on it."""
    items = [(s, True) for s in answerable] + [(s, False) for s in unanswerable]
    kept = refused = 0
    for i, (score, is_answerable) in enumerate(items):
        rest = items[:i] + items[i + 1 :]
        t = choose_threshold([s for s, a in rest if a], [s for s, a in rest if not a]).threshold
        gated = t is not None and score < t
        if is_answerable and not gated:
            kept += 1
        if not is_answerable and gated:
            refused += 1
    return {
        "answerable_kept": kept,
        "answerable_total": len(answerable),
        "unanswerable_refused": refused,
        "unanswerable_total": len(unanswerable),
    }


def rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None
