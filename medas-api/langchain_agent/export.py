"""Rendering a conversation as a PDF, for the agent's export tool.

Pure apart from the one write in `export_conversation`: the turns come from
the run's own state, so the model cannot ask for any conversation but the one
it is in.
"""

import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

__all__ = ["EXPORT_DIR", "conversation_pdf", "export_conversation"]

EXPORT_DIR = Path("exports")


def conversation_pdf(turns: list[dict], path: Path) -> None:
    """Write `turns` (each a role and its content) to `path`, oldest first."""
    styles = getSampleStyleSheet()
    story = []
    for turn in turns:
        speaker = "You" if turn["role"] == "user" else "Medas"
        # Paragraph reads its text as markup, so the turn is escaped.
        story.append(Paragraph(f"<b>{speaker}</b>", styles["Heading4"]))
        story.append(Paragraph(escape(turn["content"]), styles["BodyText"]))
        story.append(Spacer(1, 8))

    SimpleDocTemplate(str(path), pagesize=A4, title="Medas conversation").build(story)


def export_conversation(turns: list[dict]) -> str:
    """Write the conversation to a new file in EXPORT_DIR; returns its name."""
    EXPORT_DIR.mkdir(exist_ok=True)
    path = EXPORT_DIR / f"conversation-{uuid.uuid4()}.pdf"
    conversation_pdf(turns, path)
    return path.name
