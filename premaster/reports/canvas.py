# -*- coding: utf-8 -*-
"""Llenç PDF mínim (sense dependències) i ajudes de maquetació compartides pels informes.

El mateix codi de maquetació dibuixa al PDF o a la pantalla (vista prèvia):
qualsevol objecte amb new_page(), text(), rect() i line() serveix.
"""
import datetime
import zlib

from .pdf_metrics import HELVETICA, HELVETICA_BOLD

PAGE_W, PAGE_H = 595.28, 841.89
MARGIN = 50.0
CONTENT_W = PAGE_W - 2 * MARGIN
BOTTOM = 56.0

NAVY = (0.122, 0.227, 0.373)
TEXT = (0.114, 0.153, 0.2)
MUTED = (0.365, 0.42, 0.478)
WHITE = (1, 1, 1)
ROW_ALT = (0.949, 0.961, 0.976)
GRID = (0.835, 0.863, 0.898)
RED = (0.753, 0.224, 0.169)
AMBER = (0.604, 0.42, 0.0)
GREEN = (0.18, 0.545, 0.341)
FILL = {"red": (0.976, 0.851, 0.831), "yellow": (1.0, 0.945, 0.776), "ok": None, None: None,
        "green": (0.851, 0.937, 0.882)}
INK = {"red": RED, "yellow": AMBER, "ok": TEXT, "green": GREEN, None: TEXT}

_SUBST = {u"⅓": " 1/3", u"→": "->", u"≤": "<=", u"≥": ">=", u"−": "-", u"✓": "OK", u"■": "#"}


def _enc(s):
    for k, v in _SUBST.items():
        s = s.replace(k, v)
    return s.encode("cp1252", "replace")


def text_width(s, size, bold=False):
    table = HELVETICA_BOLD if bold else HELVETICA
    total = 0
    for b in bytearray(_enc(s)):
        total += table[b - 32] if 32 <= b <= 255 else 556
    return total * size / 1000.0


def fit(s, size, bold, width):
    if text_width(s, size, bold) <= width:
        return s
    lo, hi = 0, len(s)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_width(s[:mid] + u"…", size, bold) <= width:
            lo = mid
        else:
            hi = mid - 1
    return s[:lo].rstrip() + u"…"


def wrap(s, size, bold, width):
    lines, cur = [], ""
    for w in s.split(" "):
        cand = (cur + " " + w) if cur else w
        if text_width(cand, size, bold) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _esc(b):
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class PdfCanvas(object):
    def __init__(self):
        self.pages = []
        self.ops = None

    def new_page(self):
        self.ops = []
        self.pages.append(self.ops)

    def text(self, x, y, s, size=10, bold=False, color=TEXT, align="left", italic=False):
        if align == "right":
            x -= text_width(s, size, bold)
        elif align == "center":
            x -= text_width(s, size, bold) / 2.0
        font = b"F2" if bold else (b"F3" if italic else b"F1")
        self.ops.append(b"BT /%s %.2f Tf %.3f %.3f %.3f rg %.2f %.2f Td (%s) Tj ET" % (
            font, size, color[0], color[1], color[2], x, y, _esc(_enc(s))))

    def rect(self, x, y, w, h, fill):
        self.ops.append(b"%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f" % (fill[0], fill[1], fill[2], x, y, w, h))

    def line(self, x1, y1, x2, y2, color=GRID, width=0.6):
        self.ops.append(b"%.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S" % (
            color[0], color[1], color[2], width, x1, y1, x2, y2))

    def save(self, path, title):
        objs = []

        def add(body):
            objs.append(body)
            return len(objs)

        cat_id = add(None)
        pages_id = add(None)
        fonts = []
        for base in (b"Helvetica", b"Helvetica-Bold", b"Helvetica-Oblique"):
            fonts.append(add(b"<< /Type /Font /Subtype /Type1 /BaseFont /" + base + b" /Encoding /WinAnsiEncoding >>"))
        kids = []
        for ops in self.pages:
            data = zlib.compress(b"\n".join(ops))
            cid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data) + data + b"\nendstream")
            pid = add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Resources << /Font << "
                       "/F1 %d 0 R /F2 %d 0 R /F3 %d 0 R >> >> /Contents %d 0 R >>"
                       % (pages_id, PAGE_W, PAGE_H, fonts[0], fonts[1], fonts[2], cid)).encode("ascii"))
            kids.append(pid)
        objs[cat_id - 1] = ("<< /Type /Catalog /Pages %d 0 R >>" % pages_id).encode("ascii")
        objs[pages_id - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
                              % (" ".join("%d 0 R" % k for k in kids), len(kids))).encode("ascii")
        now = datetime.datetime.now().strftime("D:%Y%m%d%H%M%S")
        title_hex = (u"﻿" + title).encode("utf-16-be").hex().upper().encode("ascii")
        info = add(b"<< /Title <" + title_hex + b"> /Producer (VinylPremaster) /CreationDate (" +
                   now.encode("ascii") + b") >>")
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objs, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += (b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objs) + 1, cat_id, info, xref))
        with open(path, "wb") as f:
            f.write(bytes(out))


class Doc(object):
    """Maquetació en flux (de dalt a baix) amb salts de pàgina, capçalera i peu."""

    def __init__(self, c, footer_left):
        self.c = c
        self.footer_left = footer_left
        self.page = 0
        self.y = 0.0
        self.new_page()

    def _footer(self):
        c = self.c
        c.line(MARGIN, 38, PAGE_W - MARGIN, 38, GRID, 0.5)
        c.text(MARGIN, 26, fit(self.footer_left, 7.5, False, CONTENT_W - 60), 7.5, False, MUTED)
        c.text(PAGE_W - MARGIN, 26, "Pág. %d" % self.page, 7.5, False, MUTED, "right")

    def new_page(self):
        if self.page:
            self._footer()
        self.c.new_page()
        self.page += 1
        self.c.rect(0, PAGE_H - 14, PAGE_W, 14, NAVY)
        self.y = PAGE_H - MARGIN

    def need(self, h):
        if self.y - h < BOTTOM:
            self.new_page()
            return True
        return False

    def gap(self, h):
        self.y -= h

    def finish(self):
        self._footer()
        return self.page

    # --- blocs de text ---------------------------------------------------
    def title(self, title, sub_lines):
        c = self.c
        y = self.y - 8
        c.text(PAGE_W / 2, y, fit(title, 19, True, CONTENT_W), 19, True, NAVY, "center")
        y -= 19
        for s in sub_lines:
            c.text(PAGE_W / 2, y, fit(s, 9, False, CONTENT_W), 9, False, MUTED, "center")
            y -= 12
        y += 2
        c.line(MARGIN, y, PAGE_W - MARGIN, y, NAVY, 1.2)
        self.y = y - 20

    def h1(self, text):
        self.need(40)
        self.c.text(MARGIN, self.y - 12, text, 13, True, NAVY)
        self.y -= 24

    def runs(self, runs, size=9.5, indent=0.0, lead=12.5, width=None):
        """Paràgraf amb trams de format: [(text, bold, color)], amb ajust de línia."""
        width = (width or CONTENT_W) - indent
        words = []
        for text, bold, color in runs:
            for i, w in enumerate(text.split(" ")):
                if w == "" and i:
                    continue
                words.append((w, bold, color))
        lines, cur, cur_w = [], [], 0.0
        space = text_width(" ", size)
        for w, bold, color in words:
            ww = text_width(w, size, bold)
            add = ww + (space if cur else 0)
            if cur and cur_w + add > width:
                lines.append(cur)
                cur, cur_w = [], 0.0
                add = ww
            cur.append((w, bold, color))
            cur_w += add
        if cur:
            lines.append(cur)
        for ln in lines:
            self.need(lead)
            x = MARGIN + indent
            for i, (w, bold, color) in enumerate(ln):
                if i:
                    x += space
                self.c.text(x, self.y - size, w, size, bold, color)
                x += text_width(w, size, bold)
            self.y -= lead
        return len(lines)

    def para(self, text, size=9.5, bold=False, color=TEXT, indent=0.0, after=5.0):
        self.runs([(text, bold, color)], size=size, indent=indent)
        self.y -= after

    def bullet(self, lead_text, text, size=9.5, lead_color=TEXT):
        self.need(14)
        self.c.text(MARGIN + 2, self.y - size, u"•", size, True, NAVY)
        runs = []
        if lead_text:
            runs.append((lead_text, True, lead_color))
        if text:
            runs.append((text, False, TEXT))
        self.runs(runs, size=size, indent=12)
        self.y -= 3

    def note(self, text, size=7.5):
        self.need(12)
        self.runs([(text, False, MUTED)], size=size, lead=10)

    # --- taula -------------------------------------------------------------
    def table(self, cols, rows, head_size=7.5, body_size=8.3, row_h=16.0, separators=()):
        """cols: [(capçalera, amplada, alineació)]; rows: [[cel·la]], cel·la = text o dict(text, status, bold, color, sub).
        separators: índexs de fila abans dels quals es dibuixa una línia gruixuda (canvi de cara)."""
        c = self.c
        total_w = sum(w for _, w, _ in cols)
        scale = CONTENT_W / total_w if total_w > CONTENT_W else 1.0
        cols = [(h, w * scale, a) for h, w, a in cols]
        head_lines = [wrap(h, head_size, True, w - 6) for h, w, _ in cols]
        hh = 6 + 9.5 * max(len(x) for x in head_lines)

        def header():
            self.need(hh + row_h)
            y = self.y
            c.rect(MARGIN, y - hh, sum(w for _, w, _ in cols), hh, NAVY)
            x = MARGIN
            for (h, w, a), lines in zip(cols, head_lines):
                ty = y - 4 - head_size
                for ln in lines:
                    if a == "right":
                        c.text(x + w - 4, ty, ln, head_size, True, WHITE, "right")
                    elif a == "center":
                        c.text(x + w / 2, ty, ln, head_size, True, WHITE, "center")
                    else:
                        c.text(x + 4, ty, ln, head_size, True, WHITE)
                    ty -= 9.5
                x += w
            self.y = y - hh

        header()
        width = sum(w for _, w, _ in cols)
        for i, row in enumerate(rows):
            has_sub = any(isinstance(cell, dict) and cell.get("sub") for cell in row)
            h = row_h + (8.5 if has_sub else 0)
            if self.y - h < BOTTOM:
                self.new_page()
                header()
            y = self.y
            if i % 2:
                c.rect(MARGIN, y - h, width, h, ROW_ALT)
            x = MARGIN
            for (hd, w, a), cell in zip(cols, row):
                if not isinstance(cell, dict):
                    cell = {"text": cell}
                st = cell.get("status")
                if FILL.get(st):
                    c.rect(x + 0.5, y - h + 0.5, w - 1, h - 1, FILL[st])
                color = cell.get("color") or INK.get(st, TEXT)
                bold = cell.get("bold", False)
                txt = fit(cell.get("text", ""), body_size, bold, w - 7)
                ty = y - (11.0 if has_sub else (h / 2 + body_size / 2 - 1.5))
                if a == "right":
                    c.text(x + w - 4, ty, txt, body_size, bold, color, "right")
                elif a == "center":
                    c.text(x + w / 2, ty, txt, body_size, bold, color, "center")
                else:
                    c.text(x + 4, ty, txt, body_size, bold, color)
                if cell.get("sub"):
                    sub = fit(cell["sub"], 6.8, False, w - 7)
                    sx = {"right": x + w - 4, "center": x + w / 2}.get(a, x + 4)
                    c.text(sx, ty - 9, sub, 6.8, False, MUTED, a if a in ("right", "center") else "left")
                x += w
            c.line(MARGIN, y - h, MARGIN + width, y - h, GRID, 0.5)
            if i in separators:
                c.line(MARGIN, y, MARGIN + width, y, NAVY, 1.4)
            self.y = y - h
        self.y -= 6

    def legend(self, items, size=7.3):
        """items: [(status, text)] + text final"""
        self.need(12)
        x = MARGIN
        y = self.y - size
        for st, txt in items:
            if st:
                self.c.rect(x, y - 1, 8, 8, FILL[st])
                x += 11
            self.c.text(x, y, txt, size, False, MUTED)
            x += text_width(txt, size) + 10
        self.y -= 11

    def box(self, title, lines, color=RED):
        """Requadre destacat (títol en franja de color + línies)."""
        size = 9
        body = []
        for ln in lines:
            body += wrap(u"• " + ln, size, False, CONTENT_W - 20)
        h = 22 + 12 * len(body) + 6
        self.need(h + 6)
        y = self.y
        c = self.c
        c.rect(MARGIN, y - 20, CONTENT_W, 20, color)
        c.text(MARGIN + 8, y - 14, title, 9, True, WHITE)
        c.rect(MARGIN, y - h, CONTENT_W, h - 20, (0.988, 0.957, 0.953) if color == RED else (0.95, 0.96, 0.98))
        c.line(MARGIN, y - h, PAGE_W - MARGIN, y - h, color, 0.8)
        ty = y - 34
        for ln in body:
            c.text(MARGIN + 10, ty, ln, size, False, TEXT)
            ty -= 12
        self.y = y - h - 10

    def bars(self, title, labels, values, unit, target=None, target_label="", invert=False, height=120.0,
             width=None, x0=None, colors=None):
        """Gràfic de barres simple (valors negatius com LUFS es dibuixen cap avall des de 0)."""
        c = self.c
        width = width or CONTENT_W / 2 - 10
        x0 = MARGIN if x0 is None else x0
        top = self.y
        c.text(x0 + width / 2, top - 9, title, 8.5, True, NAVY, "center")
        y_top = top - 18
        y_bot = top - height
        vals = list(values) + ([target] if target is not None else [])
        vmin = min(0.0, min(vals))
        vmax = max(0.0, max(vals))
        rng = (vmax - vmin) or 1.0
        lower = vmin - 0.08 * rng if vmin < 0 else 0.0
        upper = vmax + 0.12 * rng if vmax > 0 else 0.0
        to_y = lambda v: y_bot + (v - lower) / (upper - lower) * (y_top - y_bot)  # noqa: E731
        c.line(x0 + 26, to_y(0), x0 + width, to_y(0), MUTED, 0.6)
        n = len(values)
        slot = (width - 30) / max(1, n)
        for i, (lab, v) in enumerate(zip(labels, values)):
            bx = x0 + 30 + i * slot + slot * 0.2
            bw = slot * 0.6
            y0, y1 = sorted((to_y(0), to_y(v)))
            c.rect(bx, y0, bw, max(0.5, y1 - y0), (colors[i] if colors else NAVY))
            txt = (u"%.1f" % v).replace(".", ",")
            if v >= 0:
                c.text(bx + bw / 2, y1 + 3, txt, 7.5, True, TEXT, "center")
            else:
                c.text(bx + bw / 2, y1 - 11, txt, 7.5, True, WHITE, "center")
            c.text(bx + bw / 2, y_bot - 10, fit(lab, 7.5, False, slot), 7.5, False, TEXT, "center")
        if target is not None:
            ty = to_y(target)
            c.line(x0 + 26, ty, x0 + width, ty, RED, 0.8)
            c.text(x0 + 28, ty + 2.5, target_label, 6.5, False, RED)
        c.text(x0 + 2, (y_top + y_bot) / 2, unit, 7, False, MUTED)
        return top - height - 16
