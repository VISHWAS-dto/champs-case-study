"""Build memo/final_memo.pdf from memo/final_memo.md with headless Chrome (no Python packages needed).

Usage:
    python3 memo/build_memo.py            # CHROME=/path/to/chrome to override the default macOS path

The converter handles only what the memo uses: # / ## headings, paragraphs, **bold**, *italic*,
`code`, [links](url), fenced code blocks, "- " lists and pipe tables. Prints the page count.
"""

import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC, OUT = HERE / "final_memo.md", HERE / "final_memo.pdf"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

CSS = """
@page { size: A4; margin: 10mm 11mm; }
body { font: 8.6pt/1.32 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1d1d1b; margin: 0; }
h1 { font-size: 15pt; color: #17406d; margin: 0 0 2px; }
h2 { font-size: 9.6pt; color: #17406d; text-transform: uppercase; letter-spacing: .02em; margin: 7px 0 2px; }
h1 + p { color: #555; border-bottom: 1.5px solid #17406d; padding-bottom: 4px; margin-bottom: 4px; }
p { margin: 0 0 3px; }
ul { margin: 1px 0 3px; padding-left: 14px; } li { margin: 0; }
code { font: 8.1pt Menlo, monospace; background: #eef1f5; padding: 0 2px; border-radius: 2px; }
pre { font: 8.1pt/1.35 Menlo, monospace; background: #eef1f5; border-left: 3px solid #17406d;
      padding: 3px 6px; margin: 2px 0 3px; white-space: pre-wrap; }
table { border-collapse: collapse; width: 100%; margin: 3px 0 2px; font-size: 8.3pt; }
th, td { border: 1px solid #d5dbe3; padding: 1.5px 5px; text-align: left; vertical-align: top; }
th { background: #eef1f5; }
a { color: #17406d; }
"""


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![*\w])\*([^*]+)\*(?![*\w])", r"<i>\1</i>", s)
    return s


def to_html(md):
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            j = i + 1
            while not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
        elif line.startswith("# "):
            out.append(f"<h1>{inline(line[2:])}</h1>"); i += 1
        elif line.startswith("## "):
            out.append(f"<h2>{inline(line[3:])}</h2>"); i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")]); i += 1
            head, body = rows[0], rows[2:]
            out.append("<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
                       + "</table>")
        elif line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
        elif line.strip():
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"(#|\||```|- )", lines[i]):
                para.append(lines[i]); i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
        else:
            i += 1
    return "\n".join(out)


def main():
    page = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{to_html(SRC.read_text())}</body></html>"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "memo.html"
        src.write_text(page)
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={OUT}", src.as_uri()], check=True, capture_output=True)
    pages = len(re.findall(rb"/Type\s*/Page(?!s)", OUT.read_bytes()))
    print(f"wrote {OUT.relative_to(HERE.parent)}: {pages} page(s)")
    return 0 if pages == 1 else 1


if __name__ == "__main__":
    sys.exit(main())
