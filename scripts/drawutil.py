"""Shared cairo drawing helpers: colours, outlined shapes, patterns, easing."""
import math
import random

import cairocffi as cairo

OUTLINE = (0.09, 0.07, 0.06)
OL = 4.2  # outline width in character units (character ~450 units tall)


def hexc(c):
    if isinstance(c, (tuple, list)):
        return tuple(c[:3])
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def shade(c, k):
    """k<0 darkens, k>0 lightens."""
    r, g, b = hexc(c)
    if k < 0:
        return (r * (1 + k), g * (1 + k), b * (1 + k))
    return (r + (1 - r) * k, g + (1 - g) * k, b + (1 - b) * k)


def mix(a, b, t):
    a, b = hexc(a), hexc(b)
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_io(t):
    t = clamp(t)
    return 0.5 - 0.5 * math.cos(math.pi * t)


def src(ctx, c, a=1.0):
    r, g, b = hexc(c)
    if a >= 1.0:
        ctx.set_source_rgb(r, g, b)
    else:
        ctx.set_source_rgba(r, g, b, a)


def fill_stroke(ctx, fill, ol=OL, line=OUTLINE):
    """Fill current path with colour (or pattern) and stroke a cartoon outline."""
    if fill is not None:
        if isinstance(fill, cairo.Pattern):
            ctx.set_source(fill)
        else:
            src(ctx, fill)
        if ol:
            ctx.fill_preserve()
        else:
            ctx.fill()
    if ol:
        src(ctx, line)
        ctx.set_line_width(ol)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.stroke()


def ellipse_path(ctx, x, y, rx, ry, rot=0.0):
    ctx.save()
    ctx.translate(x, y)
    if rot:
        ctx.rotate(rot)
    ctx.scale(max(rx, 0.01), max(ry, 0.01))
    ctx.new_sub_path()
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()


def ellipse(ctx, x, y, rx, ry, fill, ol=OL, rot=0.0):
    ctx.new_path()
    ellipse_path(ctx, x, y, rx, ry, rot)
    fill_stroke(ctx, fill, ol)


def circle(ctx, x, y, r, fill, ol=OL):
    ellipse(ctx, x, y, r, r, fill, ol)


def rrect_path(ctx, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    ctx.close_path()


def rrect(ctx, x, y, w, h, r, fill, ol=OL):
    ctx.new_path()
    rrect_path(ctx, x, y, w, h, r)
    fill_stroke(ctx, fill, ol)


def poly_path(ctx, pts, close=True):
    ctx.move_to(*pts[0])
    for p in pts[1:]:
        ctx.line_to(*p)
    if close:
        ctx.close_path()


def poly(ctx, pts, fill, ol=OL):
    ctx.new_path()
    poly_path(ctx, pts)
    fill_stroke(ctx, fill, ol)


def smooth_path(ctx, pts, close=True, tension=0.5):
    """Catmull-Rom spline through points."""
    n = len(pts)
    if n < 3:
        poly_path(ctx, pts, close)
        return
    ctx.move_to(*pts[0])
    rng = range(n) if close else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n] if (close or i > 0) else pts[i]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if (close or i + 2 < n) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) * tension / 3, p1[1] + (p2[1] - p0[1]) * tension / 3)
        c2 = (p2[0] - (p3[0] - p1[0]) * tension / 3, p2[1] - (p3[1] - p1[1]) * tension / 3)
        ctx.curve_to(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
    if close:
        ctx.close_path()


def blob(ctx, pts, fill, ol=OL):
    ctx.new_path()
    smooth_path(ctx, pts)
    fill_stroke(ctx, fill, ol)


def limb(ctx, pts, width, fill, ol=OL, cap=cairo.LINE_CAP_ROUND):
    """Thick outlined stroke (cartoon limb)."""
    ctx.new_path()
    poly_path(ctx, pts, close=False)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_cap(cap)
    if ol:
        src(ctx, OUTLINE)
        ctx.set_line_width(width + 2 * ol)
        ctx.stroke_preserve()
    src(ctx, fill)
    ctx.set_line_width(width)
    ctx.stroke()


def line(ctx, pts, width, color=OUTLINE, a=1.0):
    ctx.new_path()
    poly_path(ctx, pts, close=False)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    src(ctx, color, a)
    ctx.set_line_width(width)
    ctx.stroke()


def curve(ctx, p0, c, p1, width, color=OUTLINE, a=1.0):
    ctx.new_path()
    ctx.move_to(*p0)
    ctx.curve_to(c[0], c[1], c[0], c[1], p1[0], p1[1])
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    src(ctx, color, a)
    ctx.set_line_width(width)
    ctx.stroke()


_PATTERN_CACHE = {}


def check_pattern(c1, c2="#f4efe6", size=9.0):
    """Krama (Cambodian checked scarf) pattern."""
    key = ("chk", str(c1), str(c2), size)
    if key in _PATTERN_CACHE:
        return _PATTERN_CACHE[key]
    n = 4
    s = int(size * n)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, s, s)
    g = cairo.Context(surf)
    src(g, c2)
    g.paint()
    a = hexc(c1)
    for i in range(n):
        for j in range(n):
            if i % 2 == 0 or j % 2 == 0:
                alpha = 0.95 if (i % 2 == 0 and j % 2 == 0) else 0.55
                g.set_source_rgba(a[0], a[1], a[2], alpha)
                g.rectangle(i * size, j * size, size, size)
                g.fill()
    pat = cairo.SurfacePattern(surf)
    pat.set_extend(cairo.EXTEND_REPEAT)
    pat.set_filter(cairo.FILTER_GOOD)
    _PATTERN_CACHE[key] = pat
    return pat


def stripe_pattern(c1, c2, size=10.0, vertical=False):
    key = ("str", str(c1), str(c2), size, vertical)
    if key in _PATTERN_CACHE:
        return _PATTERN_CACHE[key]
    s = int(size * 2)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, s, s)
    g = cairo.Context(surf)
    src(g, c1)
    g.paint()
    src(g, c2)
    if vertical:
        g.rectangle(0, 0, size, s)
    else:
        g.rectangle(0, 0, s, size)
    g.fill()
    pat = cairo.SurfacePattern(surf)
    pat.set_extend(cairo.EXTEND_REPEAT)
    _PATTERN_CACHE[key] = pat
    return pat


def lin_grad(x0, y0, x1, y1, stops):
    g = cairo.LinearGradient(x0, y0, x1, y1)
    for off, c in stops:
        if isinstance(c, tuple) and len(c) == 4:
            g.add_color_stop_rgba(off, *c)
        else:
            g.add_color_stop_rgb(off, *hexc(c))
    return g


def rad_grad(x, y, r0, r1, stops):
    g = cairo.RadialGradient(x, y, r0, x, y, r1)
    for off, c in stops:
        if isinstance(c, tuple) and len(c) == 4:
            g.add_color_stop_rgba(off, *c)
        else:
            g.add_color_stop_rgb(off, *hexc(c))
    return g


def flower(ctx, x, y, r, color, center="#f7d23e", ol=1.6):
    for k in range(5):
        a = k * 2 * math.pi / 5 - math.pi / 2
        ellipse(ctx, x + math.cos(a) * r * 0.55, y + math.sin(a) * r * 0.55, r * 0.5, r * 0.5, color, ol)
    circle(ctx, x, y, r * 0.3, center, ol * 0.7)


def rng(seed):
    return random.Random(seed)


def ik2(sx, sy, tx, ty, l1, l2, pref):
    """2-bone IK in 2D. pref: preferred bend direction vector. Returns (elbow, hand)."""
    dx, dy = tx - sx, ty - sy
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return (sx, sy + l1), (sx, sy + l1 + l2)
    maxd = (l1 + l2) * 0.999
    if d > maxd:
        tx, ty = sx + dx / d * maxd, sy + dy / d * maxd
        dx, dy, d = tx - sx, ty - sy, maxd
    mind = abs(l1 - l2) + 1e-3
    if d < mind:
        d = mind
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = math.sqrt(max(l1 * l1 - a * a, 0))
    ux, uy = dx / d, dy / d
    px, py = sx + ux * a, sy + uy * a
    nx, ny = -uy, ux
    if nx * pref[0] + ny * pref[1] < 0:
        nx, ny = -nx, -ny
    return (px + nx * h, py + ny * h), (tx, ty)
