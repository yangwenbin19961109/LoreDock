"""Small, deterministic parsers used by the retrieval experiments."""

from dataclasses import dataclass
from pathlib import Path

from docx import Document
from pypdf import PdfReader


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    source_id: str
    title: str
    text: str
    page_spans: tuple[tuple[int, int, int], ...] = ()

    def page_at(self, char_offset: int) -> int | None:
        for page, start, end in self.page_spans:
            if start <= char_offset < end:
                return page
        return None


def _parse_pdf(path: Path) -> ParsedDocument:
    parts: list[str] = []
    spans: list[tuple[int, int, int]] = []
    cursor = 0
    for page_number, page in enumerate(PdfReader(path).pages, start=1):
        text = page.extract_text() or ""
        if parts:
            parts.append("\n\n")
            cursor += 2
        start = cursor
        parts.append(text)
        cursor += len(text)
        spans.append((page_number, start, cursor))
    return ParsedDocument(path.stem, path.stem, "".join(parts), tuple(spans))


def _parse_docx(path: Path) -> ParsedDocument:
    paragraphs = [paragraph.text for paragraph in Document(str(path)).paragraphs]
    return ParsedDocument(path.stem, path.stem, "\n\n".join(paragraphs))


def parse_path(
    path: Path, *, source_id: str | None = None, allowed_root: Path | None = None
) -> ParsedDocument:
    """Parse a supported local file without modifying the source."""

    resolved = path.resolve(strict=True)
    if allowed_root is not None:
        root = allowed_root.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError("Document path is outside the allowed root")
    suffix = resolved.suffix.lower()
    if suffix == ".pdf":
        parsed = _parse_pdf(resolved)
    elif suffix == ".docx":
        parsed = _parse_docx(resolved)
    elif suffix in {".md", ".markdown", ".txt"}:
        parsed = ParsedDocument(resolved.stem, resolved.stem, resolved.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"Unsupported document type: {suffix or '<none>'}")
    if source_id is None:
        return parsed
    return ParsedDocument(source_id, parsed.title, parsed.text, parsed.page_spans)
