from io import BytesIO
from pathlib import Path

from loredock.application import LoreDockService


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
