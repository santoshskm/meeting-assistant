from datetime import datetime
from pathlib import Path

from config import EXPORTS_DIR


class ReportGenerator:

    def __init__(self):
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def save(self, transcript: str, summary: str, app_name: str, fmt: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = EXPORTS_DIR / f"meeting_notes_{stamp}.{fmt}"

        if fmt == "md":
            self._write_markdown(path, transcript, summary, app_name)
        elif fmt == "pdf":
            path = self._write_pdf(path, transcript, summary, app_name)

        return str(path)

    # --- formats ---

    def _write_markdown(self, path: Path, transcript: str, summary: str, app_name: str):
        now = datetime.now()
        content = f"""# Meeting Report

**Date:** {now.strftime("%B %d, %Y")}
**Time:** {now.strftime("%I:%M %p")}
**Platform:** {app_name}

---

## AI Summary & Action Items

{summary.strip() if summary.strip() else "_No summary generated._"}

---

## Full Transcript

{transcript}
"""
        path.write_text(content, encoding="utf-8")

    def _write_pdf(self, path: Path, transcript: str, summary: str, app_name: str) -> Path:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.platypus import (
                HRFlowable,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
            )

            doc = SimpleDocTemplate(
                str(path), pagesize=A4,
                rightMargin=inch, leftMargin=inch,
                topMargin=inch, bottomMargin=inch,
            )
            styles = getSampleStyleSheet()
            now = datetime.now()
            story = []

            story.append(Paragraph("Meeting Report", styles["Title"]))
            story.append(Spacer(1, 10))
            for line in [
                f"<b>Date:</b> {now.strftime('%B %d, %Y')}",
                f"<b>Time:</b> {now.strftime('%I:%M %p')}",
                f"<b>Platform:</b> {app_name}",
            ]:
                story.append(Paragraph(line, styles["Normal"]))
            story.append(Spacer(1, 10))
            story.append(HRFlowable(width="100%"))
            story.append(Spacer(1, 10))

            story.append(Paragraph("Summary & Action Items", styles["Heading1"]))
            for line in (summary.strip() or "_No summary generated._").splitlines():
                if line.strip():
                    story.append(Paragraph(line.strip(), styles["Normal"]))
                    story.append(Spacer(1, 3))

            story.append(Spacer(1, 12))
            story.append(HRFlowable(width="100%"))
            story.append(Spacer(1, 10))

            story.append(Paragraph("Full Transcript", styles["Heading1"]))
            mono = ParagraphStyle("mono", parent=styles["Normal"], fontSize=9, spaceAfter=3)
            for line in transcript.splitlines():
                if line.strip():
                    story.append(Paragraph(line, mono))

            doc.build(story)
            return path

        except ImportError:
            # Fall back to markdown if reportlab is not installed
            md_path = path.with_suffix(".md")
            self._write_markdown(md_path, transcript, summary, app_name)
            return md_path