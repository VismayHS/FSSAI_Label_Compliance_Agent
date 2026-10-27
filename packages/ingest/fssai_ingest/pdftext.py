"""PDF text extraction. The corpus PDFs carry a text layer, so no OCR is needed (data/corpus/manifest.json)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

MIN_CHARS_FOR_TEXT_PAGE = 50


@lru_cache(maxsize=16)
def _page_texts(path: str, mtime_ns: int, size: int) -> tuple[str, ...]:
    return tuple(page.extract_text() or "" for page in PdfReader(path).pages)


def page_texts(path: Path) -> list[str]:
    """One string per page, in reading order as pypdf extracts it. Cached per file version, because a
    build reads every PDF twice (fingerprint, then chunking) and extraction dominates its run time."""
    st = Path(path).stat()
    return list(_page_texts(str(path), st.st_mtime_ns, st.st_size))


def has_text_layer(pages: list[str], threshold: float = 0.9) -> bool:
    """True if at least `threshold` of the pages have extractable text (else the file needs OCR)."""
    if not pages:
        return False
    with_text = sum(1 for p in pages if len(p.strip()) >= MIN_CHARS_FOR_TEXT_PAGE)
    return with_text / len(pages) >= threshold
