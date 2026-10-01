"""Writing a conversation to a file, for the agent's export tool.

csv and json are written from the turns with the standard library; anything
else is a PDF, rendered from markdown by markdown-pdf. Pure apart from the one
write in `export_turns`: the turns come from the run's own state, so the model
cannot ask for any conversation but the one it is in.
"""

import csv
import io
import json
import re
import uuid
from pathlib import Path

from markdown_pdf import MarkdownPdf, Section

__all__ = ["EXPORT_DIR", "export_turns"]

EXPORT_DIR = Path("exports")
TITLE = "Medas conversation"

_SPEAKERS = {"user": "You", "assistant": "Medas"}
# A line a turn must not start with: an unclosed code fence would swallow the
# turns after it, and a heading would pass for a new speaker.
_RESERVED = re.compile(r"^(#|```|~~~)")


def _write_pdf(turns: list[dict], path: Path) -> None:
    parts = [f"# {TITLE}"]
    for turn in turns:
        lines = [
            f"\\{line}" if _RESERVED.match(line) else line
            for line in turn["content"].strip().splitlines()
        ]
        parts.append(f"### {_SPEAKERS[turn['role']]}\n\n" + "\n".join(lines))

    # js-default is markdown-it's preset with raw HTML off, so markup in a turn
    # is printed, not passed through. root is where an image path would be read
    # from: the export folder, which holds no images.
    pdf = MarkdownPdf(toc_level=0, mode="js-default")
    pdf.meta["title"] = TITLE
    pdf.add_section(Section("\n\n".join(parts), toc=False, root=str(path.parent)))
    pdf.save(path)


def _write_csv(turns: list[dict], path: Path) -> None:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["turn", "role", "content"])
    for number, turn in enumerate(turns, start=1):
        content = turn["content"]
        # A cell that starts like a formula would run when opened in a spreadsheet.
        if content.startswith(("=", "+", "-", "@", "\t", "\r")):
            content = "'" + content
        writer.writerow([number, turn["role"], content])
    # utf-8-sig so Excel reads accents; newline="" keeps csv's own line ends.
    path.write_text(out.getvalue(), encoding="utf-8-sig", newline="")


def _write_json(turns: list[dict], path: Path) -> None:
    document = {"title": TITLE, "turns": turns}
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


_WRITERS = {"csv": _write_csv, "json": _write_json}


def export_turns(turns: list[dict], fmt: str) -> tuple[str, str]:
    """Write the conversation to a new file in EXPORT_DIR, as csv or json when
    asked for, otherwise as a PDF. Returns the file name and the format used."""
    fmt = fmt.strip().lower().lstrip(".")
    if fmt not in _WRITERS:
        fmt = "pdf"
    EXPORT_DIR.mkdir(exist_ok=True)
    path = EXPORT_DIR / f"conversation-{uuid.uuid4()}.{fmt}"
    _WRITERS.get(fmt, _write_pdf)(turns, path)
    return path.name, fmt
