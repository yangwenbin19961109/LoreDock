import json
import sqlite3
import time
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from loredock.application import LoreDockService
from loredock.application import service as service_module
from loredock.ingestion.web import UrlFetcher, WebResponse


def _pptx_bytes() -> bytes:
    payload = BytesIO()
    with ZipFile(payload, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "ppt/presentation.xml",
            """<p:presentation
              xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
            </p:presentation>""",
        )
        archive.writestr(
            "ppt/_rels/presentation.xml.rels",
            """<Relationships
              xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
                Target="slides/slide1.xml"/>
            </Relationships>""",
        )
        archive.writestr(
            "ppt/slides/slide1.xml",
            """<p:sld
              xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r>
                <a:t>grounded slide citation</a:t>
              </a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
            </p:sld>""",
        )
    return payload.getvalue()


def _xlsx_bytes() -> bytes:
    payload = BytesIO()
    with ZipFile(payload, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets><sheet name="Knowledge" sheetId="1" r:id="rId1"/></sheets>
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
              <sheetData><row r="1"><c r="A1" t="inlineStr"><is>
                <t>grounded spreadsheet citation</t>
              </is></c></row></sheetData>
            </worksheet>""",
        )
    return payload.getvalue()


def _fixture_url_fetcher() -> UrlFetcher:
    return UrlFetcher(
        resolver=lambda _hostname, _port: ("93.184.216.34",),
        transport=lambda _url, _address, _limit: WebResponse(
            200,
            {"content-type": "text/html; charset=utf-8"},
            b"<html><head><title>Saved page</title></head>"
            b"<body><main>durable web snapshot citation</main>"
            b"<script>untrusted()</script></body></html>",
        ),
    )


def test_library_source_search_read_delete_round_trip(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    library = service.create_library("产品资料")

    source, job, duplicate = service.import_source(
        library.id,
        "guide.md",
        "text/markdown",
        BytesIO("# 安全\n\n远程 MCP 必须使用 HTTPS 和身份认证。".encode()),
    )

    assert source.status == "ready"
    assert job.status == "succeeded"
    assert duplicate is False
    results = service.search(library.id, "远程 MCP 安全")
    assert results[0].source_id == source.id
    content = service.read_source(source.id, results[0].char_start, results[0].char_end)
    assert content.text == results[0].text

    same_source, same_job, duplicate = service.import_source(
        library.id,
        "copy.md",
        "text/markdown",
        BytesIO("# 安全\n\n远程 MCP 必须使用 HTTPS 和身份认证。".encode()),
    )
    assert duplicate is True
    assert same_source.id == source.id
    assert same_job.id == job.id
    assert len(service.list_sources(library.id)) == 1

    service.close()
    service = LoreDockService(tmp_path)
    assert service.get_library(library.id).name == "产品资料"
    assert service.search(library.id, "HTTPS")[0].source_id == source.id

    service.delete_source(source.id)
    assert service.search(library.id, "HTTPS") == []
    service.delete_library(library.id)
    service.close()


def test_old_index_contract_is_rebuilt_without_changing_source(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    library = service.create_library("Migration")
    source, _, _ = service.import_source(
        library.id,
        "guide.md",
        "text/markdown",
        BytesIO(b"# Migration\n\nrebuildable derived index"),
    )
    paths = service.layout.library(library.id)
    manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
    manifest["schema_version"] = 2
    paths.manifest.write_text(json.dumps(manifest), encoding="utf-8")

    results = service.search(library.id, "derived index", lexical_only=True)

    assert results[0].source_id == source.id
    assert service.get_source(source.id).content_hash == source.content_hash
    connection = sqlite3.connect(paths.index)
    try:
        version = connection.execute(
            "SELECT value FROM index_metadata WHERE key='schema_version'"
        ).fetchone()
    finally:
        connection.close()
    assert version == ("3",)
    assert json.loads(paths.manifest.read_text(encoding="utf-8"))["schema_version"] == 3
    service.close()


def test_html_source_is_imported_indexed_and_read_as_inert_text(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    library = service.create_library("HTML")

    source, job, duplicate = service.import_source(
        library.id,
        "guide.html",
        "text/html",
        BytesIO(
            b"<h1>Offline knowledge</h1><p>citation handle is stable</p>"
            b"<script>private active content</script>"
        ),
    )

    assert source.status == "ready"
    assert source.media_type == "text/html"
    assert job.status == "succeeded"
    assert duplicate is False
    results = service.search(library.id, "citation handle", lexical_only=True)
    assert results[0].source_id == source.id
    content = service.read_source(source.id)
    assert "Offline knowledge" in content.text
    assert "private active content" not in content.text
    service.close()


def test_pptx_source_is_imported_indexed_and_read_with_slide_metadata(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    library = service.create_library("Presentations")

    source, job, duplicate = service.import_source(
        library.id,
        "briefing.pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        BytesIO(_pptx_bytes()),
    )

    assert source.status == "ready"
    assert job.status == "succeeded"
    assert duplicate is False
    results = service.search(library.id, "grounded citation", lexical_only=True)
    assert results[0].source_id == source.id
    assert results[0].page == 1
    assert "grounded slide citation" in service.read_source(source.id).text
    service.close()


def test_xlsx_source_is_imported_indexed_and_read_with_sheet_metadata(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    library = service.create_library("Spreadsheets")

    source, job, duplicate = service.import_source(
        library.id,
        "catalog.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        BytesIO(_xlsx_bytes()),
    )

    assert source.status == "ready"
    assert job.status == "succeeded"
    assert duplicate is False
    results = service.search(library.id, "spreadsheet citation", lexical_only=True)
    assert results[0].source_id == source.id
    assert results[0].page == 1
    content = service.read_source(source.id)
    assert "# 工作表 1: Knowledge" in content.text
    assert "A1: grounded spreadsheet citation" in content.text
    service.close()


def test_url_source_is_snapshotted_indexed_and_records_final_origin(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path, url_fetcher=_fixture_url_fetcher())
    library = service.create_library("Web")

    source, job, duplicate = service.import_url(library.id, "https://example.com/guide")

    assert source.status == "ready"
    assert source.source_kind == "url"
    assert source.origin_url == "https://example.com/guide"
    assert source.name == "guide.html"
    assert job.status == "succeeded"
    assert duplicate is False
    result = service.search(library.id, "snapshot citation", lexical_only=True)[0]
    assert result.source_id == source.id
    content = service.read_source(source.id).text
    assert "durable web snapshot citation" in content
    assert "untrusted" not in content
    service.close()


def test_model_install_runs_as_persisted_background_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_install(
        _directory: Path,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> Path:
        assert should_cancel is not None
        assert should_cancel() is False
        assert progress is not None
        progress(64, 128, "model.onnx")
        return _directory

    monkeypatch.setattr(service_module, "install_e5_package", fake_install)
    service = LoreDockService(tmp_path)
    started = service.start_model_install()
    deadline = time.monotonic() + 2
    completed = service.get_model_job(started.id)
    while completed.status in {"pending", "running"} and time.monotonic() < deadline:
        time.sleep(0.01)
        completed = service.get_model_job(started.id)

    assert completed.status == "succeeded"
    assert completed.bytes_downloaded == completed.bytes_total
    assert completed.attempts == 1
    service.close()
