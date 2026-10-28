import pytest

from app.ingestion.chunker import chunk_pages, normalize, split_text
from app.ingestion.pdf_loader import PageText

SENTENCE = "The quick brown fox jumps over the lazy dog near the riverbank. "


def test_empty_and_whitespace_text_gives_no_chunks():
    assert split_text("", 100, 20) == []
    assert split_text("   \n\n\t  ", 100, 20) == []


def test_short_text_is_a_single_chunk():
    assert split_text("Hello world.", 100, 20) == ["Hello world."]


def test_chunks_respect_size_limit():
    chunks = split_text(SENTENCE * 50, chunk_size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_consecutive_chunks_overlap():
    chunks = split_text(SENTENCE * 50, chunk_size=200, overlap=40)
    for current, nxt in zip(chunks, chunks[1:], strict=False):
        # The next chunk starts with text from the end of the current one.
        assert nxt[:20] in current


def test_no_words_are_lost():
    words = [f"word{i}" for i in range(500)]
    chunks = split_text(" ".join(words), chunk_size=120, overlap=30)
    covered = set(" ".join(chunks).split())
    assert covered == set(words)


def test_prefers_sentence_boundaries():
    chunks = split_text(SENTENCE * 20, chunk_size=200, overlap=40)
    assert all(c.endswith(".") for c in chunks)


def test_chunks_do_not_start_mid_word():
    chunks = split_text(SENTENCE * 20, chunk_size=150, overlap=40)
    valid_words = set(SENTENCE.split())
    assert all(c.split()[0] in valid_words for c in chunks)


def test_text_without_spaces_is_hard_cut():
    chunks = split_text("x" * 250, chunk_size=100, overlap=10)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks).count("x") >= 250


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (100, 100), (100, -1)])
def test_invalid_parameters_raise(size, overlap):
    with pytest.raises(ValueError):
        split_text("text", size, overlap)


def test_normalize_collapses_whitespace():
    assert normalize("a   b\t\tc\r\n\n\n\n d ") == "a b c\n\nd"


def test_chunk_pages_keeps_page_numbers_and_never_mixes_pages():
    pages = [
        PageText(page=1, text="alpha " * 100),
        PageText(page=2, text=""),
        PageText(page=3, text="omega " * 100),
    ]
    chunks = chunk_pages(pages, chunk_size=150, overlap=30)
    assert {c.page for c in chunks} == {1, 3}
    assert all("omega" not in c.text for c in chunks if c.page == 1)
    assert all("alpha" not in c.text for c in chunks if c.page == 3)
    page1 = [c.index for c in chunks if c.page == 1]
    assert page1 == list(range(len(page1)))
