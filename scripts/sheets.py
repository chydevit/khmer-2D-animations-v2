"""Character sheets: turnaround (5 views), expression sheet, pose sheet, thumbnail, cast lineup."""
import math
import os

import cairocffi as cairo

import rig
from drawutil import src

VIEWS = [("Front", 0), ("3/4 front", 40), ("Side", 90), ("3/4 back", 140), ("Back", 180)]
SHEET_EXPR = ["neutral", "happy", "sad", "angry", "afraid", "surprised", "laughing", "crying",
              "thinking", "worried"]
SHEET_POSES = [("Standing", dict(pose="stand")), ("Walking", dict(pose="stand", legs="walk", phase=0.9)),
               ("Running", dict(pose="stand", legs="run", phase=1.1)), ("Sitting", dict(pose="sit_hands", legs="sit")),
               ("Pointing", dict(pose="point")), ("Talking", dict(pose="talk", talk=1.0, viseme="A", mouth_open=0.8)),
               ("Bowing / sampeah", dict(pose="bow")), ("Carrying", dict(pose="carry", carry="box")),
               ("Working", dict(pose="work", t=0.2)), ("Fighting", dict(pose="fight", t=0.3, expr="determined"))]


def _label(ctx, text, x, y, size=26, color=(0.15, 0.15, 0.15), center=True):
    ctx.select_font_face("Helvetica", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(size)
    src(ctx, color)
    ext = ctx.text_extents(text)
    ctx.move_to(x - (ext[2] / 2 if center else 0), y)
    ctx.show_text(text)


def _canvas(w, h):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surf)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    return surf, ctx


def _base_state(ch, **kw):
    st = dict(theta=30, pose=ch.get("default_pose", "stand"), expr=ch.get("default_expression", "neutral"), t=0.0)
    if st["expr"] not in rig.EXPRESSIONS:
        st["expr"] = "neutral"
    st.update(kw)
    return st


def turnaround(ch, path):
    W, H = 2200, 900
    surf, ctx = _canvas(W, H)
    _label(ctx, "%s  (%s) — turnaround" % (ch.get("name", ch["character_id"]), ch["character_id"]), 40, 60, 36,
           center=False)
    for i, (name, th) in enumerate(VIEWS):
        x = 240 + i * 430
        rig.draw_character(ctx, ch, _base_state(ch, theta=th, pose="stand", expr="neutral"), x, 790, 1.2)
        _label(ctx, name, x, 860)
    surf.write_to_png(path)


def expressions(ch, path):
    cols, rows = 5, 2
    W, H = 2000, 1000
    surf, ctx = _canvas(W, H)
    _label(ctx, "%s — expressions" % ch.get("name", ch["character_id"]), 40, 56, 34, center=False)
    for i, ex in enumerate(SHEET_EXPR):
        cx = 200 + (i % cols) * 400
        cy = 90 + (i // cols) * 450
        # head + shoulders crop: draw big and clip
        ctx.save()
        ctx.rectangle(cx - 190, cy, 380, 400)
        ctx.clip()
        pose = {"thinking": "think", "crying": "cry", "laughing": "laugh", "afraid": "afraid",
                "angry": "angry"}.get(ex, "stand")
        sc = 1.25 * 80.0 / rig.BUILDS[rig.merge_rig(ch.get("rig"))["build"]]["R"]
        _, hy, _ = rig.head_center(ch, 0, 0, sc)
        rig.draw_character(ctx, ch, _base_state(ch, theta=25, pose=pose, expr=ex, t=0.4), cx, cy + 190 - hy, sc)
        ctx.restore()
        _label(ctx, ex.capitalize(), cx, cy + 430)
    surf.write_to_png(path)


def poses(ch, path):
    cols = 5
    W, H = 2200, 1300
    surf, ctx = _canvas(W, H)
    _label(ctx, "%s — pose references" % ch.get("name", ch["character_id"]), 40, 56, 34, center=False)
    for i, (name, kw) in enumerate(SHEET_POSES):
        cx = 230 + (i % cols) * 430
        by = 600 + (i // cols) * 620
        st = _base_state(ch, theta=45, expr=kw.get("expr", "neutral"))
        st.update(kw)
        if "t" not in kw:
            st["t"] = 0.0
        rig.draw_character(ctx, ch, st, cx, by, 1.1)
        _label(ctx, name, cx, by + 50)
    surf.write_to_png(path)


def thumbnail(ch, path, size=512):
    surf, ctx = _canvas(size, size)
    h = rig.character_height(ch)
    sc = size * 0.86 / h
    rig.draw_character(ctx, ch, _base_state(ch, theta=30), size / 2, size * 0.95, sc)
    surf.write_to_png(path)


def lineup(chars, path, per_row=6):
    n = len(chars)
    rows = math.ceil(n / per_row)
    W, H = 260 * per_row + 80, 560 * rows + 40
    surf, ctx = _canvas(W, H)
    for i, ch in enumerate(chars):
        x = 170 + (i % per_row) * 260
        y = 500 + (i // per_row) * 560
        rig.draw_character(ctx, ch, _base_state(ch, theta=32), x, y, 0.95)
        _label(ctx, ch.get("name", ch["character_id"]), x, y + 40, 22)
    surf.write_to_png(path)


def build_all(chars, outdir):
    paths = []
    for sub in ("sheets", "expressions", "poses", "thumbnails"):
        os.makedirs(os.path.join(outdir, sub), exist_ok=True)
    for ch in chars:
        cid = ch["character_id"]
        p = [os.path.join(outdir, "sheets", cid + "_turnaround.png"),
             os.path.join(outdir, "expressions", cid + "_expressions.png"),
             os.path.join(outdir, "poses", cid + "_poses.png"),
             os.path.join(outdir, "thumbnails", cid + ".png")]
        turnaround(ch, p[0])
        expressions(ch, p[1])
        poses(ch, p[2])
        thumbnail(ch, p[3])
        paths += p
    lp = os.path.join(outdir, "sheets", "_cast_lineup.png")
    lineup(chars, lp)
    paths.append(lp)
    return paths


if __name__ == "__main__":
    import json
    import sys
    data = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    lineup(data["characters"], os.path.join(out, "lineup.png"))
    if len(sys.argv) > 3:
        ch = [c for c in data["characters"] if c["character_id"] == sys.argv[3]][0]
        turnaround(ch, os.path.join(out, "turn.png"))
        expressions(ch, os.path.join(out, "expr.png"))
        poses(ch, os.path.join(out, "poses.png"))
