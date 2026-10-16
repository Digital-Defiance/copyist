"""Engraving: music21 score → MusicXML → SVG pages (Verovio) → PDF (PyMuPDF).

Verovio's SVG leans on CSS and an embedded SMuFL web font, neither of which
MuPDF's SVG renderer reads, so `printable_svg` rewrites each page into plain
SVG first (see DECISIONS.md, 2026-10-16).
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import pymupdf
import verovio
from music21 import stream

# US Letter. Verovio measures pages in tenths of a millimetre; PDF in points.
LETTER_MM10 = (2159, 2794)
LETTER_PT = (612, 792)

BASE_OPTIONS = {
    "pageWidth": LETTER_MM10[0],
    "pageHeight": LETTER_MM10[1],
    "pageMarginTop": 120,
    "pageMarginBottom": 120,
    "pageMarginLeft": 150,
    "pageMarginRight": 150,
    "scale": 45,
    "breaks": "auto",
    "header": "auto",
    "footer": "none",
    "lyricSize": 4.2,
    "lyricWordSpace": 2.0,
    "spacingLinear": 0.3,
    "spacingNonLinear": 0.62,
    "spacingSystem": 10,
    "justifyVertically": False,
    "adjustPageHeight": False,
    "fontTextLiberation": True,
}

# SMuFL metronome glyphs (Verovio writes them in its embedded font) and the
# Unicode characters MuPDF can draw instead.
SMUFL_TEXT = {
    # Metronome marks range (what Verovio uses in tempo marks)
    chr(0xECA2): chr(0x1D15D),  # whole note
    chr(0xECA3): chr(0x1D15E),  # half note
    chr(0xECA5): chr(0x2669),   # quarter note
    chr(0xECA7): chr(0x266A),   # eighth note
    chr(0xECB7): ".",           # augmentation dot
    # Individual notes range
    chr(0xE1D2): chr(0x1D15D),
    chr(0xE1D3): chr(0x1D15E),
    chr(0xE1D5): chr(0x2669),
    chr(0xE1D7): chr(0x266A),
    chr(0xE1E7): ".",
}


def write_musicxml(score: stream.Score, path: Path, credits: dict | None = None) -> Path:
    """Write MusicXML, adding page-one credits (title, words, music) that engravers print."""
    path.parent.mkdir(parents=True, exist_ok=True)
    score.write("musicxml", fp=str(path))
    if credits:
        add_credits(path, credits)
    return path


def add_credits(path: Path, credits: dict) -> None:
    """Insert MusicXML <credit> elements for the title and the words and music credits."""
    def credit(kind: str, text: str, justify: str, valign: str, size: int, x: int, y: int) -> str:
        return (f'  <credit page="1">\n    <credit-type>{kind}</credit-type>\n'
                f'    <credit-words default-x="{x}" default-y="{y}" justify="{justify}" valign="{valign}" '
                f'font-size="{size}">{html.escape(text)}</credit-words>\n  </credit>\n')
    # The title comes from the MusicXML <work-title>; Verovio prints it large and
    # centred on its own. A title <credit> would replace it with small type.
    parts = []
    if credits.get("words"):
        parts.append(credit("lyricist", f"Words: {credits['words']}", "left", "bottom", 10, 80, 1450))
    if credits.get("music"):
        parts.append(credit("composer", f"Music: {credits['music']}", "right", "bottom", 10, 1120, 1450))
    xml = path.read_text(encoding="utf-8")
    xml = re.sub(r"\s*<credit[ >].*?</credit>", "", xml, flags=re.S)
    xml = xml.replace("<part-list>", "".join(parts) + "  <part-list>", 1)
    path.write_text(xml, encoding="utf-8")


def write_midi(score: stream.Score, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    score.write("midi", fp=str(path))
    return path


def render_svgs(musicxml: Path, options: dict | None = None, header: dict | None = None) -> list[str]:
    """Engrave a MusicXML file with Verovio; one SVG string per page.

    `header` sets the page-one header: title, subtitle, left (words) and right
    (music) lines. Verovio's own MusicXML header drops the title when credits
    are present, so the header is written into the MEI directly.
    """
    tk = verovio.toolkit()
    tk.setOptions({**BASE_OPTIONS, **(options or {})})
    if not tk.loadFile(str(musicxml)):
        raise RuntimeError(f"Verovio couldn't read {musicxml}")
    if header:
        tk.loadData(with_header(tk.getMEI(), header))
    return [tk.renderToSVG(page) for page in range(1, tk.getPageCount() + 1)]


def with_header(mei: str, header: dict) -> str:
    """Replace the MEI page-one header with title, subtitle and left/right credit lines."""
    esc = html.escape
    rows = []
    if header.get("title"):
        rows.append(f'<rend halign="center" valign="top"><rend fontsize="x-large">{esc(header["title"])}</rend>'
                    + (f'<lb/><rend fontsize="small">{esc(header["subtitle"])}</rend>' if header.get("subtitle") else "")
                    + "</rend>")
    if header.get("left"):
        rows.append(f'<rend halign="left" valign="bottom">{esc(header["left"])}</rend>')
    if header.get("right"):
        rows.append(f'<rend halign="right" valign="bottom">{esc(header["right"])}</rend>')
    block = '<pgHead func="first">' + "".join(rows) + "</pgHead>"
    if "<pgHead" in mei:
        return re.sub(r"<pgHead[^>]*>.*?</pgHead>", block, mei, count=1, flags=re.S)
    return re.sub(r"(<scoreDef[^>]*>)", r"\1" + block, mei, count=1)


def printable_svg(svg: str) -> str:
    """Rewrite a Verovio page into SVG that MuPDF renders correctly.

    - The nested <svg class="definition-scale"> becomes a scaled <g>.
    - Shapes get an explicit stroke (Verovio sets it in CSS).
    - Metronome glyphs in the SMuFL web font become Unicode note characters.
    - The page is sized as US Letter in points.
    """
    outer = re.search(r'<svg[^>]*?\swidth="([\d.]+)px"\s+height="([\d.]+)px"', svg)
    inner = re.search(r'<svg class="definition-scale"([^>]*)viewBox="0 0 ([\d.]+) ([\d.]+)"([^>]*)>', svg)
    if not outer or not inner:
        return svg
    w, h = float(outer.group(1)), float(outer.group(2))
    iw, ih = float(inner.group(2)), float(inner.group(3))
    attrs = (inner.group(1) + inner.group(4)).strip()
    svg = svg[:inner.start()] + f'<g transform="scale({w / iw:.6f}, {h / ih:.6f})" {attrs}>' + svg[inner.end():]
    last = svg.rfind("</svg>")
    prev = svg.rfind("</svg>", 0, last)
    svg = svg[:prev] + "</g>" + svg[prev + len("</svg>"):]
    svg = re.sub(r"<(path|rect|polygon|polyline|ellipse)(?=[\s/>])", r'<\1 stroke="black"', svg)

    def smufl(m: re.Match) -> str:
        size = float(m.group(1)) * 0.62
        text = "".join(SMUFL_TEXT.get(c, c) for c in m.group(2))
        return f'<tspan font-size="{size:.0f}px">{text}</tspan>'
    svg = re.sub(r'<tspan font-family="Leipzig" font-size="([\d.]+)px">([^<]*)</tspan>', smufl, svg)
    svg = re.sub(r'(<svg[^>]*?\s)width="[\d.]+px"\s+height="[\d.]+px"',
                 rf'\1width="{LETTER_PT[0]}px" height="{LETTER_PT[1]}px" viewBox="0 0 {w:g} {h:g}"', svg, count=1)
    return svg


def svgs_to_pdf(svgs: list[str], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pymupdf.open()
    for svg in svgs:
        page_doc = pymupdf.open(stream=printable_svg(svg).encode("utf-8"), filetype="svg")
        pdf.insert_pdf(pymupdf.open("pdf", page_doc.convert_to_pdf()))
    pdf.save(str(path), garbage=3, deflate=True)
    return path


def header_for(title: str, credits: dict | None, subtitle: str | None = None) -> dict:
    credits = credits or {}
    return {
        "title": title,
        "subtitle": subtitle,
        "left": f"Words: {credits['words']}" if credits.get("words") else None,
        "right": f"Music: {credits['music']}" if credits.get("music") else None,
    }


def engrave(score: stream.Score, out_dir: Path, name: str, title: str, credits: dict | None = None,
            subtitle: str | None = None, options: dict | None = None) -> dict[str, Path]:
    """Write <name>.musicxml and <name>.pdf; return their paths."""
    xml = write_musicxml(score, out_dir / f"{name}.musicxml", credits)
    svgs = render_svgs(xml, options, header_for(title, credits, subtitle))
    pdf = svgs_to_pdf(svgs, out_dir / f"{name}.pdf")
    return {"musicxml": xml, "pdf": pdf}


def pdf_page_images(pdf: Path, dpi: int = 100) -> list[Path]:
    """Render each PDF page to PNG next to the PDF, for checking by eye."""
    out = []
    doc = pymupdf.open(str(pdf))
    for i, page in enumerate(doc, start=1):
        png = pdf.with_name(f"{pdf.stem}-p{i}.png")
        page.get_pixmap(dpi=dpi).save(str(png))
        out.append(png)
    return out
