"""Khmer-safe text rendering via pango-view (HarfBuzz shaping), cached as PNG -> cairo surfaces."""
import hashlib
import os
import shutil
import subprocess

import cairocffi as cairo

KHMER_FONT = os.environ.get("KH2D_KHMER_FONT", "Khmer Sangam MN")
LATIN_FONT = os.environ.get("KH2D_LATIN_FONT", "Helvetica Neue")
PANGO_VIEW = shutil.which("pango-view") or "/opt/homebrew/bin/pango-view"

_CACHE = {}


def has_khmer(s):
    return any(0x1780 <= ord(ch) <= 0x17FF or 0x19E0 <= ord(ch) <= 0x19FF for ch in s or "")


def render(text, size_px, cache_dir, color="#ffffff", bold=True, width_px=None, align="center", font=None):
    """Return a cairo ImageSurface with the text (transparent background)."""
    if not text:
        return None
    font = font or (KHMER_FONT if has_khmer(text) else LATIN_FONT)
    desc = "%s %s %dpx" % (font, "Bold" if bold else "", int(size_px))
    key = hashlib.sha1(("|".join([text, desc, color, str(width_px), align])).encode("utf-8")).hexdigest()[:20]
    if key in _CACHE:
        return _CACHE[key]
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, key + ".png")
    if not os.path.exists(path):
        cmd = [PANGO_VIEW, "--no-display", "--pixels", "--font=" + desc, "--background=transparent",
               "--foreground=" + color, "--margin=6", "--align=" + align, "--hinting=none", "-o", path]
        if width_px:
            cmd += ["--width=%d" % int(width_px), "--wrap=word-char"]
        cmd += ["--text", text]
        subprocess.run(cmd, check=True, capture_output=True)
    surf = cairo.ImageSurface.create_from_png(path)
    _CACHE[key] = surf
    return surf


def wrap_khmer(text, max_chars=46):
    """Split long Khmer text into <=2 lines at spaces/punctuation (Khmer has no word spaces)."""
    if len(text) <= max_chars:
        return [text]
    cands = [i for i, ch in enumerate(text) if ch in " ​។៕!?,"]
    if not cands:
        mid = len(text) // 2
        # never split inside a cluster: move to the next base consonant
        while mid < len(text) and not (0x1780 <= ord(text[mid]) <= 0x17B3):
            mid += 1
        return [text[:mid], text[mid:]]
    best = min(cands, key=lambda i: abs(i - len(text) / 2))
    a, b = text[:best + 1].strip(), text[best + 1:].strip()
    return [x for x in (a, b) if x]


def draw_outlined(ctx, surf, x, y, outline=4, shadow=True, alpha=1.0):
    """Draw a white text surface with a dark outline + soft shadow at top-left (x, y)."""
    if surf is None:
        return
    ctx.save()
    if shadow:
        ctx.set_source_rgba(0, 0, 0, 0.35 * alpha)
        ctx.mask_surface(surf, x + 3, y + 4)
    ctx.set_source_rgba(0.05, 0.04, 0.04, 0.95 * alpha)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-0.7, -0.7), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7)):
        ctx.mask_surface(surf, x + dx * outline, y + dy * outline)
    if alpha >= 1.0:
        ctx.set_source_surface(surf, x, y)
        ctx.paint()
    else:
        ctx.set_source_surface(surf, x, y)
        ctx.paint_with_alpha(alpha)
    ctx.restore()
