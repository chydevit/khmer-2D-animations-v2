"""Layered Cambodian environments in the same flat 2D cartoon style.

World space: 1920x1080 stage, drawn from x=-520 to 2440 so the camera can pan and zoom.
Layers (parallax factor): SKY 0.05, BG 0.25, MG 0.6, GROUND 1.0 (characters stand here), FG 1.3.
Characters stand on y in [780, 1010]; horizon is around y=600-660.
Each environment: ENV[name] = dict(horizon, layers={SKY: fn, BG: fn, MG: fn, GROUND: fn, FG: fn}).
fn(ctx, t, tod) draws in world coordinates. Drawing is deterministic (seeded) so it never flickers.
"""
import math

import cairocffi as cairo

from drawutil import (OUTLINE, blob, check_pattern, circle, curve, ellipse, ellipse_path, fill_stroke,
                      flower, hexc, lin_grad, line, mix, poly, rad_grad, rng, rrect, shade, src,
                      stripe_pattern)

X0, X1 = -520, 2440
LAYERS = ["SKY", "BG", "MG", "GROUND", "FG"]
PARALLAX = {"SKY": 0.05, "BG": 0.25, "MG": 0.6, "GROUND": 1.0, "FG": 1.3}
BOL = 3.0  # background outline width (thinner than characters so they pop)

TOD = {
    "morning": dict(sky=("#8fd0f2", "#ffe9c2"), sun=(0.25, 0.30, "#fff2b0"), tint=None),
    "day": dict(sky=("#5fbcef", "#d6f0fb"), sun=(0.78, 0.16, "#fff7d1"), tint=None),
    "evening": dict(sky=("#5d4c9c", "#f6a35f"), sun=(0.70, 0.52, "#ffcf7a"), tint=((1.0, 0.82, 0.66), 1.0)),
    "night": dict(sky=("#0c1736", "#2b4677"), sun=None, tint=((0.50, 0.58, 0.86), 1.0)),
    "interior": dict(sky=("#e9cfa2", "#e9cfa2"), sun=None, tint=None),
}


# --------------------------------------------------------------------------- props

def sky(ctx, t, tod, horizon=640, clouds=True):
    p = TOD.get(tod, TOD["day"])
    ctx.new_path()
    ctx.rectangle(X0, -200, X1 - X0, horizon + 400)
    ctx.set_source(lin_grad(0, -100, 0, horizon + 40, [(0, p["sky"][0]), (1, p["sky"][1])]))
    ctx.fill()
    if tod == "night":
        r = rng(99)
        for _ in range(140):
            x, y = r.uniform(X0, X1), r.uniform(-150, horizon - 120)
            tw = 0.5 + 0.5 * math.sin(t * r.uniform(1, 3) + r.uniform(0, 6))
            circle(ctx, x, y, r.uniform(1.0, 2.4), (1, 1, 0.9 * tw + 0.1), 0)
        circle(ctx, 1500, 150, 52, "#fdf6d8", 0)
        circle(ctx, 1522, 138, 46, p["sky"][0], 0)
    if p.get("sun"):
        sx, sy, sc = p["sun"]
        x, y = X0 + (X1 - X0) * sx, horizon * sy
        ctx.new_path()
        ctx.arc(x, y, 220, 0, 2 * math.pi)
        ctx.set_source(rad_grad(x, y, 40, 220, [(0, hexc(sc) + (0.55,)), (1, hexc(sc) + (0.0,))]))
        ctx.fill()
        circle(ctx, x, y, 58, sc, 0)
    if clouds and tod != "night":
        r = rng(7)
        for i in range(7):
            cx = (r.uniform(X0, X1) + t * r.uniform(4, 10)) % (X1 - X0) + X0
            cy = r.uniform(60, horizon * 0.55)
            cloud(ctx, cx, cy, r.uniform(0.6, 1.25), tod)


def cloud(ctx, x, y, s, tod="day"):
    col = "#ffffff" if tod != "evening" else "#ffd9c0"
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(s, s)
    ctx.new_path()
    for cx, cy, r in ((0, 0, 46), (52, -18, 58), (110, 0, 44), (60, 16, 48), (-36, 14, 32), (146, 16, 30)):
        ctx.new_sub_path()
        ctx.arc(cx, cy, r, 0, 2 * math.pi)
    src(ctx, col, 0.92)
    ctx.fill()
    ctx.restore()


def hills(ctx, base, color, amp, seed, step=160, top=None):
    r = rng(seed)
    pts = []
    x = X0 - 100
    while x <= X1 + 200:
        pts.append((x, base - amp * (0.4 + 0.6 * r.random())))
        x += step * r.uniform(0.7, 1.3)
    ctx.new_path()
    ctx.move_to(X0 - 200, 1300)
    ctx.line_to(*pts[0])
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        mx = (a[0] + b[0]) / 2
        ctx.curve_to(mx, a[1], mx, b[1], b[0], b[1])
    ctx.line_to(X1 + 300, 1300)
    ctx.close_path()
    src(ctx, color)
    ctx.fill()


def mountains(ctx, base, color, seed, h=260):
    r = rng(seed)
    x = X0 - 200
    while x < X1 + 200:
        w = r.uniform(260, 520)
        hh = h * r.uniform(0.55, 1.0)
        pts = [(x, base), (x + w * 0.45, base - hh), (x + w * 0.55, base - hh * 0.96), (x + w, base)]
        poly(ctx, pts, color, 0)
        poly(ctx, [(x + w * 0.45, base - hh), (x + w * 0.55, base - hh * 0.96), (x + w * 0.62, base - hh * 0.7),
                   (x + w * 0.38, base - hh * 0.72)], shade(color, 0.35), 0)
        x += w * r.uniform(0.55, 0.85)


def sugar_palm(ctx, x, y, h, t=0.0, col="#3f8f3a", ol=BOL):
    """Cambodia's iconic tnaot (sugar palm): tall straight trunk, round spiky crown."""
    sway = math.sin(t * 0.9 + x * 0.01) * h * 0.012
    top = (x + sway, y - h)
    line(ctx, [(x - 1, y), top], h * 0.05 + 2 * ol, OUTLINE)
    line(ctx, [(x, y), top], h * 0.05, "#7d5a3a")
    for k in range(4):
        yy = y - h * (0.2 + k * 0.18)
        line(ctx, [(x - h * 0.02, yy), (x + h * 0.02, yy - 3)], 1.5, "#5c3f26")
    R = h * 0.2
    for k in range(17):
        a = -math.pi + k * math.pi / 16 + math.sin(t + k) * 0.02
        a = a - 0.15 if k < 8 else a + 0.15
        ex, ey = top[0] + math.cos(a) * R * 1.05, top[1] + math.sin(a) * R * 0.95 + R * 0.1
        poly(ctx, [(top[0] - 4, top[1]), (ex, ey), (top[0] + 4, top[1] + 4)], shade(col, -0.08 * (k % 3)), ol * 0.6)
    for k in range(9):
        a = -math.pi + k * math.pi / 8
        ex, ey = top[0] + math.cos(a) * R * 0.8, top[1] - abs(math.sin(a)) * R * 0.75
        poly(ctx, [(top[0] - 5, top[1] + 2), (ex, ey), (top[0] + 5, top[1] + 2)], shade(col, 0.12), ol * 0.6)
    circle(ctx, top[0], top[1] + 6, h * 0.035, "#4a3020", ol * 0.6)


def coconut(ctx, x, y, h, t=0.0, lean=0.12):
    tx, ty = x + h * lean, y - h
    curve(ctx, (x, y), (x + h * lean * 0.2, y - h * 0.6), (tx, ty), h * 0.05 + 6, OUTLINE)
    curve(ctx, (x, y), (x + h * lean * 0.2, y - h * 0.6), (tx, ty), h * 0.05, "#8a6a45")
    for k in range(7):
        a = -math.pi * 0.95 + k * math.pi * 0.95 / 6 + math.sin(t * 1.1 + k) * 0.04
        L = h * 0.42
        ex, ey = tx + math.cos(a) * L, ty + math.sin(a) * L * 0.5 + L * 0.25
        mx, my = tx + math.cos(a) * L * 0.5, ty + math.sin(a) * L * 0.5 - L * 0.1
        ctx.new_path()
        ctx.move_to(tx, ty)
        ctx.curve_to(mx, my - 14, mx, my - 14, ex, ey)
        ctx.curve_to(mx, my + 10, mx, my + 10, tx, ty + 6)
        fill_stroke(ctx, "#3d9a40" if k % 2 else "#2f8a38", BOL * 0.7)
    for k in range(3):
        circle(ctx, tx - 10 + k * 10, ty + 8, 9, "#6d5a2a", 1.5)


def tree(ctx, x, y, s, col="#4fa83d", trunk="#7a5235", seed=0, ol=BOL):
    r = rng(seed + int(x))
    line(ctx, [(x, y), (x, y - 120 * s)], 26 * s + 2 * ol, OUTLINE)
    line(ctx, [(x, y), (x, y - 120 * s)], 26 * s, trunk)
    ctx.new_path()
    blobs = [(0, -190, 90), (-70, -150, 70), (70, -150, 72), (-40, -235, 64), (45, -230, 66), (0, -120, 60)]
    for bx, by, br in blobs:
        ctx.new_sub_path()
        ctx.arc(x + bx * s, y + by * s, br * s * r.uniform(0.92, 1.08), 0, 2 * math.pi)
    src(ctx, OUTLINE)
    ctx.set_line_width(ol * 2)
    ctx.stroke_preserve()
    src(ctx, col)
    ctx.fill()
    for bx, by, br in blobs[:3]:
        ellipse(ctx, x + (bx - br * 0.25) * s, y + (by - br * 0.3) * s, br * 0.45 * s, br * 0.3 * s,
                shade(col, 0.18), 0)


def frangipani(ctx, x, y, s, t=0.0):
    tree(ctx, x, y, s, "#5aa548", "#8a6a4f", seed=3)
    r = rng(int(x) + 5)
    for _ in range(14):
        flower(ctx, x + r.uniform(-90, 90) * s, y - r.uniform(130, 260) * s, 9 * s, "#ffffff", "#f7d23e", 1.0)


def bush(ctx, x, y, s, col="#3f9a3a"):
    ctx.new_path()
    for bx, by, br in ((0, -30, 36), (-34, -18, 26), (34, -18, 28), (0, -10, 30)):
        ctx.new_sub_path()
        ctx.arc(x + bx * s, y + by * s, br * s, 0, 2 * math.pi)
    src(ctx, OUTLINE)
    ctx.set_line_width(BOL * 2)
    ctx.stroke_preserve()
    src(ctx, col)
    ctx.fill()


def banana(ctx, x, y, s, t=0.0):
    line(ctx, [(x, y), (x, y - 120 * s)], 20 * s + 6, OUTLINE)
    line(ctx, [(x, y), (x, y - 120 * s)], 20 * s, "#7fae4a")
    for k, a in enumerate((-2.6, -2.0, -1.3, -0.6, -0.1)):
        a += math.sin(t * 1.3 + k) * 0.04
        L = 130 * s
        ex, ey = x + math.cos(a) * L, y - 120 * s + math.sin(a) * L
        ctx.new_path()
        ctx.move_to(x, y - 120 * s)
        mx, my = (x + ex) / 2, (y - 120 * s + ey) / 2
        ctx.curve_to(mx - 20 * s, my - 26 * s, mx - 20 * s, my - 26 * s, ex, ey)
        ctx.curve_to(mx + 14 * s, my + 18 * s, mx + 14 * s, my + 18 * s, x, y - 112 * s)
        fill_stroke(ctx, "#5fae3f" if k % 2 else "#4c9a35", BOL * 0.8)


def grass_tufts(ctx, y0, y1, n, seed, col="#3c8f35"):
    r = rng(seed)
    for _ in range(n):
        x, y = r.uniform(X0, X1), r.uniform(y0, y1)
        s = 0.6 + (y - y0) / max(1, y1 - y0) * 0.8
        for k in range(-2, 3):
            line(ctx, [(x + k * 4 * s, y), (x + k * 7 * s, y - 16 * s - abs(k) * -3)], 2.4 * s, col)


def stilt_house(ctx, x, y, s=1.0, wall="#a8693a", roof="#b5452f"):
    """Traditional Khmer wooden house on stilts with a steep gabled roof and ladder."""
    W, H = 420 * s, 170 * s
    fy = y - 150 * s  # floor level
    for k in range(5):
        px = x - W / 2 + 20 * s + k * (W - 40 * s) / 4
        rrect(ctx, px - 9 * s, fy, 18 * s, 150 * s, 3, "#6d4527", BOL)
    rrect(ctx, x - W / 2 - 10 * s, fy - 12 * s, W + 20 * s, 18 * s, 3, "#7a4c2a", BOL)
    rrect(ctx, x - W / 2, fy - H, W, H, 4, wall, BOL)
    for k in range(1, 12):
        line(ctx, [(x - W / 2 + k * W / 12, fy - H + 4), (x - W / 2 + k * W / 12, fy - 4)], 1.6, shade(wall, -0.25))
    # windows (open shutters)
    for wx in (x - W * 0.3, x + W * 0.05):
        rrect(ctx, wx, fy - H * 0.72, 62 * s, 64 * s, 3, "#3a2416", BOL)
        rrect(ctx, wx - 26 * s, fy - H * 0.72, 24 * s, 64 * s, 2, shade(wall, 0.12), BOL * 0.8)
    # door
    rrect(ctx, x + W * 0.3, fy - H * 0.85, 64 * s, H * 0.85, 3, "#5a3420", BOL)
    # roof
    rh = 190 * s
    poly(ctx, [(x - W / 2 - 50 * s, fy - H + 6), (x - W * 0.18, fy - H - rh), (x + W * 0.18, fy - H - rh),
               (x + W / 2 + 50 * s, fy - H + 6)], roof, BOL)
    for k in range(1, 7):
        yy = fy - H - rh * k / 7
        xx = (W / 2 + 50 * s) - (W / 2 + 50 * s - W * 0.18) * k / 7
        line(ctx, [(x - xx, yy), (x + xx, yy)], 1.4, shade(roof, -0.25))
    poly(ctx, [(x - W * 0.18, fy - H - rh), (x - W * 0.18 - 14 * s, fy - H - rh - 26 * s),
               (x - W * 0.18 + 10 * s, fy - H - rh)], roof, BOL * 0.8)
    poly(ctx, [(x + W * 0.18, fy - H - rh), (x + W * 0.18 + 14 * s, fy - H - rh - 26 * s),
               (x + W * 0.18 - 10 * s, fy - H - rh)], roof, BOL * 0.8)
    # ladder
    lx = x + W * 0.36
    line(ctx, [(lx - 10 * s, fy), (lx - 40 * s, y)], 7 * s, "#6d4527")
    line(ctx, [(lx + 40 * s, fy), (lx + 10 * s, y)], 7 * s, "#6d4527")
    for k in range(1, 6):
        yy = fy + (y - fy) * k / 6
        line(ctx, [(lx - 10 * s - 30 * s * k / 6, yy), (lx + 40 * s - 30 * s * k / 6, yy)], 5 * s, "#6d4527")
    # water jar and hay under the house
    blob(ctx, [(x - W * 0.42, y - 2), (x - W * 0.42 + 56 * s, y - 2), (x - W * 0.42 + 64 * s, y - 48 * s),
               (x - W * 0.42 + 28 * s, y - 70 * s), (x - W * 0.42 - 8 * s, y - 48 * s)], "#8b4a2c", BOL)


def pagoda(ctx, x, y, s=1.0, t=0.0):
    """Khmer Buddhist vihara: white base, stacked red-orange roofs with gold naga finials."""
    W = 560 * s
    rrect(ctx, x - W / 2 - 40 * s, y - 40 * s, W + 80 * s, 40 * s, 4, "#e8e0d0", BOL)
    for k in range(3):
        rrect(ctx, x - 70 * s + k * 10 * s, y - 40 * s + k * 13 * s, 140 * s - k * 20 * s, 13 * s, 2, "#d5cbb7", 1.5)
    rrect(ctx, x - W / 2, y - 220 * s, W, 182 * s, 4, "#f6f1e6", BOL)
    for k in range(6):
        px = x - W / 2 + 30 * s + k * (W - 60 * s) / 5
        rrect(ctx, px - 11 * s, y - 218 * s, 22 * s, 178 * s, 3, "#efe4cc", BOL * 0.8)
    rrect(ctx, x - 44 * s, y - 170 * s, 88 * s, 130 * s, 6, "#b02a2a", BOL)
    line(ctx, [(x, y - 168 * s), (x, y - 42 * s)], 2, "#e7b33a")
    # stacked roofs
    for k, (w, h, yy) in enumerate(((W * 0.62, 120 * s, y - 220 * s), (W * 0.46, 105 * s, y - 300 * s),
                                    (W * 0.30, 90 * s, y - 370 * s))):
        col = "#d9532a" if k % 2 == 0 else "#2f6d4a"
        poly(ctx, [(x - w - 30 * s, yy + 8 * s), (x - w * 0.25, yy - h), (x + w * 0.25, yy - h),
                   (x + w + 30 * s, yy + 8 * s)], col, BOL)
        line(ctx, [(x - w - 30 * s, yy + 8 * s), (x - w * 0.25, yy - h)], 5 * s, "#e9b53b")
        line(ctx, [(x + w + 30 * s, yy + 8 * s), (x + w * 0.25, yy - h)], 5 * s, "#e9b53b")
        for sd in (-1, 1):  # chovea / naga tips
            ex = x + sd * (w + 30 * s)
            curve(ctx, (ex, yy + 8 * s), (ex + sd * 30 * s, yy + 4 * s), (ex + sd * 34 * s, yy - 30 * s), 6 * s, "#e9b53b")
        rrect(ctx, x - w * 0.6, yy - 8 * s, w * 1.2, 16 * s, 3, "#e9b53b", BOL * 0.8)
    # spire
    sy0 = y - 460 * s
    poly(ctx, [(x - 16 * s, sy0 + 10 * s), (x, sy0 - 120 * s), (x + 16 * s, sy0 + 10 * s)], "#e9b53b", BOL)
    for k in range(4):
        ellipse(ctx, x, sy0 - k * 26 * s, (14 - k * 3) * s, 5 * s, "#d39b25", 1.2)


def stupa(ctx, x, y, s=1.0):
    rrect(ctx, x - 70 * s, y - 50 * s, 140 * s, 50 * s, 3, "#ece4d4", BOL)
    rrect(ctx, x - 50 * s, y - 100 * s, 100 * s, 50 * s, 3, "#f4eee2", BOL)
    blob(ctx, [(x - 46 * s, y - 100 * s), (x - 30 * s, y - 160 * s), (x, y - 180 * s), (x + 30 * s, y - 160 * s),
               (x + 46 * s, y - 100 * s)], "#f6f1e6", BOL)
    poly(ctx, [(x - 10 * s, y - 175 * s), (x, y - 270 * s), (x + 10 * s, y - 175 * s)], "#e9b53b", BOL)


def angkor(ctx, x, y, s=1.0, col="#8d8a7a"):
    """Angkor-style temple silhouette: five lotus-bud towers on a terrace."""
    rrect(ctx, x - 520 * s, y - 70 * s, 1040 * s, 70 * s, 2, shade(col, -0.1), BOL)
    rrect(ctx, x - 420 * s, y - 140 * s, 840 * s, 72 * s, 2, col, BOL)
    for k in range(-8, 9):
        line(ctx, [(x + k * 48 * s, y - 136 * s), (x + k * 48 * s, y - 72 * s)], 1.6, shade(col, -0.3))
    for tx, th, tw in ((-300, 240, 60), (300, 240, 60), (-160, 300, 74), (160, 300, 74), (0, 400, 92)):
        cx = x + tx * s
        base = y - 140 * s
        h, w = th * s, tw * s
        ctx.new_path()
        ctx.move_to(cx - w, base)
        ctx.curve_to(cx - w * 1.1, base - h * 0.55, cx - w * 0.4, base - h * 0.9, cx, base - h)
        ctx.curve_to(cx + w * 0.4, base - h * 0.9, cx + w * 1.1, base - h * 0.55, cx + w, base)
        ctx.close_path()
        fill_stroke(ctx, shade(col, 0.06), BOL)
        for k in range(1, 6):
            yy = base - h * k / 6.5
            ww = w * (1 - (k / 6.5) ** 2) * 0.98
            line(ctx, [(cx - ww, yy), (cx + ww, yy)], 1.6, shade(col, -0.3))


def market_stall(ctx, x, y, s, awn="#d8333a", seed=0):
    r = rng(seed)
    W = 260 * s
    for px in (x - W / 2 + 8 * s, x + W / 2 - 8 * s):
        line(ctx, [(px, y), (px, y - 210 * s)], 9 * s, "#6d4527")
    rrect(ctx, x - W / 2, y - 90 * s, W, 26 * s, 3, "#9a6a3e", BOL)
    rrect(ctx, x - W / 2 + 8 * s, y - 64 * s, W - 16 * s, 64 * s, 2, "#7a5232", BOL)
    # produce
    cols = ["#f2a531", "#e4542e", "#7cc04a", "#f6d23a", "#8f4fb0"]
    for k in range(4):
        bx = x - W / 2 + 40 * s + k * 60 * s
        ellipse(ctx, bx, y - 96 * s, 26 * s, 9 * s, "#b5853f", 2)
        c = cols[r.randrange(len(cols))]
        for j in range(4):
            circle(ctx, bx - 14 * s + j * 9 * s, y - 104 * s - (j % 2) * 6 * s, 8 * s, c, 1.6)
    pat = stripe_pattern(awn, "#fff6e6", 18 * s, vertical=True)
    poly(ctx, [(x - W / 2 - 24 * s, y - 196 * s), (x + W / 2 + 24 * s, y - 196 * s), (x + W / 2 + 34 * s, y - 150 * s),
               (x - W / 2 - 34 * s, y - 150 * s)], pat, BOL)
    for k in range(9):
        cx = x - W / 2 - 34 * s + k * (W + 68 * s) / 8
        ellipse(ctx, cx, y - 150 * s, (W + 68 * s) / 16, 10 * s, awn if k % 2 else "#fff6e6", 1.6)


def water(ctx, y0, y1, t, col="#4aa3d8", tod="day"):
    if tod == "night":
        col = "#24406e"
    elif tod == "evening":
        col = "#c98a7a"
    ctx.new_path()
    ctx.rectangle(X0, y0, X1 - X0, y1 - y0)
    ctx.set_source(lin_grad(0, y0, 0, y1, [(0, shade(col, 0.25)), (1, shade(col, -0.1))]))
    ctx.fill()
    r = rng(11)
    for _ in range(70):
        x = r.uniform(X0, X1)
        y = r.uniform(y0 + 8, y1 - 4)
        w = r.uniform(20, 70) * (0.5 + (y - y0) / max(1, y1 - y0))
        dx = math.sin(t * 1.3 + x * 0.03) * 10
        line(ctx, [(x + dx, y), (x + dx + w, y)], 2.4, "#ffffff", 0.45)


def boat(ctx, x, y, s, t=0.0):
    bob = math.sin(t * 1.6 + x) * 3
    y += bob
    ctx.new_path()
    ctx.move_to(x - 160 * s, y - 34 * s)
    ctx.curve_to(x - 90 * s, y + 10 * s, x + 90 * s, y + 10 * s, x + 170 * s, y - 40 * s)
    ctx.line_to(x + 140 * s, y - 20 * s)
    ctx.line_to(x - 130 * s, y - 18 * s)
    ctx.close_path()
    fill_stroke(ctx, "#7a4a2a", BOL)
    line(ctx, [(x - 120 * s, y - 16 * s), (x + 130 * s, y - 18 * s)], 3, "#a8703f")


def lotus(ctx, x, y, s, bloom=True):
    ellipse(ctx, x, y, 40 * s, 12 * s, "#4f9e46", BOL * 0.7)
    if bloom:
        for a in (-0.7, -0.35, 0, 0.35, 0.7):
            ctx.save()
            ctx.translate(x, y - 8 * s)
            ctx.rotate(a)
            blob(ctx, [(0, 0), (-9 * s, -16 * s), (0, -34 * s), (9 * s, -16 * s)], "#f48fb8", 1.6)
            ctx.restore()


def fence(ctx, y, x0, x1, s=1.0):
    k = x0
    line(ctx, [(x0, y - 50 * s), (x1, y - 50 * s)], 7 * s, "#8a5c36")
    line(ctx, [(x0, y - 24 * s), (x1, y - 24 * s)], 7 * s, "#8a5c36")
    while k < x1:
        rrect(ctx, k - 6 * s, y - 70 * s, 12 * s, 70 * s, 2, "#9b6a3e", BOL * 0.7)
        k += 70 * s


def haystack(ctx, x, y, s):
    blob(ctx, [(x - 70 * s, y), (x - 56 * s, y - 70 * s), (x, y - 110 * s), (x + 56 * s, y - 70 * s), (x + 70 * s, y)],
         "#e8c25a", BOL)
    for k in range(-3, 4):
        line(ctx, [(x + k * 14 * s, y - 6), (x + k * 9 * s, y - 80 * s + abs(k) * 8 * s)], 1.5, "#b88f2a")


def cow(ctx, x, y, s, t=0.0, col="#e9dcc8"):
    for dx in (-50, -30, 40, 58):
        line(ctx, [(x + dx * s, y - 50 * s), (x + dx * s, y)], 12 * s + 6, OUTLINE)
        line(ctx, [(x + dx * s, y - 50 * s), (x + dx * s, y)], 12 * s, col)
    rrect(ctx, x - 80 * s, y - 120 * s, 160 * s, 80 * s, 36 * s, col, BOL)
    nod = math.sin(t * 1.2) * 4 * s
    ellipse(ctx, x + 94 * s, y - 112 * s + nod, 34 * s, 28 * s, col, BOL)
    circle(ctx, x + 100 * s, y - 118 * s + nod, 4 * s, OUTLINE, 0)
    ellipse(ctx, x + 116 * s, y - 100 * s + nod, 14 * s, 11 * s, "#f0b6a8", 1.6)
    curve(ctx, (x + 80 * s, y - 136 * s + nod), (x + 70 * s, y - 158 * s), (x + 86 * s, y - 166 * s), 5 * s, "#d8c7a0")


def ground(ctx, horizon, c_far, c_near):
    ctx.new_path()
    ctx.rectangle(X0, horizon, X1 - X0, 1200 - horizon)
    ctx.set_source(lin_grad(0, horizon, 0, 1080, [(0, c_far), (1, c_near)]))
    ctx.fill()


def dirt_path(ctx, horizon, col="#d9b37a"):
    ctx.new_path()
    ctx.move_to(X0, 1000)
    ctx.curve_to(400, 900, 900, 820, 1500, 800)
    ctx.line_to(X1, 790)
    ctx.line_to(X1, 1020)
    ctx.curve_to(1500, 1010, 900, 1050, X0, 1120)
    ctx.close_path()
    src(ctx, col)
    ctx.fill()


def paddies(ctx, y0, y1, t, col="#7cc04a", mature=False):
    ctx.new_path()
    ctx.rectangle(X0, y0, X1 - X0, y1 - y0)
    src(ctx, col)
    ctx.fill()
    n = 9
    for k in range(n):
        yy = y0 + (y1 - y0) * ((k + 1) / n) ** 1.6
        line(ctx, [(X0, yy), (X1, yy)], 2 + k * 0.6, shade(col, -0.18))
    r = rng(5)
    for _ in range(320):
        x = r.uniform(X0, X1)
        f = r.random() ** 1.4
        y = y0 + (y1 - y0) * f
        h = 6 + 22 * f
        sway = math.sin(t * 1.5 + x * 0.02) * h * 0.18
        c = shade(col, -0.25) if not mature else "#d9b13a"
        line(ctx, [(x, y), (x + sway, y - h)], 1.2 + f * 1.8, c)


# --------------------------------------------------------------------------- environments

def _village(ctx, layer, t, tod):
    hz = 620
    if layer == "SKY":
        sky(ctx, t, tod, hz)
    elif layer == "BG":
        hills(ctx, hz + 10, "#8fbf8a", 70, 3)
        for k, x in enumerate(range(-500, 2500, 230)):
            sugar_palm(ctx, x + (k * 37) % 90, hz + 30, 230 + (k * 53) % 90, t, "#4f9a52", 2.2)
        hills(ctx, hz + 40, "#6fae5c", 30, 4)
    elif layer == "MG":
        stilt_house(ctx, 520, 760, 1.05)
        coconut(ctx, 1180, 760, 360, t)
        banana(ctx, 1380, 770, 1.1, t)
        haystack(ctx, 1620, 772, 1.0)
        tree(ctx, 1950, 770, 1.15, seed=2)
        tree(ctx, -120, 770, 1.0, seed=8)
    elif layer == "GROUND":
        ground(ctx, 700, "#93c26a", "#6fae4e")
        dirt_path(ctx, 700)
        grass_tufts(ctx, 760, 1070, 70, 21)
        r = rng(4)
        for _ in range(18):
            flower(ctx, r.uniform(X0, X1), r.uniform(1030, 1075), 7, ["#ffffff", "#f6d23a", "#f07fb6"][r.randrange(3)], "#f7d23e", 1.0)
    elif layer == "FG":
        bush(ctx, -60, 1110, 2.0, "#3a8a35")
        bush(ctx, 2000, 1110, 2.2, "#3a8a35")


def _rice_field(ctx, layer, t, tod, mature=False):
    hz = 560
    if layer == "SKY":
        sky(ctx, t, tod, hz)
    elif layer == "BG":
        mountains(ctx, hz + 20, "#9db7c9", 12, 200)
        hills(ctx, hz + 30, "#88b97a", 40, 13)
        for k, x in enumerate(range(-520, 2500, 150)):
            sugar_palm(ctx, x + (k * 41) % 70, hz + 46, 150 + (k * 29) % 70, t, "#4f9a52", 1.8)
    elif layer == "MG":
        paddies(ctx, hz + 40, 780, t, "#86c45a" if not mature else "#d6c055", mature)
        sugar_palm(ctx, 1500, 790, 420, t)
        sugar_palm(ctx, 1640, 800, 380, t)
    elif layer == "GROUND":
        ctx.new_path()
        ctx.rectangle(X0, 760, X1 - X0, 400)
        ctx.set_source(lin_grad(0, 760, 0, 1080, [(0, "#a7c96a"), (1, "#8ab452")]))
        ctx.fill()
        ctx.new_path()
        ctx.rectangle(X0, 850, X1 - X0, 120)
        src(ctx, "#c9a16a")
        ctx.fill()
        line(ctx, [(X0, 850), (X1, 850)], 3, "#a8814f")
        grass_tufts(ctx, 965, 1075, 40, 31, "#4c8f35")
    elif layer == "FG":
        r = rng(9)
        for _ in range(26):
            x = r.choice([r.uniform(X0, 120), r.uniform(1800, X1)])
            line(ctx, [(x, 1100), (x + math.sin(t + x) * 10, 960 + r.uniform(-20, 20))], 5, "#4f9a3a" if not mature else "#c9a43a")


def _farm(ctx, layer, t, tod):
    if layer == "MG":
        fence(ctx, 790, -500, 2440, 1.0)
        haystack(ctx, 300, 780, 1.2)
        cow(ctx, 1500, 790, 1.0, t)
        tree(ctx, 1950, 780, 1.2, seed=4)
        stilt_house(ctx, 820, 760, 0.75)
    elif layer == "GROUND":
        ground(ctx, 700, "#a5c76e", "#7db155")
        dirt_path(ctx, 700, "#d2ad74")
        grass_tufts(ctx, 800, 1070, 60, 41)
    else:
        _rice_field(ctx, layer, t, tod)


def _forest(ctx, layer, t, tod):
    hz = 640
    if layer == "SKY":
        sky(ctx, t, tod, hz, clouds=False)
        ctx.new_path()
        ctx.rectangle(X0, -200, X1 - X0, 1000)
        src(ctx, "#2f6b3a", 0.35)
        ctx.fill()
    elif layer == "BG":
        for k, x in enumerate(range(-560, 2500, 120)):
            tree(ctx, x, hz + 60, 1.2 + (k % 3) * 0.2, "#3f7d45", "#4a3526", seed=k)
    elif layer == "MG":
        for k, x in enumerate(range(-500, 2500, 260)):
            tree(ctx, x + (k * 61) % 80, 780, 1.6 + (k % 2) * 0.3, "#4b9a45", "#6a4a30", seed=k + 30)
        for x in (300, 1100, 1800):
            curve(ctx, (x, 200), (x + 30, 420), (x + 10, 620), 5, "#3c7a30")
    elif layer == "GROUND":
        ground(ctx, 740, "#6a9a4a", "#4d7f37")
        ctx.new_path()
        ellipse_path(ctx, 960, 960, 1100, 90)
        src(ctx, "#8a6a42", 0.55)
        ctx.fill()
        grass_tufts(ctx, 780, 1070, 90, 51, "#3a7a2c")
        r = rng(13)
        for _ in range(30):
            ellipse(ctx, r.uniform(X0, X1), r.uniform(800, 1070), 9, 4, ["#c98a2e", "#a35a2a", "#d8b03a"][r.randrange(3)], 0,
                    rot=r.uniform(0, 3))
    elif layer == "FG":
        for x, s in ((-80, 2.2), (2050, 2.4)):
            for k in range(6):
                a = -2.7 + k * 0.5
                ex, ey = x + math.cos(a) * 220 * s * 0.5, 1120 + math.sin(a) * 260 * s * 0.5
                curve(ctx, (x, 1120), ((x + ex) / 2 + 20, (1120 + ey) / 2 - 30), (ex, ey), 26, "#2f6e2a")


def _temple(ctx, layer, t, tod):
    hz = 640
    if layer == "SKY":
        sky(ctx, t, tod, hz)
    elif layer == "BG":
        hills(ctx, hz + 20, "#93c08a", 50, 61)
        for k, x in enumerate(range(-500, 2500, 280)):
            sugar_palm(ctx, x, hz + 40, 210 + (k * 37) % 60, t, "#4f9a52", 2.0)
    elif layer == "MG":
        pagoda(ctx, 960, 780, 1.12, t)
        stupa(ctx, 300, 790, 1.1)
        stupa(ctx, 1640, 790, 1.0)
        frangipani(ctx, -60, 800, 1.2, t)
        frangipani(ctx, 2000, 800, 1.25, t)
    elif layer == "GROUND":
        ground(ctx, 760, "#d9cfb8", "#c9bc9f")
        ctx.new_path()
        ctx.rectangle(X0, 760, X1 - X0, 30)
        src(ctx, "#b9ad92")
        ctx.fill()
        for k in range(-6, 30):
            line(ctx, [(k * 90, 800), (k * 90 - 120, 1080)], 1.6, "#b5a88c")
    elif layer == "FG":
        bush(ctx, -40, 1110, 1.8, "#3f8f3a")
        bush(ctx, 1990, 1110, 1.8, "#3f8f3a")


def _market(ctx, layer, t, tod):
    hz = 600
    if layer == "SKY":
        sky(ctx, t, tod, hz)
    elif layer == "BG":
        for k, x in enumerate(range(-500, 2500, 210)):
            h = 220 + (k * 47) % 120
            rrect(ctx, x, hz + 40 - h, 200, h + 40, 3, ["#e9d7b0", "#f0c58a", "#d8e2c8", "#efd2c4"][k % 4], BOL)
            for j in range(3):
                rrect(ctx, x + 20 + j * 60, hz + 40 - h + 30, 38, 48, 2, "#6a8fb0", 2)
    elif layer == "MG":
        for k, x in enumerate((60, 420, 780, 1160, 1540, 1900)):
            market_stall(ctx, x, 790, 1.0, ["#d8333a", "#2f7fc0", "#f0a52a", "#3a9a5a"][k % 4], seed=k)
    elif layer == "GROUND":
        ground(ctx, 720, "#d9c7a4", "#cbb68e")
        grass_tufts(ctx, 1040, 1075, 10, 71, "#8a9a55")
    elif layer == "FG":
        r = rng(3)
        for x in (60, 1860):
            ellipse(ctx, x, 1090, 90, 26, "#b5853f", BOL)
            for j in range(5):
                circle(ctx, x - 50 + j * 25, 1068, 16, ["#f2a531", "#e4542e", "#7cc04a"][j % 3], 2)


def _palace(ctx, layer, t, tod):
    hz = 600
    if layer == "SKY":
        sky(ctx, t, tod, hz)
    elif layer == "BG":
        angkor(ctx, 960, hz + 60, 1.0, "#a49c86")
        hills(ctx, hz + 80, "#8db87d", 20, 81)
    elif layer == "MG":
        for x in (-200, 200, 1720, 2120):
            rrect(ctx, x - 26, 380, 52, 420, 4, "#b52a2a", BOL)
            rrect(ctx, x - 34, 370, 68, 22, 3, "#e9b53b", BOL)
            rrect(ctx, x - 34, 790, 68, 18, 3, "#e9b53b", BOL)
        poly(ctx, [(-400, 380), (2340, 380), (2240, 300), (-300, 300)], "#c0392b", BOL)
        line(ctx, [(-400, 380), (2340, 380)], 8, "#e9b53b")
        frangipani(ctx, 560, 800, 1.0, t)
        frangipani(ctx, 1360, 800, 1.0, t)
    elif layer == "GROUND":
        ground(ctx, 780, "#e3d6b8", "#cdbb93")
        for k in range(-6, 30):
            line(ctx, [(k * 110, 800), (k * 110 - 160, 1080)], 1.6, "#bba77f")
        for y in (860, 960):
            line(ctx, [(X0, y), (X1, y)], 1.6, "#bba77f")
    elif layer == "FG":
        pass


def _palace_hall(ctx, layer, t, tod):
    if layer == "SKY":
        ctx.new_path()
        ctx.rectangle(X0, -200, X1 - X0, 1400)
        ctx.set_source(lin_grad(0, 0, 0, 800, [(0, "#7a1d1d"), (1, "#b1342c")]))
        ctx.fill()
    elif layer == "BG":
        for k in range(-3, 14):
            x = k * 220
            rrect(ctx, x + 40, 160, 140, 200, 8, "#9a2723", 2)
            ctx.new_path()
            ctx.move_to(x + 110, 190)
            ctx.line_to(x + 140, 260)
            ctx.line_to(x + 110, 330)
            ctx.line_to(x + 80, 260)
            ctx.close_path()
            fill_stroke(ctx, "#e9b53b", 1.6)
    elif layer == "MG":
        # throne dais
        rrect(ctx, 760, 640, 400, 140, 6, "#e9b53b", BOL)
        rrect(ctx, 820, 520, 280, 130, 10, "#c0392b", BOL)
        poly(ctx, [(810, 520), (960, 380), (1110, 520)], "#e9b53b", BOL)
        for x in (-160, 360, 1560, 2080):
            rrect(ctx, x - 30, 60, 60, 760, 4, "#c0392b", BOL)
            for y in (60, 790):
                rrect(ctx, x - 40, y - 10, 80, 26, 3, "#e9b53b", BOL)
    elif layer == "GROUND":
        ground(ctx, 790, "#8a3b2a", "#6e2a1f")
        ctx.new_path()
        ctx.move_to(800, 790)
        ctx.line_to(1120, 790)
        ctx.line_to(1400, 1090)
        ctx.line_to(520, 1090)
        ctx.close_path()
        fill_stroke(ctx, "#c9302c", 0)
        line(ctx, [(800, 790), (520, 1090)], 6, "#e9b53b")
        line(ctx, [(1120, 790), (1400, 1090)], 6, "#e9b53b")


def _river(ctx, layer, t, tod):
    hz = 600
    if layer == "SKY":
        sky(ctx, t, tod, hz)
    elif layer == "BG":
        hills(ctx, hz + 20, "#86b67c", 50, 91)
        for k, x in enumerate(range(-500, 2500, 170)):
            sugar_palm(ctx, x + (k * 53) % 80, hz + 40, 160 + (k * 31) % 80, t, "#4f9a52", 1.8)
            if k % 3 == 0:
                stilt_house(ctx, x + 60, hz + 46, 0.3)
    elif layer == "MG":
        water(ctx, hz + 40, 800, t, tod=tod)
        boat(ctx, 1300, 720, 0.9, t)
    elif layer == "GROUND":
        ctx.new_path()
        ctx.move_to(X0, 800)
        ctx.curve_to(500, 780, 1400, 820, X1, 790)
        ctx.line_to(X1, 1200)
        ctx.line_to(X0, 1200)
        ctx.close_path()
        ctx.set_source(lin_grad(0, 780, 0, 1080, [(0, "#c8b07a"), (1, "#9fbb5f")]))
        ctx.fill()
        # wooden dock
        rrect(ctx, 1560, 770, 420, 26, 3, "#8a5c36", BOL)
        for k in range(5):
            line(ctx, [(1580 + k * 95, 796), (1580 + k * 95, 860)], 10, "#6d4527")
        grass_tufts(ctx, 900, 1070, 50, 93)
    elif layer == "FG":
        r = rng(4)
        for x in (-40, 40, 1900, 1980):
            line(ctx, [(x, 1120), (x + math.sin(t + x) * 8, 900)], 6, "#4c8f35")
            ellipse(ctx, x, 900, 8, 24, "#7a4a2a", 1.6)


def _pond(ctx, layer, t, tod):
    if layer == "MG":
        water(ctx, 680, 820, t, "#3f9bc0", tod)
        for x, y, s in ((200, 760, 1.0), (520, 720, 0.8), (900, 780, 1.1), (1300, 740, 0.9), (1700, 770, 1.0)):
            lotus(ctx, x, y, s)
    elif layer == "GROUND":
        ctx.new_path()
        ctx.rectangle(X0, 820, X1 - X0, 400)
        ctx.set_source(lin_grad(0, 820, 0, 1080, [(0, "#9cc66a"), (1, "#74ac4e")]))
        ctx.fill()
        grass_tufts(ctx, 840, 1070, 60, 101)
    else:
        _village(ctx, layer, t, tod) if layer != "MG" else None


def _mountain(ctx, layer, t, tod):
    hz = 640
    if layer == "SKY":
        sky(ctx, t, tod, hz)
    elif layer == "BG":
        mountains(ctx, hz + 30, "#7e9fbf", 111, 420)
        mountains(ctx, hz + 50, "#6f9a7a", 112, 260)
    elif layer == "MG":
        hills(ctx, 760, "#79b05e", 90, 113)
        for x in (-200, 300, 1700, 2200):
            tree(ctx, x, 790, 1.3, seed=x)
    elif layer == "GROUND":
        ground(ctx, 760, "#8fbf62", "#6aa449")
        dirt_path(ctx, 760, "#c9a46e")
        grass_tufts(ctx, 800, 1070, 60, 115)
    elif layer == "FG":
        ellipse(ctx, -40, 1080, 200, 80, "#8d8a80", BOL)
        ellipse(ctx, 1980, 1090, 220, 90, "#8d8a80", BOL)


def _house_interior(ctx, layer, t, tod):
    if layer == "SKY":
        ctx.new_path()
        ctx.rectangle(X0, -200, X1 - X0, 1400)
        src(ctx, "#b77b46")
        ctx.fill()
        for k in range(-6, 32):
            line(ctx, [(k * 90, -200), (k * 90, 1200)], 3, "#9a6436")
    elif layer == "BG":
        for wx in (360, 1400):
            rrect(ctx, wx, 220, 260, 240, 6, "#8fd0f2", BOL)
            for k in range(1, 4):
                line(ctx, [(wx + 4, 220 + k * 60), (wx + 256, 220 + k * 60)], 4, "#7a4c2a")
            sugar_palm(ctx, wx + 130, 470, 200, t)
            rrect(ctx, wx, 220, 260, 240, 6, None, BOL)
        rrect(ctx, 820, 260, 240, 180, 6, "#e9d7b0", BOL)  # family picture frame
        circle(ctx, 940, 350, 50, "#f2c46a", 2)
    elif layer == "MG":
        rrect(ctx, 1700, 560, 300, 230, 6, "#7a4c2a", BOL)  # cabinet
        for k in range(3):
            circle(ctx, 1760 + k * 80, 540, 22, ["#c0392b", "#2f7fc0", "#e9b53b"][k], 2)
        blob(ctx, [(160, 790), (230, 790), (250, 720), (195, 670), (140, 720)], "#8b4a2c")  # water jar
    elif layer == "GROUND":
        ctx.new_path()
        ctx.rectangle(X0, 780, X1 - X0, 400)
        src(ctx, "#c48c55")
        ctx.fill()
        for k in range(8):
            line(ctx, [(X0, 780 + k * 40), (X1, 780 + k * 40)], 2, "#a06d3d")
        # woven mat
        ctx.new_path()
        ctx.move_to(560, 860)
        ctx.line_to(1360, 860)
        ctx.line_to(1460, 1040)
        ctx.line_to(460, 1040)
        ctx.close_path()
        fill_stroke(ctx, check_pattern("#c0392b", "#e9c46a", 14), BOL)


def _angkor(ctx, layer, t, tod):
    hz = 560
    if layer == "SKY":
        sky(ctx, t, tod, hz)
    elif layer == "BG":
        angkor(ctx, 960, hz + 120, 1.1, "#9b947f")
        for x in (-300, 2200):
            sugar_palm(ctx, x, hz + 110, 260, t)
    elif layer == "MG":
        water(ctx, hz + 120, 780, t, "#5aa8c8", tod)
        for x in (200, 1720):
            lotus(ctx, x, 740, 1.0)
    elif layer == "GROUND":
        ctx.new_path()
        ctx.rectangle(X0, 780, X1 - X0, 400)
        src(ctx, "#cfc4a8")
        ctx.fill()
        for k in range(-6, 40):
            line(ctx, [(k * 80, 790), (k * 80 - 60, 1080)], 1.4, "#b4a888")
        rrect(ctx, X0, 770, X1 - X0, 24, 2, "#b4a888", BOL)
    elif layer == "FG":
        for x in (-60, 1980):
            for k in range(3):
                line(ctx, [(x + k * 30, 1100), (x + k * 30 + 20, 860)], 10, "#4f9a3a")


def _school(ctx, layer, t, tod):
    if layer == "MG":
        rrect(ctx, 380, 440, 1160, 350, 6, "#f3d98a", BOL)
        poly(ctx, [(330, 450), (960, 300), (1590, 450)], "#2f6fb2", BOL)
        for k in range(5):
            x = 450 + k * 220
            rrect(ctx, x, 520, 120, 120, 4, "#8fd0f2", BOL)
            line(ctx, [(x + 60, 524), (x + 60, 636)], 3, "#ffffff")
        rrect(ctx, 900, 660, 120, 130, 4, "#7a4c2a", BOL)
        tree(ctx, 160, 800, 1.3, seed=5)
        tree(ctx, 1780, 800, 1.4, seed=6)
        line(ctx, [(1660, 800), (1660, 420)], 6, "#9aa3ab")
    elif layer == "GROUND":
        ground(ctx, 790, "#d6c49a", "#c3ae80")
        grass_tufts(ctx, 820, 1070, 30, 121)
    else:
        _village(ctx, layer, t, tod) if layer in ("SKY", "FG") else hills(ctx, 640, "#8fbf8a", 60, 122)


def _town(ctx, layer, t, tod):
    hz = 620
    if layer == "SKY":
        sky(ctx, t, tod, hz)
    elif layer == "BG":
        for k, x in enumerate(range(-500, 2500, 160)):
            h = 260 + (k * 67) % 200
            rrect(ctx, x, hz + 60 - h, 150, h, 2, ["#c9d6e3", "#e3d0b5", "#d4c3d9"][k % 3], BOL * 0.8)
    elif layer == "MG":
        cols = ["#f0c58a", "#e8a798", "#b7d3a8", "#f3e08e", "#a8c8e8"]
        for k, x in enumerate(range(-480, 2500, 330)):
            rrect(ctx, x, 380, 320, 420, 3, cols[k % len(cols)], BOL)
            rrect(ctx, x + 20, 640, 280, 160, 3, "#5a4a3a", BOL)
            for j in range(2):
                rrect(ctx, x + 40 + j * 140, 430, 100, 120, 3, "#8fb8d8", BOL * 0.8)
            poly(ctx, [(x - 10, 640), (x + 330, 640), (x + 350, 600), (x - 30, 600)], ["#d8333a", "#2f7fc0", "#3a9a5a"][k % 3], BOL)
    elif layer == "GROUND":
        ground(ctx, 800, "#b9b4aa", "#9f9a90")
        ctx.new_path()
        ctx.rectangle(X0, 800, X1 - X0, 40)
        src(ctx, "#d6d0c4")
        ctx.fill()
        for k in range(-6, 40):
            line(ctx, [(k * 160, 960), (k * 160 + 80, 960)], 6, "#f2f2f2")


ENVIRONMENTS = {
    "village": _village,
    "rice_field": _rice_field,
    "rice_field_harvest": lambda c, l, t, d: _rice_field(c, l, t, d, mature=True),
    "farm": _farm,
    "forest": _forest,
    "temple": _temple,
    "market": _market,
    "palace": _palace,
    "palace_hall": _palace_hall,
    "river": _river,
    "pond": _pond,
    "mountain": _mountain,
    "house_interior": _house_interior,
    "angkor": _angkor,
    "school": _school,
    "town": _town,
}


def draw_layer(ctx, env, layer, t, tod):
    fn = ENVIRONMENTS.get(env)
    if fn is None:
        raise KeyError("unknown environment '%s'. Available: %s" % (env, ", ".join(sorted(ENVIRONMENTS))))
    if env == "house_interior" or env == "palace_hall":
        tod_eff = tod
    else:
        tod_eff = tod
    fn(ctx, layer, t, tod_eff)


def apply_tint(ctx, tod, w, h):
    p = TOD.get(tod)
    if not p or not p.get("tint"):
        return
    col, a = p["tint"]
    ctx.save()
    ctx.set_operator(cairo.OPERATOR_MULTIPLY)
    ctx.set_source_rgba(col[0], col[1], col[2], a)
    ctx.rectangle(0, 0, w, h)
    ctx.fill()
    ctx.restore()
