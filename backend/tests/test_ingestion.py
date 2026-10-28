import pytest

from app.ingestion.pdf_loader import PdfExtractionError, extract_pages
from app.ingestion.validation import UploadRejected, sanitize_filename
from tests.helpers import make_pdf

SOLAR_PDF = make_pdf(
    [
        ["Chapter one is about photosynthesis in green plants."],
        ["Chapter two explains how volcanoes erupt and form islands."],
        ["Chapter three covers the migration of arctic terns."],
    ]
)


def upload(client, *files):
    return client.post(
        "/documents",
        files=[("files", (name, data, "application/pdf")) for name, data in files],
    )


# --- PDF extraction ---------------------------------------------------------


def test_extract_pages_uses_one_based_page_index(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(SOLAR_PDF)
    pages = extract_pages(path)
    assert [p.page for p in pages] == [1, 2, 3]
    assert "volcanoes" in pages[1].text


def test_pdf_without_text_is_rejected(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(make_pdf([[], []]))
    with pytest.raises(PdfExtractionError, match="No extractable text"):
        extract_pages(path)


def test_corrupt_pdf_is_rejected(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"%PDF-1.4 this is not really a pdf")
    with pytest.raises(PdfExtractionError):
        extract_pages(path)


# --- Filename sanitizing ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("Report.PDF", "Report.pdf"),
        ("../../etc/evil.pdf", "evil.pdf"),
        ("C:\\Users\\me\\notes.pdf", "notes.pdf"),
        ("my <script> file.pdf", "my _script_ file.pdf"),
        ("a" * 300 + ".pdf", "a" * 116 + ".pdf"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize("raw", ["notes.txt", "archive.pdf.exe", ".pdf", "noextension", ""])
def test_sanitize_filename_rejects_non_pdf(raw):
    with pytest.raises(UploadRejected):
        sanitize_filename(raw)


# --- Upload, list, search, delete through the API ----------------------------


def test_upload_then_search_returns_correct_page(client):
    response = upload(client, ("science.pdf", SOLAR_PDF))
    assert response.status_code == 201
    [doc] = response.json()
    assert doc["filename"] == "science.pdf"
    assert doc["pages"] == 3
    assert doc["chunks"] == 3

    results = client.get("/search", params={"q": "how do volcanoes erupt", "k": 3}).json()
    top = results["results"][0]
    assert top["doc"] == "science.pdf"
    assert top["page"] == 2
    assert "volcanoes" in top["text"]
    assert top["score"] > results["results"][1]["score"]


def test_list_documents_and_health_count(client):
    upload(client, ("science.pdf", SOLAR_PDF))
    docs = client.get("/documents").json()
    assert [d["filename"] for d in docs] == ["science.pdf"]
    assert client.get("/health").json()["documents"] == 1


def test_duplicate_upload_is_rejected(client):
    assert upload(client, ("a.pdf", SOLAR_PDF)).status_code == 201
    response = upload(client, ("b.pdf", SOLAR_PDF))
    assert response.status_code == 409
    assert "a.pdf" in response.json()["detail"]


def test_non_pdf_content_is_rejected(client):
    response = upload(client, ("fake.pdf", b"<html>not a pdf</html>"))
    assert response.status_code == 415


def test_wrong_extension_is_rejected(client):
    response = upload(client, ("notes.txt", SOLAR_PDF))
    assert response.status_code == 415


def test_oversized_file_is_rejected(client):
    too_big = b"%PDF-1.4\n" + b"0" * (1024 * 1024)  # test settings allow 1 MB
    response = upload(client, ("big.pdf", too_big))
    assert response.status_code == 413


def test_pdf_without_text_returns_422_and_stores_nothing(client, settings):
    response = upload(client, ("scan.pdf", make_pdf([[]])))
    assert response.status_code == 422
    assert client.get("/documents").json() == []
    assert list(settings.upload_dir.iterdir()) == []


def test_one_bad_file_rejects_the_whole_batch(client):
    response = upload(client, ("good.pdf", SOLAR_PDF), ("bad.pdf", b"nope"))
    assert response.status_code == 415
    assert client.get("/documents").json() == []


def test_delete_removes_document_and_its_chunks(client, settings):
    [doc] = upload(client, ("science.pdf", SOLAR_PDF)).json()
    other = make_pdf([["Tea is grown on hillsides in Darjeeling."]])
    upload(client, ("tea.pdf", other))

    assert client.delete(f"/documents/{doc['id']}").status_code == 204
    assert client.delete(f"/documents/{doc['id']}").status_code == 404
    assert [d["filename"] for d in client.get("/documents").json()] == ["tea.pdf"]
    assert not (settings.upload_dir / f"{doc['id']}.pdf").exists()

    results = client.get("/search", params={"q": "volcanoes", "k": 5}).json()["results"]
    assert all(r["doc"] == "tea.pdf" for r in results)


def test_search_with_no_documents_returns_empty(client):
    assert client.get("/search", params={"q": "anything"}).json()["results"] == []


@pytest.mark.parametrize(
    "params", [{"q": ""}, {"q": "   "}, {"q": "x", "k": 0}, {"q": "x", "k": 99}]
)
def test_search_validates_parameters(client, params):
    assert client.get("/search", params=params).status_code == 422
