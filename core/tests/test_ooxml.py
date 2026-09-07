from pathlib import Path
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZipFile

import pytest

from loredock.ingestion import OoxmlLimits, OoxmlPackage, OoxmlPackageError

RELATIONSHIPS = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId2" Type="external" Target="https://example.invalid/data"
    TargetMode="External"/>
</Relationships>
"""


def write_package(path: Path, parts: dict[str, bytes], *, compression: int = ZIP_DEFLATED) -> None:
    with ZipFile(path, "w", compression=compression) as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)


def test_reads_bounded_xml_and_resolves_internal_relationships(tmp_path: Path) -> None:
    path = tmp_path / "sample.pptx"
    write_package(
        path,
        {
            "ppt/presentation.xml": b'<p:presentation xmlns:p="urn:presentation"/>',
            "ppt/_rels/presentation.xml.rels": RELATIONSHIPS,
            "ppt/slides/slide1.xml": b'<p:sld xmlns:p="urn:presentation"/>',
        },
    )

    with OoxmlPackage(path) as package:
        assert package.read_xml("ppt/presentation.xml").tag == "{urn:presentation}presentation"
        relationships = package.relationships("ppt/presentation.xml")

    assert relationships[0].target == "ppt/slides/slide1.xml"
    assert relationships[0].external is False
    assert relationships[1].target == "https://example.invalid/data"
    assert relationships[1].external is True


@pytest.mark.parametrize("name", ["../outside.xml", "/absolute.xml", "ppt/../../slide.xml"])
def test_rejects_unsafe_member_names(tmp_path: Path, name: str) -> None:
    path = tmp_path / "unsafe.pptx"
    write_package(path, {name: b"<root/>"})

    with pytest.raises(OoxmlPackageError, match="unsafe part name"):
        OoxmlPackage(path)


def test_rejects_duplicate_parts(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.xlsx"
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", b"<first/>")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("xl/workbook.xml", b"<second/>")

    with pytest.raises(OoxmlPackageError, match="duplicate"):
        OoxmlPackage(path)


def test_rejects_member_and_total_decompression_limits(tmp_path: Path) -> None:
    member_path = tmp_path / "large-part.xlsx"
    write_package(member_path, {"xl/workbook.xml": b"x" * 33})
    limits = OoxmlLimits(max_part_bytes=32, max_total_bytes=64)

    with pytest.raises(OoxmlPackageError, match="part exceeds"):
        OoxmlPackage(member_path, limits=limits)

    total_path = tmp_path / "large-total.xlsx"
    write_package(total_path, {"xl/a.xml": b"x" * 24, "xl/b.xml": b"y" * 24})
    limits = OoxmlLimits(max_part_bytes=32, max_total_bytes=40)

    with pytest.raises(OoxmlPackageError, match="total decompression"):
        OoxmlPackage(total_path, limits=limits)


def test_rejects_excessive_member_count_and_invalid_archives(tmp_path: Path) -> None:
    member_path = tmp_path / "members.xlsx"
    write_package(member_path, {"xl/a.xml": b"<a/>", "xl/b.xml": b"<b/>"})
    limits = OoxmlLimits(max_members=1)

    with pytest.raises(OoxmlPackageError, match="too many parts"):
        OoxmlPackage(member_path, limits=limits)

    invalid_path = tmp_path / "invalid.pptx"
    invalid_path.write_bytes(b"not a ZIP package")

    with pytest.raises(OoxmlPackageError, match="not a readable"):
        OoxmlPackage(invalid_path)


def test_rejects_suspicious_compression_and_unsupported_methods(tmp_path: Path) -> None:
    compressed_path = tmp_path / "compressed.xlsx"
    write_package(compressed_path, {"xl/workbook.xml": b"a" * 4096})
    limits = OoxmlLimits(
        max_part_bytes=8192,
        max_total_bytes=8192,
        max_compression_ratio=4,
        compression_ratio_floor_bytes=128,
    )

    with pytest.raises(OoxmlPackageError, match="compression ratio"):
        OoxmlPackage(compressed_path, limits=limits)

    bzip_path = tmp_path / "bzip.xlsx"
    write_package(bzip_path, {"xl/workbook.xml": b"<root/>"}, compression=ZIP_BZIP2)

    with pytest.raises(OoxmlPackageError, match="compression method"):
        OoxmlPackage(bzip_path)


@pytest.mark.parametrize(
    "declaration",
    [
        b'<!DOCTYPE root SYSTEM "https://example.invalid/evil.dtd"><root/>',
        b'<!DOCTYPE root [<!ENTITY secret "value">]><root>&secret;</root>',
    ],
)
def test_rejects_dtd_and_entity_declarations(tmp_path: Path, declaration: bytes) -> None:
    path = tmp_path / "entity.xlsx"
    write_package(path, {"xl/workbook.xml": declaration})

    with OoxmlPackage(path) as package, pytest.raises(OoxmlPackageError, match="DTDs or entities"):
        package.read_xml("xl/workbook.xml")


def test_rejects_relationships_that_escape_the_package(tmp_path: Path) -> None:
    path = tmp_path / "escape.pptx"
    relationships = RELATIONSHIPS.replace(
        b'Target="slides/slide1.xml"', b'Target="../../outside.xml"'
    )
    write_package(path, {"ppt/_rels/presentation.xml.rels": relationships})

    with OoxmlPackage(path) as package, pytest.raises(OoxmlPackageError, match="escapes"):
        package.relationships("ppt/presentation.xml")
