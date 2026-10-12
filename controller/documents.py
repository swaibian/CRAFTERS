"""REAL local document adapters operating on actual user files.

North star: chat about changes of a document → the agent does + sees +
reasons until finished. Each adapter:

- ``open(path)`` registers the file as a ``doc_id`` in the session and works
  on a COPY in the session work dir (never the original).
- ``inspect`` re-reads the working copy (the "see" step).
- Mutations snapshot the working copy first (lightweight revisions) and
  return before/after evidence; ``verify`` re-reads to confirm.
- Content hashes (sha256) prove transforms landed; image bytes and cell
  content never reach logs (counts/hashes/dims only).

Adapters: :class:`SheetAdapter` (.xlsx via openpyxl → gridcraft),
:class:`PhotoAdapter` (raster via PIL → photocraft), :class:`PdfAdapter`
(.pdf via pypdf + pymupdf → pdfcraft).

SW-REQ: SW-REQ-STREAM (document edit loop backing, TC-B controller side).
"""

from __future__ import annotations

import hashlib
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logger import get_logger, safe_event

log = get_logger()


class DocumentError(Exception):
    """Adapter failure (bad file, bad op, verify mismatch — safe message)."""


def content_hash(path: Path) -> str:
    """sha256 hex of a file (evidence that a transform landed).

    :param path: File to hash.
    :returns: ``"sha256:<hex>"``.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


@dataclass
class OpenDocument:
    """One open working copy in a session.

    :param doc_id: Stable id (``doc_<hex>``).
    :param kind: ``sheet`` | ``photo`` | ``pdf``.
    :param source_name: Original upload filename (display only).
    :param work_path: Working copy path (mutations land here).
    :param revision: Mutation counter (bumped per op, snapshot-guarded).
    :param revisions: Revision → backup path (lightweight snapshot store).
    """

    doc_id: str
    kind: str
    source_name: str
    work_path: Path
    revision: int = 0
    revisions: dict[int, Path] = field(default_factory=dict)


class DocumentRegistry:
    """Session work-dir registry: open docs + revision snapshots.

    :param work_dir: Session work dir (copies + ``.revisions/`` live here).
    """

    def __init__(self, work_dir: str | Path) -> None:
        self._work = Path(work_dir)
        self._work.mkdir(parents=True, exist_ok=True)
        self._rev_dir = self._work / ".revisions"
        self._rev_dir.mkdir(parents=True, exist_ok=True)
        self._docs: dict[str, OpenDocument] = {}

    @property
    def work_dir(self) -> Path:
        """Session work dir."""
        return self._work

    def register_copy(
        self, kind: str, source_name: str, work_path: Path
    ) -> OpenDocument:
        """Register a working copy (id + revision 0 snapshot).

        :param kind: ``sheet`` | ``photo`` | ``pdf``.
        :param source_name: Original filename (display only).
        :param work_path: Working copy path inside the work dir.
        :returns: The new :class:`OpenDocument`.
        """
        doc = OpenDocument(
            doc_id=f"doc_{secrets.token_hex(8)}",
            kind=kind,
            source_name=source_name,
            work_path=work_path,
        )
        self._docs[doc.doc_id] = doc
        self.snapshot(doc.doc_id, label="open")
        log.info(
            "doc opened: %s",
            safe_event(event="doc_open", adapter=kind, doc_id=doc.doc_id, ok=True),
        )
        return doc

    def get(self, doc_id: str) -> OpenDocument | None:
        """Return the open doc, or None if unknown."""
        return self._docs.get(doc_id)

    def snapshot(self, doc_id: str, label: str = "") -> int:
        """Copy the working file into ``.revisions/`` (pre-mutation guard).

        :param doc_id: Open document id.
        :param label: Human label (logged as op only).
        :returns: New revision number.
        :raises DocumentError: Unknown doc.
        """
        doc = self._docs.get(doc_id)
        if doc is None:
            raise DocumentError("unknown document")
        doc.revision += 1
        backup = self._rev_dir / f"{doc.doc_id}_r{doc.revision}{doc.work_path.suffix}"
        shutil.copy2(doc.work_path, backup)
        doc.revisions[doc.revision] = backup
        log.info(
            "doc snapshot: %s",
            safe_event(
                event="doc_snapshot",
                adapter=doc.kind,
                doc_id=doc.doc_id,
                revision=doc.revision,
                op=label,
                ok=True,
            ),
        )
        return doc.revision

    def restore(self, doc_id: str, revision: int) -> None:
        """Roll the working copy back to a prior revision.

        :param doc_id: Open document id.
        :param revision: Revision to restore.
        :raises DocumentError: Unknown doc or revision.
        """
        doc = self._docs.get(doc_id)
        if doc is None:
            raise DocumentError("unknown document")
        backup = doc.revisions.get(revision)
        if backup is None:
            raise DocumentError("unknown revision")
        shutil.copy2(backup, doc.work_path)
        doc.revision = revision


# --- gridcraft: .xlsx via openpyxl --------------------------------------------


class SheetAdapter:
    """Spreadsheet adapter (.xlsx via openpyxl → gridcraft semantics).

    :param registry: Session document registry (copies + snapshots).
    """

    KIND = "sheet"
    SUFFIXES = (".xlsx", ".xlsm")

    def __init__(self, registry: DocumentRegistry) -> None:
        self._registry = registry

    def open(self, source: Path, source_name: str) -> OpenDocument:
        """Copy ``source`` into the work dir and register it.

        :param source: Uploaded file path.
        :param source_name: Original filename.
        :returns: The open document.
        :raises DocumentError: Wrong suffix or unreadable workbook.
        """
        if source.suffix.lower() not in self.SUFFIXES:
            raise DocumentError(f"unsupported spreadsheet: {source.suffix}")
        dest = self._registry.work_dir / f"sheet_{secrets.token_hex(4)}_{source.name}"
        shutil.copy2(source, dest)
        try:
            import openpyxl

            wb = openpyxl.load_workbook(dest, data_only=False)
            wb.close()
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise DocumentError("cannot read workbook") from exc
        return self._registry.register_copy(self.KIND, source_name, dest)

    def inspect(self, doc_id: str) -> dict[str, Any]:
        """Re-read the working copy: sheets, dims, sample (the "see" step).

        :param doc_id: Open document id.
        :returns: ``{doc_id, kind, revision, content_hash, sheets: [{title,
            dims, max_row, max_column, sample}]}``.
        """
        doc = self._require(doc_id)
        import openpyxl

        wb = openpyxl.load_workbook(doc.work_path, data_only=False)
        try:
            sheets = []
            for ws in wb.worksheets:
                sample = []
                for row in ws.iter_rows(
                    min_row=1,
                    max_row=min(3, ws.max_row or 1),
                    max_col=min(4, ws.max_column or 1),
                    values_only=True,
                ):
                    sample.append(list(row))
                sheets.append(
                    {
                        "title": ws.title,
                        "dims": ws.dimensions,
                        "max_row": ws.max_row,
                        "max_column": ws.max_column,
                        "sample": sample,
                    }
                )
        finally:
            wb.close()
        evidence = {
            "doc_id": doc.doc_id,
            "kind": doc.kind,
            "revision": doc.revision,
            "content_hash": content_hash(doc.work_path),
            "sheets": sheets,
        }
        log.info(
            "sheet inspect: %s",
            safe_event(
                event="doc_inspect",
                adapter=self.KIND,
                doc_id=doc.doc_id,
                revision=doc.revision,
                count=len(sheets),
                ok=True,
            ),
        )
        return evidence

    def set_cell(
        self, doc_id: str, cell: str, value: Any, sheet: str | None = None
    ) -> dict[str, Any]:
        """Set a cell, snapshot-guarded, verified by re-reading.

        :param doc_id: Open document id.
        :param cell: A1-style address (validated).
        :param value: New value.
        :param sheet: Sheet title (defaults to active).
        :returns: Before/after evidence ``{before, after, revision}``.
        """
        import re

        from openpyxl.utils import column_index_from_string, get_column_letter

        match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", str(cell).upper())
        if not match:
            raise DocumentError(f"bad cell address: {cell}")
        doc = self._require(doc_id)
        before = self._read_cell(doc, match.group(0), sheet)
        self._registry.snapshot(doc_id, label="set_cell")
        import openpyxl

        wb = openpyxl.load_workbook(doc.work_path)
        try:
            ws = wb[sheet] if sheet else wb.active
            if ws is None:
                raise DocumentError("workbook has no sheets")
            col = column_index_from_string(match.group(1))
            row = int(match.group(2))
            ws.cell(row=row, column=col, value=value)
            wb.save(doc.work_path)
        finally:
            wb.close()
        after = self._read_cell(doc, match.group(0), sheet)
        if str(after) != str(value):
            raise DocumentError("verify failed: cell did not change")
        evidence = {
            "op": "set_cell",
            "cell": match.group(0),
            "column": get_column_letter(column_index_from_string(match.group(1))),
            "before": before,
            "after": after,
            "revision": doc.revision,
            "content_hash": content_hash(doc.work_path),
        }
        log.info(
            "sheet op: %s",
            safe_event(
                event="doc_mutate",
                adapter=self.KIND,
                doc_id=doc.doc_id,
                op="set_cell",
                revision=doc.revision,
                ok=True,
            ),
        )
        return evidence

    def add_sheet(self, doc_id: str, title: str) -> dict[str, Any]:
        """Add a worksheet, snapshot-guarded, verified by re-reading.

        :param doc_id: Open document id.
        :param title: New sheet title.
        :returns: Before/after evidence ``{before_sheets, after_sheets}``.
        """
        name = str(title or "").strip()
        if not name:
            raise DocumentError("sheet title is required")
        doc = self._require(doc_id)
        import openpyxl

        before = openpyxl.load_workbook(doc.work_path).sheetnames
        self._registry.snapshot(doc_id, label="add_sheet")
        wb = openpyxl.load_workbook(doc.work_path)
        try:
            if name in wb.sheetnames:
                raise DocumentError(f"sheet exists: {name}")
            wb.create_sheet(title=name)
            wb.save(doc.work_path)
        finally:
            wb.close()
        after = openpyxl.load_workbook(doc.work_path).sheetnames
        if name not in after:
            raise DocumentError("verify failed: sheet missing")
        evidence = {
            "op": "add_sheet",
            "before_sheets": before,
            "after_sheets": after,
            "revision": doc.revision,
            "content_hash": content_hash(doc.work_path),
        }
        log.info(
            "sheet op: %s",
            safe_event(
                event="doc_mutate",
                adapter=self.KIND,
                doc_id=doc.doc_id,
                op="add_sheet",
                revision=doc.revision,
                ok=True,
            ),
        )
        return evidence

    def _read_cell(self, doc: OpenDocument, cell: str, sheet: str | None) -> Any:
        import openpyxl

        wb = openpyxl.load_workbook(doc.work_path, data_only=False)
        try:
            ws = wb[sheet] if sheet else wb.active
            return ws[cell].value if ws is not None else None
        finally:
            wb.close()

    def _require(self, doc_id: str) -> OpenDocument:
        doc = self._registry.get(doc_id)
        if doc is None or doc.kind != self.KIND:
            raise DocumentError("unknown spreadsheet document")
        return doc


# --- photocraft: raster via PIL -------------------------------------------------


class PhotoAdapter:
    """Raster adapter (PIL → photocraft semantics).

    :param registry: Session document registry (copies + snapshots).
    """

    KIND = "photo"
    SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff")

    def __init__(self, registry: DocumentRegistry) -> None:
        self._registry = registry

    def open(self, source: Path, source_name: str) -> OpenDocument:
        """Copy ``source`` into the work dir and register it.

        :param source: Uploaded file path.
        :param source_name: Original filename.
        :returns: The open document.
        :raises DocumentError: Wrong suffix or unreadable image.
        """
        if source.suffix.lower() not in self.SUFFIXES:
            raise DocumentError(f"unsupported image: {source.suffix}")
        dest = self._registry.work_dir / f"photo_{secrets.token_hex(4)}_{source.name}"
        shutil.copy2(source, dest)
        try:
            from PIL import Image

            with Image.open(dest) as img:
                img.verify()
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise DocumentError("cannot read image") from exc
        return self._registry.register_copy(self.KIND, source_name, dest)

    def inspect(self, doc_id: str) -> dict[str, Any]:
        """Re-read the working copy: size, mode, histogram stats ("see").

        :param doc_id: Open document id.
        :returns: ``{doc_id, kind, revision, content_hash, width, height,
            mode, format, histogram_mean}`` (no pixels, stats only).
        """
        doc = self._require(doc_id)
        from PIL import Image

        with Image.open(doc.work_path) as img:
            img.load()
            gray = img.convert("L")
            hist = gray.histogram()
            total = sum(hist) or 1
            mean = sum(i * count for i, count in enumerate(hist)) / total
            evidence = {
                "doc_id": doc.doc_id,
                "kind": doc.kind,
                "revision": doc.revision,
                "content_hash": content_hash(doc.work_path),
                "width": img.width,
                "height": img.height,
                "mode": img.mode,
                "format": img.format,
                "histogram_mean": round(mean, 2),
            }
        log.info(
            "photo inspect: %s",
            safe_event(
                event="doc_inspect",
                adapter=self.KIND,
                doc_id=doc.doc_id,
                revision=doc.revision,
                ok=True,
            ),
        )
        return evidence

    def transform(self, doc_id: str, kind: str, **kwargs: Any) -> dict[str, Any]:
        """Transform the working copy, snapshot-guarded, verified by re-read.

        Kinds: ``resize`` (width/height, aspect kept when one side given),
        ``rotate`` (degrees, counter-clockwise, expand), ``convert``
        (format png/jpeg/webp), ``grayscale``, ``blur`` (radius).

        :param doc_id: Open document id.
        :param kind: Transform kind.
        :returns: Before/after evidence ``{before, after}`` with dims, mode,
            format, and content hashes proving the change landed.
        """
        doc = self._require(doc_id)
        before = self.inspect(doc_id)
        self._registry.snapshot(doc_id, label=f"transform:{kind}")
        from PIL import Image, ImageFilter

        with Image.open(doc.work_path) as img:
            img.load()
            out_format = (img.format or "PNG").upper()
            if kind == "resize":
                width = kwargs.get("width")
                height = kwargs.get("height")
                if width is None and height is None:
                    raise DocumentError("resize needs width and/or height")
                w, h = img.width, img.height
                if width is not None and height is not None:
                    size = (max(1, int(width)), max(1, int(height)))
                elif width is not None:
                    scale = int(width) / w
                    size = (max(1, int(width)), max(1, round(h * scale)))
                else:
                    scale = int(height) / h
                    size = (max(1, round(w * scale)), max(1, int(height)))
                img = img.resize(size, Image.LANCZOS)
            elif kind == "rotate":
                degrees = float(kwargs.get("degrees", 90))
                img = img.rotate(degrees, expand=True)
            elif kind == "convert":
                out_format = str(kwargs.get("format", "png")).upper().lstrip(".")
                if out_format == "JPG":
                    out_format = "JPEG"
                if out_format not in ("PNG", "JPEG", "WEBP"):
                    raise DocumentError(f"bad convert format: {out_format}")
                if out_format == "JPEG" and img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
            elif kind == "grayscale":
                img = img.convert("L")
            elif kind == "blur":
                radius = float(kwargs.get("radius", 2.0))
                img = img.filter(ImageFilter.GaussianBlur(radius))
            else:
                raise DocumentError(f"unknown transform: {kind}")
            save_path = doc.work_path.with_suffix(
                f".{out_format.lower()}" if kind == "convert" else doc.work_path.suffix
            )
            save_kwargs: dict[str, Any] = {}
            if out_format == "JPEG":
                save_kwargs["quality"] = 92
            img.save(save_path, out_format, **save_kwargs)
            if save_path != doc.work_path:
                save_path.replace(doc.work_path)
        after = self.inspect(doc_id)
        if after["content_hash"] == before["content_hash"] and kind != "convert":
            raise DocumentError("verify failed: content hash unchanged")
        evidence = {"op": f"transform:{kind}", "before": before, "after": after}
        log.info(
            "photo op: %s",
            safe_event(
                event="doc_mutate",
                adapter=self.KIND,
                doc_id=doc.doc_id,
                op=f"transform:{kind}",
                revision=doc.revision,
                ok=True,
            ),
        )
        return evidence

    def _require(self, doc_id: str) -> OpenDocument:
        doc = self._registry.get(doc_id)
        if doc is None or doc.kind != self.KIND:
            raise DocumentError("unknown photo document")
        return doc


# --- pdfcraft: .pdf via pypdf + pymupdf ------------------------------------------


class PdfAdapter:
    """PDF adapter (.pdf via pypdf + pymupdf → pdfcraft semantics).

    :param registry: Session document registry (copies + snapshots).
    """

    KIND = "pdf"
    SUFFIXES = (".pdf",)

    def __init__(self, registry: DocumentRegistry) -> None:
        self._registry = registry

    def open(self, source: Path, source_name: str) -> OpenDocument:
        """Copy ``source`` into the work dir and register it.

        :param source: Uploaded file path.
        :param source_name: Original filename.
        :returns: The open document.
        :raises DocumentError: Wrong suffix or unreadable PDF.
        """
        if source.suffix.lower() not in self.SUFFIXES:
            raise DocumentError(f"unsupported document: {source.suffix}")
        dest = self._registry.work_dir / f"pdf_{secrets.token_hex(4)}_{source.name}"
        shutil.copy2(source, dest)
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(dest))
            if len(reader.pages) == 0:
                raise DocumentError("pdf has no pages")
        except DocumentError:
            dest.unlink(missing_ok=True)
            raise
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise DocumentError("cannot read pdf") from exc
        return self._registry.register_copy(self.KIND, source_name, dest)

    def inspect(self, doc_id: str) -> dict[str, Any]:
        """Re-read the working copy: pages, sizes, text extract ("see").

        :param doc_id: Open document id.
        :returns: ``{doc_id, kind, revision, content_hash, pages: [{index,
            width_pt, height_pt, rotation, text_chars}]}``.
        """
        doc = self._require(doc_id)
        from pypdf import PdfReader

        reader = PdfReader(str(doc.work_path))
        pages = []
        for index, page in enumerate(reader.pages):
            box = page.mediabox
            try:
                text = page.extract_text() or ""
            except (AttributeError, ValueError):
                text = ""
            pages.append(
                {
                    "index": index,
                    "width_pt": round(float(box.width), 1),
                    "height_pt": round(float(box.height), 1),
                    "rotation": int(page.get("/Rotate") or 0),
                    "text_chars": len(text),
                }
            )
        evidence = {
            "doc_id": doc.doc_id,
            "kind": doc.kind,
            "revision": doc.revision,
            "content_hash": content_hash(doc.work_path),
            "pages": pages,
        }
        log.info(
            "pdf inspect: %s",
            safe_event(
                event="doc_inspect",
                adapter=self.KIND,
                doc_id=doc.doc_id,
                revision=doc.revision,
                count=len(pages),
                ok=True,
            ),
        )
        return evidence

    def render_thumbnail(self, doc_id: str, page: int = 0, max_side: int = 256) -> Path:
        """Render a page to a PNG thumbnail (pymupdf) for the "see" step.

        :param doc_id: Open document id.
        :param page: 0-based page index.
        :param max_side: Long-edge cap in pixels.
        :returns: Thumbnail PNG path inside the work dir.
        :raises DocumentError: Bad page index or render failure.
        """
        doc = self._require(doc_id)
        try:
            import fitz

            pdf = fitz.open(str(doc.work_path))
            try:
                if page < 0 or page >= pdf.page_count:
                    raise DocumentError(f"bad page index: {page}")
                pix = pdf[page].get_pixmap(
                    matrix=fitz.Matrix(
                        max_side / max(pdf[page].rect.width, 1),
                        max_side / max(pdf[page].rect.height, 1),
                    )
                )
                thumb = self._registry.work_dir / f"{doc.doc_id}_p{page}.png"
                pix.save(str(thumb))
                return thumb
            finally:
                pdf.close()
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError("thumbnail render failed") from exc

    def transform(
        self, doc_id: str, kind: str, page: int = 0, degrees: int = 90
    ) -> dict[str, Any]:
        """Rotate/delete pages, snapshot-guarded, verified by re-reading.

        :param doc_id: Open document id.
        :param kind: ``rotate`` (clockwise ``degrees`` on ``page``) or
            ``delete`` (remove ``page``).
        :param page: 0-based page index.
        :param degrees: Clockwise rotation (rotate only).
        :returns: Before/after evidence ``{before, after}``.
        """
        doc = self._require(doc_id)
        before = self.inspect(doc_id)
        if page < 0 or page >= len(before["pages"]):
            raise DocumentError(f"bad page index: {page}")
        self._registry.snapshot(doc_id, label=f"transform:{kind}")
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(str(doc.work_path))
        writer = PdfWriter()
        if kind == "rotate":
            for index, pg in enumerate(reader.pages):
                if index == page:
                    pg.rotate(int(degrees))
                writer.add_page(pg)
        elif kind == "delete":
            if len(reader.pages) <= 1:
                raise DocumentError("cannot delete the only page")
            for index, pg in enumerate(reader.pages):
                if index != page:
                    writer.add_page(pg)
        else:
            raise DocumentError(f"unknown transform: {kind}")
        with open(doc.work_path, "wb") as handle:
            writer.write(handle)
        after = self.inspect(doc_id)
        if after["content_hash"] == before["content_hash"]:
            raise DocumentError("verify failed: content hash unchanged")
        evidence = {"op": f"transform:{kind}", "before": before, "after": after}
        log.info(
            "pdf op: %s",
            safe_event(
                event="doc_mutate",
                adapter=self.KIND,
                doc_id=doc.doc_id,
                op=f"transform:{kind}",
                revision=doc.revision,
                ok=True,
            ),
        )
        return evidence

    def _require(self, doc_id: str) -> OpenDocument:
        doc = self._registry.get(doc_id)
        if doc is None or doc.kind != self.KIND:
            raise DocumentError("unknown pdf document")
        return doc


__all__ = [
    "DocumentError",
    "DocumentRegistry",
    "OpenDocument",
    "PdfAdapter",
    "PhotoAdapter",
    "SheetAdapter",
    "content_hash",
]
