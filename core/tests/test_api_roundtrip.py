import time
from io import BytesIO
from pathlib import Path
from typing import Protocol, cast
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient
from httpx import Response

from loredock.app import create_app
from loredock.application import LoreDockService
from loredock.ingestion.web import UrlFetcher, WebResponse


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: object) -> Response: ...

    def post(self, url: str, **kwargs: object) -> Response: ...

    def delete(self, url: str, **kwargs: object) -> Response: ...


def _wait_for_import(client: HttpClient, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 3
    payload: dict[str, object] = {}
    while time.monotonic() < deadline:
        payload = client.get(f"/api/v1/jobs/{job_id}").json()
        if payload["status"] not in {"pending", "running"}:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"import job did not finish: {payload}")


def _xlsx_upload() -> bytes:
    payload = BytesIO()
    with ZipFile(payload, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets><sheet name="API" sheetId="1" r:id="rId1"/></sheets>
            </workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<Relationships
              xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
                Target="worksheets/sheet1.xml"/>
            </Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1"><c r="C7" t="inlineStr"><is>
                <t>HTTP spreadsheet reference</t>
              </is></c></row></sheetData>
            </worksheet>""",
        )
    return payload.getvalue()


def _url_fetcher() -> UrlFetcher:
    return UrlFetcher(
        resolver=lambda _hostname, _port: ("93.184.216.34",),
        transport=lambda _url, _address, _limit: WebResponse(
            200,
            {"content-type": "text/html"},
            b"<main>HTTP imported web knowledge</main>",
        ),
    )


def test_http_api_completes_knowledge_round_trip(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    app = create_app(data_dir=tmp_path)
    app.state.service = service
    client = cast(HttpClient, TestClient(app))

    created = client.post("/api/v1/libraries", json={"name": "API Library"})
    assert created.status_code == 201
    library_id = str(created.json()["id"])

    imported = client.post(
        f"/api/v1/libraries/{library_id}/sources",
        files={"file": ("notes.txt", "LoreDock keeps exact citation ranges.", "text/plain")},
    )
    assert imported.status_code == 201
    source_id = str(imported.json()["source"]["id"])
    assert _wait_for_import(client, str(imported.json()["job"]["id"]))["status"] == "succeeded"

    searched = client.post(
        f"/api/v1/libraries/{library_id}/search",
        json={"query": "exact citation ranges"},
    )
    assert searched.status_code == 200
    result = searched.json()["items"][0]
    assert result["source_id"] == source_id
    assert result["matched_chunk_id"] == result["chunk_id"]
    assert result["context_id"]
    assert result["matched_range"]["char_start"] == result["char_start"]
    assert "citation ranges" in result["context_text"]

    content = client.get(f"/api/v1/sources/{source_id}/content")
    assert content.status_code == 200
    assert "citation ranges" in content.json()["text"]

    assert client.delete(f"/api/v1/sources/{source_id}").status_code == 204
    assert client.delete(f"/api/v1/libraries/{library_id}").status_code == 204
    service.close()


def test_http_import_batch_pause_resume_and_history(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    app = create_app(data_dir=tmp_path)
    app.state.service = service
    client = cast(HttpClient, TestClient(app))
    library_id = str(client.post("/api/v1/libraries", json={"name": "Batch API"}).json()["id"])

    created = client.post(
        f"/api/v1/libraries/{library_id}/import-batches",
        json={"name": "Two notes", "expected_items": 1},
    )
    assert created.status_code == 201
    batch_id = str(created.json()["id"])
    assert client.post(f"/api/v1/import-batches/{batch_id}/pause").json()["status"] == "paused"

    imported = client.post(
        f"/api/v1/libraries/{library_id}/sources?batch_id={batch_id}",
        files={"file": ("batch.txt", "persistent batch history", "text/plain")},
    )
    assert imported.status_code == 201
    assert imported.json()["job"]["batch_id"] == batch_id
    assert client.post(f"/api/v1/import-batches/{batch_id}/seal").json()["status"] == "paused"
    assert client.post(f"/api/v1/import-batches/{batch_id}/resume").status_code == 200
    assert _wait_for_import(client, str(imported.json()["job"]["id"]))["status"] == "succeeded"

    batch = client.get(f"/api/v1/import-batches/{batch_id}").json()
    assert batch["status"] == "succeeded"
    assert batch["succeeded_items"] == 1
    history = client.get(f"/api/v1/libraries/{library_id}/import-batches").json()
    assert history["items"][0]["id"] == batch_id
    service.close()


def test_http_api_accepts_html_without_indexing_active_content(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    app = create_app(data_dir=tmp_path)
    app.state.service = service
    client = cast(HttpClient, TestClient(app))
    library_id = str(client.post("/api/v1/libraries", json={"name": "HTML"}).json()["id"])

    imported = client.post(
        f"/api/v1/libraries/{library_id}/sources",
        files={
            "file": (
                "reference.html",
                "<main>grounded citation</main><script>untrusted command</script>",
                "text/html",
            )
        },
    )

    assert imported.status_code == 201
    source_id = str(imported.json()["source"]["id"])
    assert _wait_for_import(client, str(imported.json()["job"]["id"]))["status"] == "succeeded"
    content = client.get(f"/api/v1/sources/{source_id}/content")
    assert content.json()["text"] == "grounded citation"
    assert (
        client.post(
            f"/api/v1/libraries/{library_id}/search", json={"query": "grounded citation"}
        ).json()["items"][0]["source_id"]
        == source_id
    )
    assert (
        client.post(
            f"/api/v1/libraries/{library_id}/search",
            json={"query": "untrusted command", "lexical_only": True},
        ).json()["items"]
        == []
    )
    service.close()


def test_http_api_accepts_xlsx_with_sheet_and_cell_reference(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    app = create_app(data_dir=tmp_path)
    app.state.service = service
    client = cast(HttpClient, TestClient(app))
    library_id = str(client.post("/api/v1/libraries", json={"name": "XLSX"}).json()["id"])

    imported = client.post(
        f"/api/v1/libraries/{library_id}/sources",
        files={
            "file": (
                "reference.xlsx",
                _xlsx_upload(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert imported.status_code == 201
    source_id = str(imported.json()["source"]["id"])
    assert _wait_for_import(client, str(imported.json()["job"]["id"]))["status"] == "succeeded"
    result = client.post(
        f"/api/v1/libraries/{library_id}/search",
        json={"query": "spreadsheet reference", "lexical_only": True},
    ).json()["items"][0]
    assert result["source_id"] == source_id
    assert result["page"] == 1
    content = client.get(f"/api/v1/sources/{source_id}/content").json()["text"]
    assert "# 工作表 1: API" in content
    assert "C7: HTTP spreadsheet reference" in content
    service.close()


def test_http_api_imports_bounded_url_snapshot(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path, url_fetcher=_url_fetcher())
    app = create_app(data_dir=tmp_path)
    app.state.service = service
    client = cast(HttpClient, TestClient(app))
    library_id = str(client.post("/api/v1/libraries", json={"name": "Web"}).json()["id"])

    imported = client.post(
        f"/api/v1/libraries/{library_id}/url-sources",
        json={"url": "https://example.com/reference"},
    )

    assert imported.status_code == 201
    source = imported.json()["source"]
    assert source["source_kind"] == "url"
    assert source["origin_url"] == "https://example.com/reference"
    assert _wait_for_import(client, str(imported.json()["job"]["id"]))["status"] == "succeeded"
    content = client.get(f"/api/v1/sources/{source['id']}/content")
    assert content.json()["text"] == "HTTP imported web knowledge"
    service.close()
