"""PDF parsing and export service."""
from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_PAGES = 200


class PdfService:
    """Parse PDFs via pdfplumber and export markdown to PDF."""

    async def parse(self, path: Path) -> dict:
        """Parse a PDF file and extract text, tables, and metadata."""
        return await asyncio.to_thread(self._parse_sync, path)

    def _parse_sync(self, path: Path) -> dict:
        import pdfplumber

        if not path.is_file():
            raise FileNotFoundError(f"PDF not found: {path}")

        pages_out: list[dict] = []
        tables_out: list[str] = []
        all_text_parts: list[str] = []

        with pdfplumber.open(path) as pdf:
            metadata = dict(pdf.metadata) if pdf.metadata else {}
            page_count = len(pdf.pages)

            for i, page in enumerate(pdf.pages[:_MAX_PAGES]):
                text = page.extract_text() or ""
                all_text_parts.append(text)

                page_tables = page.extract_tables() or []
                md_tables: list[str] = []
                for table in page_tables:
                    if not table or not table[0]:
                        continue
                    header = table[0]
                    md = "| " + " | ".join(str(c or "") for c in header) + " |\n"
                    md += "| " + " | ".join("---" for _ in header) + " |\n"
                    for row in table[1:]:
                        md += "| " + " | ".join(str(c or "") for c in row) + " |\n"
                    md_tables.append(md)
                    tables_out.append(md)

                pages_out.append({
                    "page": i + 1,
                    "text": text,
                    "tables": md_tables,
                })

        return {
            "text": "\n\n".join(all_text_parts),
            "pages": pages_out,
            "tables": tables_out,
            "metadata": metadata,
            "page_count": page_count,
        }

    async def export(self, content: str, output_path: Path) -> Path:
        """Convert markdown content to PDF."""
        return await asyncio.to_thread(self._export_sync, content, output_path)

    def _export_sync(self, content: str, output_path: Path) -> Path:
        import markdown as md_lib

        html_body = md_lib.markdown(content, extensions=["tables", "fenced_code"])
        full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: sans-serif; max-width: 800px; margin: 2em auto; line-height: 1.6; }}
table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
th {{ background: #f5f5f5; }}
pre {{ background: #f8f8f8; padding: 12px; border-radius: 4px; overflow-x: auto; }}
code {{ font-family: monospace; }}
@media print {{ body {{ margin: 0; }} }}
</style>
</head><body>{html_body}</body></html>"""

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Try weasyprint first, fall back to pandoc
        try:
            from weasyprint import HTML
            HTML(string=full_html).write_pdf(str(output_path))
            return output_path
        except ImportError:
            logger.info("weasyprint not available, falling back to pandoc")

        # Pandoc fallback: write temp HTML, convert
        tmp_html = output_path.with_suffix(".tmp.html")
        try:
            tmp_html.write_text(full_html, encoding="utf-8")
            subprocess.run(
                ["pandoc", str(tmp_html), "-o", str(output_path), "--pdf-engine=wkhtmltopdf"],
                check=True,
                capture_output=True,
                timeout=60,
            )
            return output_path
        finally:
            tmp_html.unlink(missing_ok=True)
