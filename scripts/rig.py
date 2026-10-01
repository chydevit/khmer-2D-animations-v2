"""Procedural 2D character rig in the locked Khmer chibi style of the reference sheet.

Big round head, small black dot eyes, no nose, clean black outlines, warm yellow skin,
simple body. Everything is vector (cairo) so characters stay identical in every shot
and stay crisp in close-ups.

Character-local coordinates: origin at the feet (ground contact), y grows downwards,
an adult is ~450 units tall. draw_character() places it at (x, y) with a scale.
"""
import math
import zlib

import cairocffi as cairo

from drawutil import (OL, OUTLINE, blob, poly_path, check_pattern, circle, clamp, curve, ellipse,
                      ellipse_path, fill_stroke, flower, hexc, ik2, lerp, limb, line, mix,
                      poly, rrect, shade, smooth, src, stripe_pattern)

SKIN = "#FED06F"
MOUTH_IN = "#8a2a24"
TONGUE = "#e8807a"
GOLD = "#F2B632"

BUILDS = {
    # R head radius, sw shoulder width, sh shoulder y, wa waist y, hip y,
    # a1/a2 arm bones, aw arm width, lw leg width
    "adult_m": dict(R=80, sw=140, sh=-290, wa=-165, hip=-150, a1=68, a2=62, aw=28, lw=46),
    "adult_f": dict(R=80, sw=122, sh=-288, wa=-170, hip=-155, a1=66, a2=60, aw=25, lw=40),
    "elder_m": dict(R=80, sw=136, sh=-282, wa=-160, hip=-146, a1=66, a2=60, aw=27, lw=44, stoop=5),
    "elder_f": dict(R=80, sw=124, sh=-280, wa=-162, hip=-148, a1=64, a2=58, aw=25, lw=40, stoop=5),
    "teen": dict(R=76, sw=118, sh=-246, wa=-140, hip=-128, a1=58, a2=54, aw=25, lw=40),
    "child": dict(R=70, sw=104, sh=-200, wa=-112, hip=-102, a1=48, a2=45, aw=23, lw=36),
}

DEFAULT_RIG = {
    "build": "adult_m",
    "skin": SKIN,
    "hair": {"style": "short", "color": "#151515", "flower": None},
    "beard": None,
    "top": {"style": "longsleeve", "color": "#1f8a4c"},
    "bottom": {"style": "pants", "color": "#7a7a7a"},
    "sash": "#d9333a",
    "scarf": None,
    "headwear": None,
    "jewelry": [],
    "shoes": "sandals",
    "prop": None,
}


def merge_rig(rig):
    out = {}
    for k, v in DEFAULT_RIG.items():
        r = rig.get(k, v) if rig else v
        if isinstance(v, dict) and isinstance(r, dict):
            d = dict(v)
            d.update(r)
            out[k] = d
        else:
            out[k] = r
    for k, v in (rig or {}).items():
        if k not in out:
            out[k] = v
    return out


# --------------------------------------------------------------------------- poses
# Hand targets in body space: (lat_out, fwd, dy) relative to that arm's shoulder.
# lat_out > 0 = outwards from the body, -sw/2 reaches the body centre line.
# fwd > 0 = towards the character's facing direction.  dy > 0 = down.

def _arm_rest(b):
    return (2, 10, (b["a1"] + b["a2"]) * 0.97)


def pose_targets(name, b, t, talk=0.0, phase=0.0):
    """Return dict(near=(lat,fwd,dy), far=..., lean=deg, head_dy, head_tilt, bounce, fists)."""
    sw = b["sw"]
    L = b["a1"] + b["a2"]
    rest = _arm_rest(b)
    P = dict(near=rest, far=rest, lean=0.0, head_dy=0.0, head_tilt=0.0, bounce=0.0,
             hold=None, shake=0.0)
    c = -sw / 2  # reach body centre
    if name in ("stand", "idle", "walk", "run", "sit"):
        pass
    elif name == "clasp":  # hands folded in front (polite)
        P["near"] = (c + 6, 30, L * 0.90)
        P["far"] = (c - 2, 28, L * 0.93)
    elif name == "sampeah":  # palms together at chest
        P["near"] = (c + 2, 34, L * 0.30)
        P["far"] = (c - 2, 32, L * 0.32)
        P["head_dy"] = 4
        P["hold"] = "sampeah"
    elif name == "sampeah_high":  # respect to monks / king
        P["near"] = (c + 2, 34, -L * 0.05)
        P["far"] = (c - 2, 32, -L * 0.03)
        P["head_dy"] = 8
        P["hold"] = "sampeah"
    elif name == "bow":
        P["near"] = (c + 2, 34, L * 0.30)
        P["far"] = (c - 2, 32, L * 0.32)
        P["lean"] = 24
        P["head_dy"] = 6
        P["hold"] = "sampeah"
    elif name == "point":
        P["near"] = (L * 0.30, L * 0.90, L * 0.05)
        P["hold"] = "point"
    elif name == "talk":
        g = math.sin(t * 5.2) * talk
        P["near"] = (-4, L * 0.55 + 8 * g, L * 0.52 - 10 * g)
        P["hold"] = "open"
    elif name == "explain":  # both hands open
        g = math.sin(t * 4.4) * talk
        P["near"] = (-2, L * 0.55 + 6 * g, L * 0.50 - 8 * g)
        P["far"] = (4, L * 0.45 - 6 * g, L * 0.55 + 6 * g)
        P["hold"] = "open"
    elif name == "wave":
        g = math.sin(t * 9.0)
        P["near"] = (L * 0.62 + 14 * g, 6, -L * 0.66)
        P["hold"] = "open"
    elif name == "think":
        P["near"] = (c + sw * 0.22, 40, -L * 0.18)
        P["far"] = (c + 8, 30, L * 0.58)
        P["head_tilt"] = 6
    elif name == "afraid":
        sh = math.sin(t * 38) * 2.5
        P["near"] = (c + sw * 0.30, 34, L * 0.15 + sh)
        P["far"] = (c + sw * 0.25, 30, L * 0.18 - sh)
        P["shake"] = 1.8
    elif name == "cry":
        P["near"] = (c + sw * 0.26, 34, -L * 0.40)
        P["far"] = (c + sw * 0.20, 30, -L * 0.38)
        P["head_dy"] = 6
        P["shake"] = 0.8
    elif name == "laugh":
        P["near"] = (c + 22, 26, L * 0.62)
        P["far"] = (c + 18, 22, L * 0.64)
        P["bounce"] = abs(math.sin(t * 9)) * 5
        P["head_tilt"] = -6
    elif name == "angry":  # fists down at sides
        P["near"] = (16, 2, L * 0.86)
        P["far"] = (16, 2, L * 0.86)
        P["shake"] = 0.6
        P["hold"] = "fist"
    elif name == "arms_crossed":
        P["near"] = (c + sw * 0.62, 30, L * 0.40)
        P["far"] = (c + sw * 0.60, 26, L * 0.36)
    elif name == "carry":  # object held in front with both hands
        P["near"] = (c + 18, 40, L * 0.55)
        P["far"] = (c + 18, 36, L * 0.55)
        P["hold"] = "carry"
    elif name == "carry_head":  # basket on head
        P["near"] = (8, 6, -L * 0.95)
        P["hold"] = "carry_head"
    elif name == "hold_bowl":  # monk alms bowl
        P["near"] = (c + 14, 34, L * 0.52)
        P["far"] = (c + 14, 30, L * 0.56)
        P["hold"] = "bowl"
    elif name == "give":  # hand object forward to someone
        P["near"] = (-8, L * 0.86, L * 0.38)
        P["far"] = (-8, L * 0.80, L * 0.42)
        P["hold"] = "give"
    elif name == "pick_up":
        P["near"] = (-6, L * 0.55, L * 1.15)
        P["lean"] = 30
        P["hold"] = "open"
    elif name == "shoulder_tool":  # hoe / tool on shoulder
        P["near"] = (c + sw * 0.75, 24, L * 0.05)
        P["hold"] = "shoulder"
    elif name == "hold_staff":  # cane, spear
        P["near"] = (8, 30, L * 0.80)
        P["hold"] = "staff"
    elif name == "hip_basket":
        P["near"] = (12, 16, L * 0.84)
        P["hold"] = "hip"
    elif name == "dance":  # apsara-like
        w = math.sin(t * 1.6)
        P["near"] = (20, 8, -L * 0.30 + 6 * w)
        P["far"] = (30, -10, L * 0.55 - 6 * w)
        P["head_tilt"] = 8 * w
        P["hold"] = "dance"
    elif name == "work":  # hoe / digging cycle
        k = 0.5 + 0.5 * math.sin(t * 4.2)
        P["near"] = (c + 18, lerp(30, L * 0.75, k), lerp(-L * 0.55, L * 0.95, k))
        P["far"] = (c + 22, lerp(22, L * 0.65, k), lerp(-L * 0.45, L * 0.95, k))
        P["lean"] = lerp(-4, 20, k)
        P["hold"] = "work"
    elif name == "fight":  # spear / sword thrust cycle
        k = smooth((math.sin(t * 5.0) + 1) / 2)
        P["near"] = (-6, lerp(L * 0.35, L * 0.98, k), L * 0.40)
        P["far"] = (10, lerp(-10, L * 0.40, k), L * 0.55)
        P["lean"] = lerp(0, 12, k)
        P["hold"] = "staff"
    elif name == "sit_hands":  # sitting, hands on lap
        P["near"] = (c + 18, 30, L * 0.70)
        P["far"] = (c + 18, 28, L * 0.72)
    elif name == "pray":  # = sampeah, kept as alias
        return pose_targets("sampeah", b, t, talk, phase)
    return P


POSES = ["stand", "clasp", "sampeah", "sampeah_high", "bow", "point", "talk", "explain", "wave",
         "think", "afraid", "cry", "laugh", "angry", "arms_crossed", "carry", "carry_head",
         "hold_bowl", "give", "pick_up", "shoulder_tool", "hold_staff", "hip_basket", "dance",
         "work", "fight", "sit_hands"]

EXPRESSIONS = ["neutral", "happy", "sad", "angry", "afraid", "surprised", "laughing", "crying",
               "thinking", "worried", "smile", "calm", "determined", "shy"]

VISEMES = ["rest", "A", "E", "I", "O", "U", "MBP", "FV", "LR"]


# --------------------------------------------------------------------------- face

def _sph(cx, R, phi_deg, alpha_deg, k):
    a = math.radians(phi_deg + alpha_deg)
    return cx + R * k * math.sin(a), math.cos(a)


def draw_eyes(ctx, cx, cy, R, phi, expr, blink, look=(0.0, 0.0)):
    out = []
    for a in (-20, 20):
        x, vis = _sph(cx, R, phi, a, 0.86)
        if vis > 0.12:
            out.append((x, vis))
    ey = cy + 0.24 * R + look[1] * R * 0.06
    er = R * 0.085
    for x, vis in out:
        x += look[0] * R * 0.06
        sq = 0.55 + 0.45 * vis  # horizontal squash near the silhouette
        if blink or expr in ("laughing", "crying"):
            if expr in ("laughing", "crying") and not blink:
                # happy / crying closed arcs
                ctx.new_path()
                if expr == "laughing":
                    ctx.move_to(x - er * 1.3 * sq, ey + er * 0.4)
                    ctx.curve_to(x - er * 0.6 * sq, ey - er * 1.3, x + er * 0.6 * sq, ey - er * 1.3,
                                 x + er * 1.3 * sq, ey + er * 0.4)
                else:
                    ctx.move_to(x - er * 1.3 * sq, ey - er * 0.2)
                    ctx.curve_to(x - er * 0.6 * sq, ey + er * 1.1, x + er * 0.6 * sq, ey + er * 1.1,
                                 x + er * 1.3 * sq, ey - er * 0.2)
                src(ctx, OUTLINE)
                ctx.set_line_width(R * 0.05)
                ctx.set_line_cap(cairo.LINE_CAP_ROUND)
                ctx.stroke()
            else:
                line(ctx, [(x - er * 1.2 * sq, ey), (x + er * 1.2 * sq, ey)], R * 0.045)
            continue
        if expr == "happy" or expr == "smile" or expr == "shy":
            ellipse(ctx, x, ey, er * sq, er * 0.95, OUTLINE, 0)
        elif expr in ("surprised", "afraid"):
            ellipse(ctx, x, ey, er * 1.25 * sq, er * 1.35, OUTLINE, 0)
            circle(ctx, x - er * 0.35 * sq, ey - er * 0.45, er * 0.38, "#ffffff", 0)
        elif expr == "thinking":
            ellipse(ctx, x + er * 0.3, ey - er * 0.6, er * sq, er, OUTLINE, 0)
        else:
            ellipse(ctx, x, ey, er * sq, er, OUTLINE, 0)
    return out, ey, er


def draw_brows(ctx, eyes, ey, er, R, expr):
    if expr not in ("sad", "angry", "afraid", "surprised", "worried", "crying", "determined",
                    "thinking"):
        return
    by = ey - R * 0.26
    w = er * 1.5
    for i, (x, vis) in enumerate(eyes):
        side = -1 if i == 0 else 1
        if len(eyes) == 1:
            side = 1
        # p1 is the inner end (towards the nose line)
        if expr in ("angry", "determined"):
            p0, p1 = (x + w * side * 0.9, by - w * 0.35), (x - w * side * 0.4, by + w * 0.30)
        elif expr in ("sad", "worried", "afraid", "crying"):
            p0, p1 = (x + w * side * 0.9, by + w * 0.30), (x - w * side * 0.5, by - w * 0.30)
        elif expr == "thinking":
            p0, p1 = (x - w * 0.8, by - w * (0.3 if side > 0 else -0.05)), (x + w * 0.8, by - w * 0.1)
        else:  # surprised
            p0, p1 = (x - w * 0.8, by - w * 0.5), (x + w * 0.8, by - w * 0.5)
        line(ctx, [p0, p1], R * 0.04)


def draw_mouth(ctx, cx, cy, R, phi, expr, vis_name, openness):
    mx, vis = _sph(cx, R, phi, 4, 0.74)
    if vis < 0.05:
        return
    my = cy + 0.56 * R
    sq = 0.5 + 0.5 * vis
    u = R * 0.16
    lw = R * 0.038
    speaking = vis_name and vis_name != "rest" and openness > 0.05
    if not speaking:
        if expr == "calm":
            curve(ctx, (mx - u * 0.35 * sq, my), (mx, my + u * 0.25), (mx + u * 0.35 * sq, my), lw)
        elif expr in ("happy", "smile", "shy"):
            curve(ctx, (mx - u * 0.55 * sq, my - u * 0.08), (mx, my + u * 0.55), (mx + u * 0.55 * sq, my - u * 0.08), lw)
        elif expr == "laughing":
            _open_mouth(ctx, mx, my - u * 0.1, u * 0.9 * sq, u * 0.75, smile=True)
        elif expr in ("sad", "worried"):
            curve(ctx, (mx - u * 0.45 * sq, my + u * 0.25), (mx, my - u * 0.25), (mx + u * 0.45 * sq, my + u * 0.25), lw)
        elif expr == "angry":
            curve(ctx, (mx - u * 0.5 * sq, my + u * 0.2), (mx, my - u * 0.15), (mx + u * 0.5 * sq, my + u * 0.2), lw)
        elif expr == "surprised":
            _open_mouth(ctx, mx, my + u * 0.1, u * 0.35 * sq, u * 0.42)
        elif expr == "afraid":
            ctx.new_path()
            n = 6
            for i in range(n + 1):
                x = mx - u * 0.6 * sq + i * u * 1.2 * sq / n
                y = my + u * 0.1 + (u * 0.12 if i % 2 else -u * 0.12)
                (ctx.move_to if i == 0 else ctx.line_to)(x, y)
            src(ctx, OUTLINE)
            ctx.set_line_width(lw)
            ctx.stroke()
        elif expr == "crying":
            _open_mouth(ctx, mx, my + u * 0.15, u * 0.6 * sq, u * 0.5, smile=False, frown=True)
        elif expr == "thinking":
            line(ctx, [(mx - u * 0.25 * sq, my + u * 0.1), (mx + u * 0.2 * sq, my + u * 0.05)], lw)
        elif expr == "determined":
            line(ctx, [(mx - u * 0.35 * sq, my + u * 0.05), (mx + u * 0.35 * sq, my + u * 0.05)], lw)
        return
    o = clamp(openness, 0.15, 1.0)
    smile = expr in ("happy", "laughing", "smile")
    v = vis_name
    if v == "MBP":
        line(ctx, [(mx - u * 0.45 * sq, my), (mx + u * 0.45 * sq, my)], lw * 1.1)
        return
    shapes = {"A": (0.62, 0.62), "E": (0.72, 0.36), "I": (0.66, 0.22), "O": (0.42, 0.55),
              "U": (0.28, 0.34), "FV": (0.55, 0.18), "LR": (0.5, 0.42)}
    w, h = shapes.get(v, (0.5, 0.4))
    _open_mouth(ctx, mx, my + u * 0.05, u * w * sq, u * h * (0.45 + 0.55 * o), smile=smile,
                teeth=(v in ("FV", "I", "E")), tongue=(v in ("A", "LR")))


def _open_mouth(ctx, x, y, rx, ry, smile=False, frown=False, teeth=False, tongue=False):
    ctx.new_path()
    if smile:
        ctx.move_to(x - rx, y - ry * 0.35)
        ctx.curve_to(x - rx * 0.6, y - ry * 0.55, x + rx * 0.6, y - ry * 0.55, x + rx, y - ry * 0.35)
        ctx.curve_to(x + rx * 0.9, y + ry * 1.2, x - rx * 0.9, y + ry * 1.2, x - rx, y - ry * 0.35)
        ctx.close_path()
    elif frown:
        ctx.move_to(x - rx, y + ry * 0.5)
        ctx.curve_to(x - rx * 0.8, y - ry * 1.1, x + rx * 0.8, y - ry * 1.1, x + rx, y + ry * 0.5)
        ctx.curve_to(x + rx * 0.5, y + ry * 0.2, x - rx * 0.5, y + ry * 0.2, x - rx, y + ry * 0.5)
        ctx.close_path()
    else:
        ellipse_path(ctx, x, y, rx, ry)
    ctx.save()
    src(ctx, MOUTH_IN)
    ctx.fill_preserve()
    ctx.clip_preserve()
    if tongue:
        ctx.new_path()
        ellipse_path(ctx, x, y + ry * 0.9, rx * 0.7, ry * 0.55)
        src(ctx, TONGUE)
        ctx.fill()
    if teeth:
        ctx.new_path()
        ctx.rectangle(x - rx, y - ry * 1.2, rx * 2, ry * 0.75)
        src(ctx, "#ffffff")
        ctx.fill()
    ctx.restore()
    src(ctx, OUTLINE)
    ctx.set_line_width(max(rx, ry) * 0.22)
    ctx.stroke()


def draw_face_extras(ctx, cx, cy, R, phi, expr, eyes, ey, t):
    if math.cos(math.radians(phi)) < 0.1:
        return
    if expr in ("happy", "laughing", "shy", "smile"):
        for x, vis in eyes:
            ellipse(ctx, x + R * 0.04, ey + R * 0.2, R * 0.12 * (0.5 + 0.5 * vis), R * 0.06,
                    (0.98, 0.55, 0.5), 0)
            ctx.new_path()
    if expr == "angry":
        x = cx + R * 0.5 * math.sin(math.radians(phi + 40))
        y = cy - R * 0.55
        for a in range(4):
            ang = a * math.pi / 2 + math.pi / 4
            line(ctx, [(x + math.cos(ang) * R * 0.05, y + math.sin(ang) * R * 0.05),
                       (x + math.cos(ang) * R * 0.14, y + math.sin(ang) * R * 0.14)], R * 0.035,
                 "#d8242c")
    if expr in ("afraid", "worried"):
        x = cx + R * 0.82 * math.sin(math.radians(phi + 55))
        y = cy - R * 0.1 + (t * 30) % 8
        ctx.new_path()
        ctx.move_to(x, y - R * 0.14)
        ctx.curve_to(x + R * 0.1, y, x + R * 0.08, y + R * 0.1, x, y + R * 0.1)
        ctx.curve_to(x - R * 0.08, y + R * 0.1, x - R * 0.1, y, x, y - R * 0.14)
        fill_stroke(ctx, (0.62, 0.84, 0.98), 1.5)
    if expr == "crying":
        for x, vis in eyes:
            ph = (t * 1.4 + x * 0.01) % 1.0
            y0 = ey + R * 0.1
            ctx.new_path()
            ctx.move_to(x, y0)
            ctx.line_to(x, y0 + R * (0.25 + 0.45 * ph))
            src(ctx, (0.45, 0.75, 0.98), 0.85)
            ctx.set_line_width(R * 0.06)
            ctx.set_line_cap(cairo.LINE_CAP_ROUND)
            ctx.stroke()
            circle(ctx, x, y0 + R * (0.3 + 0.5 * ph), R * 0.05, (0.45, 0.75, 0.98), 0)


# --------------------------------------------------------------------------- head

def draw_hair_back(ctx, rig, cx, cy, R, phi, front_view, sh_y, sw):
    hair = rig["hair"]
    style = hair.get("style")
    col = hair.get("color", "#151515")
    if style == "long":
        dep = math.cos(math.radians(phi))
        if dep > -0.3:  # visible behind the body
            x0 = cx - R * 0.35 * math.sin(math.radians(phi))
            blob(ctx, [(x0 - R * 0.85, cy), (x0 - R * 0.9, sh_y + R * 0.9), (x0 - R * 0.55, sh_y + R * 1.35),
                       (x0 + R * 0.4, sh_y + R * 1.25), (x0 + R * 0.85, sh_y + R * 0.6), (x0 + R * 0.8, cy)],
                 col)


def _bun_pos(cx, cy, R, phi, style):
    a = math.radians(phi + 180)
    if style == "bun_top":
        return cx + R * 0.25 * math.sin(a), cy - R * 1.0, R * 0.36, -math.cos(math.radians(phi))
    return cx + R * 0.62 * math.sin(a), cy - R * 0.68, R * 0.40, -math.cos(math.radians(phi))


def draw_bun(ctx, rig, cx, cy, R, phi, behind):
    hair = rig["hair"]
    style = hair.get("style")
    if style not in ("bun", "bun_top"):
        return
    bx, by, br, dep = _bun_pos(cx, cy, R, phi, style)
    is_behind = dep < 0.25
    if style == "bun_top":
        is_behind = dep < -0.2
    if behind != is_behind:
        return
    col = hair.get("color", "#151515")
    circle(ctx, bx, by, br, col)
    curve(ctx, (bx - br * 0.5, by - br * 0.2), (bx, by - br * 0.75), (bx + br * 0.5, by - br * 0.1),
          2.5, shade(col, 0.35) if sum(hexc(col)) > 0.6 else "#555555")
    fl = hair.get("flower")
    if fl:
        fx = bx + br * 0.75 * (1 if math.sin(math.radians(phi)) >= 0 else -1) * 0.6
        flower(ctx, fx, by + br * 0.45, R * 0.17, fl)


def draw_head(ctx, rig, cx, cy, R, phi, st):
    skin = rig.get("skin", SKIN)
    hair = rig["hair"]
    style = hair.get("style", "short")
    hcol = hair.get("color", "#151515")
    if style == "shaved":
        hcol = hair.get("color") if hair.get("color") not in (None, "#151515") else "#a39d94"
    s, c = math.sin(math.radians(phi)), math.cos(math.radians(phi))

    draw_bun(ctx, rig, cx, cy, R, phi, behind=True)

    # ears (only visible near profile) + earrings
    for a in (-90, 90):
        ex, vis = _sph(cx, R, phi, a, 0.97)
        if 0.0 < vis < 0.75 and style not in ("long",):
            pass
    # skull
    ctx.new_path()
    ellipse_path(ctx, cx, cy, R, R)
    ctx.save()
    ctx.clip_preserve()
    src(ctx, shade(skin, -0.10))
    ctx.fill()
    ctx.new_path()
    ellipse_path(ctx, cx - R * 0.14, cy - R * 0.16, R * 1.02, R * 1.02)
    src(ctx, skin)
    ctx.fill()
    # hair cap
    if style != "none" and hair.get("visible", True):
        face_vis = 1.0 if c >= 0 else max(0.0, 1 + c * 1.55)
        hb = lerp(0.12, 0.55, clamp(-c * 1.4 + 0.1, 0, 1))  # hair bottom (front -> back)
        if style == "shaved":
            hb = lerp(-0.05, 0.35, clamp(-c, 0, 1))
        if style == "long":
            hb = lerp(0.40, 0.8, clamp(-c, 0, 1))
        hb_y = cy + R * hb
        has_face = face_vis > 0.02
        fx = cx + R * 0.52 * s
        frx = R * 0.84 * (0.62 + 0.38 * abs(c)) * face_vis
        top = -0.34 if style != "shaved" else -0.50
        fry = R * (0.56 - top) * 0.62
        fcy = cy + R * top + fry
        big = (cx - R * 1.3, cy - R * 1.3, R * 2.6, R * 2.6)

        def face_path():
            ellipse_path(ctx, fx, fcy, frx, fry)

        # hair = (head above hair line) minus the face oval
        # hair line slopes down towards the back of the head in side views
        d = 1 if s >= 0 else -1
        hb_back = cy + R * lerp(hb, 0.62 if style != "shaved" else 0.45, abs(s))
        bx_edge = fx - d * frx * 0.92 if has_face else cx
        hair_poly = [(cx - d * R * 1.3, big[1]), (cx + d * R * 1.3, big[1]), (cx + d * R * 1.3, hb_y),
                     (bx_edge, hb_y), (bx_edge - d * R * 0.12, hb_back), (cx - d * R * 1.3, hb_back)]
        ctx.save()
        ctx.new_path()
        poly_path(ctx, hair_poly)
        ctx.clip()
        ctx.new_path()
        ctx.rectangle(*big)
        if has_face:
            face_path()
        ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        src(ctx, hcol)
        ctx.fill()
        if has_face:
            ctx.new_path()
            face_path()
            src(ctx, OUTLINE)
            ctx.set_line_width(2.6)
            ctx.stroke()
        ctx.restore()
        # hair bottom edge and long-hair side curtains, kept off the face
        ctx.save()
        ctx.new_path()
        ctx.rectangle(*big)
        if has_face:
            face_path()
        ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        ctx.clip()
        if style == "long":
            for side in (-1, 1):
                ctx.new_path()
                ellipse_path(ctx, cx + side * R * 0.95 * (0.4 + 0.6 * abs(c)) - s * R * 0.2, cy + R * 0.4,
                             R * 0.28, R * 0.6)
                fill_stroke(ctx, hcol, 2.6)
        else:
            line(ctx, hair_poly[2:], 2.6)
        ctx.restore()
        if has_face and style in ("short", "bun", "bun_top", "long") and hair.get("fringe", True) and c > -0.3:
            # side-swept fringe over the forehead
            d = 1 if s >= 0 else -1
            fr_x = fx - R * 0.18 * d - R * 0.15 * c
            a0 = (fr_x - frx * 1.1 * d, fcy - fry * 0.55)
            a1 = (fr_x + frx * 1.15 * d, fcy - fry * 0.40)
            ctx.new_path()
            ctx.move_to(*a0)
            ctx.curve_to(fr_x - frx * 0.4 * d, fcy - fry * 1.35, fr_x + frx * 0.9 * d, fcy - fry * 1.1, *a1)
            ctx.curve_to(fr_x + frx * 0.55 * d, fcy - fry * 0.78, fr_x - frx * 0.15 * d, fcy - fry * 0.70, *a0)
            ctx.close_path()
            src(ctx, hcol)
            ctx.fill()
            ctx.new_path()
            ctx.move_to(*a1)
            ctx.curve_to(fr_x + frx * 0.55 * d, fcy - fry * 0.78, fr_x - frx * 0.15 * d, fcy - fry * 0.70, *a0)
            src(ctx, OUTLINE)
            ctx.set_line_width(2.6)
            ctx.stroke()
        # hair shine
        if style not in ("shaved",) and sum(hexc(hcol)) < 1.2:
            curve(ctx, (cx - R * 0.55, cy - R * 0.55), (cx - R * 0.3, cy - R * 0.88), (cx + R * 0.05, cy - R * 0.9),
                  R * 0.06, "#ffffff", 0.18)
    ctx.restore()
    ctx.new_path()
    ellipse_path(ctx, cx, cy, R, R)
    fill_stroke(ctx, None)

    # earrings
    if "earrings" in rig.get("jewelry", []):
        for a in (-80, 80):
            ex, vis = _sph(cx, R, phi, a, 0.93)
            if vis > -0.05:
                circle(ctx, ex, cy + R * 0.42, R * 0.07, GOLD, 1.6)

    # beard
    if rig.get("beard") and c > -0.2:
        bx, _ = _sph(cx, R, phi, 6, 0.72)
        bc = rig["beard"] if isinstance(rig["beard"], str) else "#b9b9b9"
        blob(ctx, [(bx - R * 0.16, cy + R * 0.62), (bx + R * 0.16, cy + R * 0.62), (bx + R * 0.06, cy + R * 1.1),
                   (bx - R * 0.02, cy + R * 1.18)], bc, 1.8)
        curve(ctx, (bx - R * 0.32, cy + R * 0.58), (bx, cy + R * 0.46), (bx + R * 0.32, cy + R * 0.58), R * 0.07, bc)

    # face features
    if c > -0.12:
        expr = st.get("expr", "neutral")
        eyes, ey, er = draw_eyes(ctx, cx, cy, R, phi, expr, st.get("blink", False), st.get("look", (0, 0)))
        draw_brows(ctx, eyes, ey, er, R, expr)
        draw_mouth(ctx, cx, cy, R, phi, expr, st.get("viseme"), st.get("mouth_open", 0.0))
        draw_face_extras(ctx, cx, cy, R, phi, expr, eyes, ey, st.get("t", 0))

    draw_bun(ctx, rig, cx, cy, R, phi, behind=False)
    if hair.get("flower") and style not in ("bun", "bun_top"):
        fx, vis = _sph(cx, R, phi, -70, 0.8)
        flower(ctx, fx, cy - R * 0.55, R * 0.17, hair["flower"])
    draw_headwear(ctx, rig, cx, cy, R, phi, st.get("t", 0))


def draw_headwear(ctx, rig, cx, cy, R, phi, t):
    hw = rig.get("headwear")
    if not hw:
        return
    s, c = math.sin(math.radians(phi)), math.cos(math.radians(phi))
    if isinstance(hw, dict):
        kind, col = hw.get("type"), hw.get("color")
    else:
        kind, col = hw, None
    if kind == "conical_hat":
        col = col or "#E9B456"
        apex = (cx + R * 0.08 * s, cy - R * 1.32)
        poly(ctx, [(cx - R * 0.95, cy - R * 0.58), apex, (cx + R * 0.95, cy - R * 0.58)], col)
        for k in (-0.5, 0.0, 0.5):
            line(ctx, [apex, (cx + R * 0.95 * k, cy - R * 0.6)], 1.6, shade(col, -0.3))
        ellipse(ctx, cx, cy - R * 0.56, R * 1.5, R * 0.30, col)
        ctx.new_path()
        ellipse_path(ctx, cx, cy - R * 0.56, R * 1.2, R * 0.2)
        src(ctx, shade(col, -0.25))
        ctx.set_line_width(1.6)
        ctx.stroke()
    elif kind in ("mokot", "crown", "helmet"):
        col = col or GOLD
        tall = 2.25 if kind != "helmet" else 1.9
        rrect(ctx, cx - R * 0.98, cy - R * 0.72, R * 1.96, R * 0.3, R * 0.12, col)
        n = 5
        top_y = cy - R * tall
        base_y = cy - R * 0.72
        for i in range(n):
            k0 = i / n
            y0 = lerp(base_y, top_y + R * 0.35, k0)
            y1 = lerp(base_y, top_y + R * 0.35, (i + 1) / n)
            w0 = lerp(R * 0.9, R * 0.12, k0)
            w1 = lerp(R * 0.9, R * 0.12, (i + 1) / n)
            ox = R * 0.1 * s * k0
            poly(ctx, [(cx - w0 + ox, y0), (cx - w1 * 0.9 + ox, y1), (cx + w1 * 0.9 + ox, y1), (cx + w0 + ox, y0)],
                 shade(col, -0.06 * (i % 2)), 2.4)
        poly(ctx, [(cx - R * 0.12 + R * 0.1 * s, top_y + R * 0.36), (cx + R * 0.1 * s, top_y),
                   (cx + R * 0.12 + R * 0.1 * s, top_y + R * 0.36)], col, 2.4)
        circle(ctx, cx + R * 0.45 * s, cy - R * 0.58, R * 0.07, "#d8242c", 1.4)
        if kind != "helmet":  # ear ornaments
            for a in (-85, 85):
                ex, vis = _sph(cx, R, phi, a, 0.95)
                if vis > -0.1:
                    poly(ctx, [(ex, cy - R * 0.45), (ex - R * 0.12, cy + R * 0.05), (ex + R * 0.05, cy - R * 0.1)],
                         col, 1.8)
    elif kind == "tiara":
        col = col or GOLD
        base = cy - R * 0.62
        ctx.new_path()
        ctx.move_to(cx - R * 0.85, base + R * 0.1)
        for i in range(7):
            x = lerp(cx - R * 0.75, cx + R * 0.75, i / 6) + R * 0.15 * s
            h = R * (0.42 if i == 3 else (0.3 if i in (2, 4) else 0.2))
            ctx.line_to(x - R * 0.08, base)
            ctx.line_to(x, base - h)
            ctx.line_to(x + R * 0.08, base)
        ctx.line_to(cx + R * 0.85, base + R * 0.1)
        ctx.close_path()
        fill_stroke(ctx, col, 2.2)
        circle(ctx, cx + R * 0.15 * s, base - R * 0.1, R * 0.06, "#d8242c", 1.2)
    elif kind == "krama_head":
        col = col or "#b8203a"
        pat = check_pattern(col, "#f4efe6", 7)
        ctx.new_path()
        ctx.move_to(cx - R * 1.04, cy + R * 0.15)
        ctx.curve_to(cx - R * 1.15, cy - R * 1.25, cx + R * 1.15, cy - R * 1.25, cx + R * 1.04, cy + R * 0.15)
        ctx.curve_to(cx + R * 0.6 + R * 0.4 * s, cy - R * 0.45, cx - R * 0.6 + R * 0.4 * s, cy - R * 0.45,
                     cx - R * 1.04, cy + R * 0.15)
        ctx.close_path()
        fill_stroke(ctx, pat, 3.0)
        bx = cx - R * 0.95 * (1 if s >= 0 else -1)
        poly(ctx, [(bx, cy - R * 0.1), (bx - R * 0.25 * (1 if s >= 0 else -1), cy + R * 0.7),
                   (bx + R * 0.15 * (1 if s >= 0 else -1), cy + R * 0.65)], pat, 2.6)
    elif kind == "headband":
        col = col or "#d9333a"
        ctx.save()
        ctx.new_path()
        ellipse_path(ctx, cx, cy, R + 2, R + 2)
        ctx.clip()
        ctx.new_path()
        ctx.move_to(cx - R * 1.2, cy - R * 0.5)
        ctx.curve_to(cx - R * 0.4, cy - R * 0.32, cx + R * 0.4, cy - R * 0.32, cx + R * 1.2, cy - R * 0.5)
        ctx.line_to(cx + R * 1.2, cy - R * 0.25)
        ctx.curve_to(cx + R * 0.4, cy - R * 0.06, cx - R * 0.4, cy - R * 0.06, cx - R * 1.2, cy - R * 0.25)
        ctx.close_path()
        fill_stroke(ctx, col, 2.6)
        ctx.restore()
        side = -1 if s >= 0 else 1
        kx = cx + side * R * 0.95
        sway = math.sin(t * 3) * R * 0.05
        poly(ctx, [(kx, cy - R * 0.42), (kx + side * R * 0.55, cy - R * 0.7 + sway), (kx + side * R * 0.5, cy - R * 0.5 + sway)],
             col, 2.4)
        poly(ctx, [(kx, cy - R * 0.32), (kx + side * R * 0.5, cy - R * 0.15 + sway), (kx + side * R * 0.38, cy - R * 0.02 + sway)],
             col, 2.4)


# --------------------------------------------------------------------------- body

class Frame:
    """Projects body-space points (lat, fwd, y) to screen for a facing angle theta."""

    def __init__(self, theta):
        self.s = math.sin(math.radians(theta))
        self.c = math.cos(math.radians(theta))

    def x(self, lat, fwd):
        return lat * self.c + fwd * self.s

    def depth(self, lat, fwd):
        return -lat * self.s + fwd * self.c


def _leg_state(b, legs, phase, F, lean_run):
    """Return list of (hip, knee, ankle, depth, lift) for the two legs."""
    out = []
    hip_y = b["hip"]
    llen = -hip_y - 14
    l1, l2 = llen * 0.52, llen * 0.50
    for i, L in enumerate((-1, 1)):
        lat = L * b["sw"] * 0.2
        hx = F.x(lat, 0)
        if legs in ("walk", "run"):
            ph = phase + (0 if i == 0 else math.pi)
            stride = (0.42 if legs == "walk" else 0.62) * llen
            fwd = stride * math.sin(ph)
            lift = max(0.0, math.cos(ph)) * (0.14 if legs == "walk" else 0.28) * llen
            ax, ay = hx + F.s * fwd, -14 - lift
        else:
            fwd = 0
            ax, ay = hx * 1.05, -14
        pref = (F.s * 1.0 + 0.0001, -0.2)  # knees bend forward
        knee, ank = ik2(hx, hip_y, ax, ay, l1, l2, pref)
        out.append(dict(hip=(hx, hip_y), knee=knee, ankle=ank, depth=F.depth(lat, fwd), lat=lat, fwd=fwd))
    return out


def _sleeve_frac(top_style):
    return {"longsleeve": 0.97, "shortsleeve": 0.42, "none": 0.0, "wrap": 0.0, "sbai": 0.0,
            "robe": 0.0, "armor": 0.45, "royal": 0.30, "vest": 0.0, "blouse": 0.97}.get(top_style, 0.95)


def _point_along(pts, frac):
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    lens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs]
    total = sum(lens) * frac
    out = [pts[0]]
    for (a, b), l in zip(segs, lens):
        if total <= l:
            k = total / l if l else 0
            out.append((a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k))
            return out
        out.append(b)
        total -= l
    return out


def draw_arm(ctx, rig, b, arm, F, front, robe_bare=False):
    skin = rig.get("skin", SKIN)
    top = rig["top"]
    sh, el, hd = arm["sh"], arm["el"], arm["hand"]
    pts = [sh, el, hd]
    limb(ctx, pts, b["aw"] * 0.72, skin)
    frac = _sleeve_frac(top.get("style"))
    if top.get("style") == "robe" and not robe_bare:
        frac = 0.55
    if frac > 0:
        sl = _point_along(pts, frac)
        limb(ctx, sl, b["aw"], top.get("sleeve_color") or top.get("color"), cap=cairo.LINE_CAP_BUTT)
        ctx.new_path()
        ellipse_path(ctx, sh[0], sh[1], b["aw"] * 0.5 + 0.5, b["aw"] * 0.5 + 0.5)
        src(ctx, top.get("sleeve_color") or top.get("color"))
        ctx.fill()
    if "bracelets" in rig.get("jewelry", []):
        k = 0.86
        wx, wy = lerp(el[0], hd[0], k), lerp(el[1], hd[1], k)
        ellipse(ctx, wx, wy, b["aw"] * 0.42, b["aw"] * 0.2, GOLD, 1.4,
                rot=math.atan2(hd[1] - el[1], hd[0] - el[0]) + math.pi / 2)
    circle(ctx, hd[0], hd[1], b["aw"] * 0.44, skin, OL * 0.85)


def draw_leg(ctx, rig, b, lg, F):
    skin = rig.get("skin", SKIN)
    bottom = rig["bottom"]
    bstyle = bottom.get("style", "pants")
    hip, knee, ank = lg["hip"], lg["knee"], lg["ankle"]
    # shin / ankle skin
    limb(ctx, [knee, ank], b["lw"] * 0.42, skin)
    if bstyle in ("pants", "chang_kben", "longpants", "shorts"):
        frac = {"pants": 0.86, "chang_kben": 0.80, "longpants": 0.96, "shorts": 0.45}[bstyle]
        pts = _point_along([hip, knee, ank], frac)
        w = b["lw"] * (1.08 if bstyle == "chang_kben" else 1.0)
        limb(ctx, pts, w, bottom.get("color"), cap=cairo.LINE_CAP_BUTT)
        # cuff
        a, c2 = pts[-2], pts[-1]
        ang = math.atan2(c2[1] - a[1], c2[0] - a[0])
        nx, ny = -math.sin(ang), math.cos(ang)
        line(ctx, [(c2[0] - nx * w * 0.55, c2[1] - ny * w * 0.55), (c2[0] + nx * w * 0.55, c2[1] + ny * w * 0.55)],
             OL)
    # foot
    fx = ank[0] + F.s * 10
    shoes = rig.get("shoes", "sandals")
    fw = b["lw"] * 0.5 * (0.75 + 0.25 * abs(F.s))
    if shoes == "barefoot":
        ellipse(ctx, fx, ank[1] + 6, fw, b["lw"] * 0.2, skin, OL * 0.8)
    else:
        ellipse(ctx, fx, ank[1] + 8, fw + 3, b["lw"] * 0.17, "#3b2a20", OL * 0.8)
        ellipse(ctx, fx, ank[1] + 4, fw - 2, b["lw"] * 0.16, skin, OL * 0.6)
    if "anklets" in rig.get("jewelry", []):
        ellipse(ctx, ank[0], ank[1] - 6, b["lw"] * 0.28, 3, GOLD, 1.2)


def torso_path(ctx, b, F, sh_y, wa_y, bulge=1.0, female=False):
    w = b["sw"] * (0.74 + 0.26 * abs(F.c)) / 2
    wb = w * (0.92 if female else 1.0)
    bot = b["hip"] + 18
    r = b["aw"] * 0.75
    ctx.new_path()
    ctx.move_to(-w + r, sh_y)
    ctx.line_to(w - r, sh_y)
    ctx.curve_to(w - r * 0.2, sh_y, w + 2, sh_y + r * 0.4, w + 2, sh_y + r)
    ctx.curve_to(w + 4 * bulge, (sh_y + bot) / 2, wb + 6 * bulge, bot - 10, wb + 4, bot)
    ctx.line_to(-wb - 4, bot)
    ctx.curve_to(-wb - 6 * bulge, bot - 10, -w - 4 * bulge, (sh_y + bot) / 2, -w - 2, sh_y + r)
    ctx.curve_to(-w - 2, sh_y + r * 0.4, -w + r * 0.2, sh_y, -w + r, sh_y)
    ctx.close_path()
    return w, bot


def _shaded_fill(ctx, color, w, top, bot, F):
    """Fill current path with colour plus a soft shadow band on the right side."""
    ctx.save()
    ctx.clip_preserve()
    if isinstance(color, cairo.Pattern):
        ctx.set_source(color)
    else:
        src(ctx, color)
    ctx.fill_preserve()
    ctx.new_path()
    ctx.rectangle(w * 0.45, top - 50, w * 2, bot - top + 100)
    ctx.set_source_rgba(0, 0, 0, 0.10)
    ctx.fill()
    ctx.restore()
    fill_stroke(ctx, None)


def draw_torso(ctx, rig, b, F):
    top = rig["top"]
    style = top.get("style", "longsleeve")
    col = top.get("color", "#1f8a4c")
    skin = rig.get("skin", SKIN)
    female = rig.get("build", "").endswith("_f") or rig.get("female", False)
    sh_y = b["sh"]
    if style in ("none", "wrap", "sbai", "royal"):
        w, bot = torso_path(ctx, b, F, sh_y, b["wa"], female=female)
        _shaded_fill(ctx, skin, w, sh_y, bot, F)
        if style == "none":
            curve(ctx, (-w * 0.25, b["wa"] + 4), (0, b["wa"] + 12), (w * 0.25, b["wa"] + 4), 1.8, OUTLINE, 0.5)
        if style in ("wrap", "sbai", "royal"):
            ctx.save()
            torso_path(ctx, b, F, sh_y, b["wa"], female=female)
            ctx.clip()
            yb0 = sh_y + (b["wa"] - sh_y) * 0.22
            ctx.new_path()
            ctx.rectangle(-w * 2, yb0, w * 4, b["hip"] + 40 - yb0)
            _shaded_fill(ctx, col, w, yb0, b["hip"] + 40, F)
            if style in ("sbai", "royal"):
                acc = top.get("accent", GOLD if style == "royal" else shade(col, -0.25))
                ctx.new_path()
                ctx.move_to(-w * 1.1 + F.s * 10, yb0 - 4)
                ctx.line_to(-w * 0.5 + F.s * 10, yb0 - 4)
                ctx.line_to(w * 1.2, b["wa"] - 6)
                ctx.line_to(w * 1.2, b["wa"] + 18)
                ctx.close_path()
                fill_stroke(ctx, acc, 2.4)
            if style == "royal":
                line(ctx, [(-w * 1.2, yb0 + 3), (w * 1.2, yb0 + 3)], 5, GOLD)
            ctx.restore()
            torso_path(ctx, b, F, sh_y, b["wa"], female=female)
            fill_stroke(ctx, None)
        return w
    if style == "robe":
        w, bot = torso_path(ctx, b, F, sh_y, b["wa"], bulge=1.6)
        _shaded_fill(ctx, col, w, sh_y, bot, F)
        # bare shoulder triangle (near side) and robe fold
        side = -1 if F.s >= 0 else 1
        ctx.save()
        torso_path(ctx, b, F, sh_y, b["wa"], bulge=1.6)
        ctx.clip()
        poly(ctx, [(side * w * 1.1, sh_y - 5), (side * w * 0.2, sh_y - 5), (side * w * 1.1, sh_y + (b["wa"] - sh_y) * 0.55)],
             skin, 2.4)
        curve(ctx, (side * w * 0.25, sh_y), (-side * w * 0.1, (sh_y + b["wa"]) / 2), (-side * w * 0.9, b["wa"] + 10),
              2.2, shade(col, -0.35))
        ctx.restore()
        return w
    w, bot = torso_path(ctx, b, F, sh_y, b["wa"], female=female)
    fill = col
    if top.get("pattern") == "stripes":
        fill = stripe_pattern(col, shade(col, -0.2), 9)
    _shaded_fill(ctx, fill, w, sh_y, bot, F)
    if F.c > 0.1:
        nx = F.x(0, 12)
        if style in ("longsleeve", "shortsleeve", "blouse"):
            line(ctx, [(nx, sh_y + 2), (nx, sh_y + 26)], 2.2, shade(col, -0.45))
            line(ctx, [(nx - 12, sh_y + 2), (nx, sh_y + 10), (nx + 12, sh_y + 2)], 2.2, shade(col, -0.45))
    if style == "armor":
        acc = top.get("accent", GOLD)
        ctx.save()
        torso_path(ctx, b, F, sh_y, b["wa"])
        ctx.clip()
        line(ctx, [(-w * 1.2, sh_y + 8), (w * 1.2, sh_y + 8)], 10, acc)
        line(ctx, [(-w * 1.2, bot - 6), (w * 1.2, bot - 6)], 8, acc)
        circle(ctx, F.x(0, 20), sh_y + 46, 13, acc, 2.2)
        ctx.restore()
        torso_path(ctx, b, F, sh_y, b["wa"])
        fill_stroke(ctx, None)
    if style == "vest":
        pass
    return w


def draw_skirt(ctx, rig, b, F, legs_state, t):
    bottom = rig["bottom"]
    bstyle = bottom.get("style")
    if bstyle not in ("sampot", "robe_skirt", "long_sampot", "sarong", "dancer"):
        if rig["top"].get("style") != "robe":
            return
        bstyle = "robe_skirt"
        col = rig["top"].get("color")
    else:
        col = bottom.get("color")
    w = b["sw"] * (0.74 + 0.26 * abs(F.c)) / 2 * (1.02 if bstyle != "robe_skirt" else 1.12)
    top_y = b["wa"] - 2
    hem = -26 if bstyle != "robe_skirt" else -22
    feet_c = sum(lg["ankle"][0] for lg in legs_state) / 2
    spread = abs(legs_state[0]["ankle"][0] - legs_state[1]["ankle"][0])
    hw = w * 1.05 + spread * 0.25
    sway = math.sin(t * 2.2) * 2
    pts = [(-w, top_y), (w, top_y), (feet_c + hw + sway, hem), (feet_c - hw + sway, hem)]
    fill = col
    if bottom.get("pattern") == "stripes":
        fill = stripe_pattern(col, shade(col, -0.18), 7, vertical=True)
    ctx.new_path()
    ctx.move_to(*pts[0])
    ctx.line_to(*pts[1])
    ctx.curve_to(w + 6, (top_y + hem) / 2, pts[2][0] + 2, hem - 30, pts[2][0], pts[2][1])
    ctx.line_to(*pts[3])
    ctx.curve_to(pts[3][0] - 2, hem - 30, -w - 6, (top_y + hem) / 2, *pts[0])
    ctx.close_path()
    _shaded_fill(ctx, fill, w, top_y, hem, F)
    # fold / pleat
    fx = F.x(0, 14) * 0.6
    line(ctx, [(fx, top_y + 10), (fx + sway * 0.6 + (feet_c * 0.3), hem - 4)], 2.2, shade(col, -0.35))
    if bottom.get("hem"):
        line(ctx, [(feet_c - hw + sway + 3, hem - 7), (feet_c + hw + sway - 3, hem - 7)], 6, bottom["hem"])


def draw_sash(ctx, rig, b, F, w, t):
    sc = rig.get("sash")
    if not sc:
        return
    y = b["wa"] - 2
    h = 18
    ww = w + 5
    ctx.save()
    rrect(ctx, -ww, y - h / 2, ww * 2, h, 6, sc, OL * 0.9)
    ctx.restore()
    if F.c < -0.25:
        return  # knot and tails hang at the front
    kx = F.x(-b["sw"] * 0.18, 18)
    sway = math.sin(t * 2.6) * 3
    for dx, ln in ((-5, 62), (7, 48)):
        poly(ctx, [(kx + dx - 6, y + 4), (kx + dx + 6, y + 4), (kx + dx + 8 + sway, y + ln), (kx + dx - 6 + sway, y + ln - 4)],
             sc, OL * 0.8)
    ellipse(ctx, kx, y, 10, 9, shade(sc, -0.1), OL * 0.8)


def draw_scarf(ctx, rig, b, F, w, t):
    sc = rig.get("scarf")
    if not sc:
        return
    col = sc.get("color", "#b8203a") if isinstance(sc, dict) else sc
    pat = check_pattern(col, "#f4efe6", 7)
    sh_y = b["sh"]
    side = 1 if F.s >= 0 else -1
    if F.c < -0.2:
        side = -side
    x0 = side * w * 0.45
    ln = (b["wa"] - sh_y) + 40
    sway = math.sin(t * 2.0) * 2
    poly(ctx, [(x0 - 15, sh_y - 6), (x0 + 15, sh_y - 6), (x0 + 17 + sway, sh_y + ln), (x0 - 13 + sway, sh_y + ln)],
         pat, OL * 0.8)
    for k in range(4):
        line(ctx, [(x0 - 12 + k * 8 + sway, sh_y + ln), (x0 - 12 + k * 8 + sway, sh_y + ln + 8)], 2.0, col)
    rrect(ctx, -w * 0.75, sh_y - 10, w * 1.5, 16, 7, pat, OL * 0.8)


def draw_necklace(ctx, rig, b, F):
    if "necklace" not in rig.get("jewelry", []) or F.c < -0.1:
        return
    sh = b["sh"]
    cx = F.x(0, 14)
    curve(ctx, (cx - 26, sh + 2), (cx, sh + 34), (cx + 26, sh + 2), 3.5, GOLD)
    poly(ctx, [(cx, sh + 18), (cx + 7, sh + 27), (cx, sh + 37), (cx - 7, sh + 27)], GOLD, 1.6)


# --------------------------------------------------------------------------- props

def draw_prop(ctx, kind, hand, other, F, b, t, layer):
    """layer: 'back' (behind the arm) or 'front'."""
    if not kind:
        return
    hx, hy = hand
    d = 1 if F.s >= 0 else -1
    if kind == "cane" and layer == "back":
        line(ctx, [(hx, hy - 8), (hx + 2, -6)], 13, OUTLINE)
        line(ctx, [(hx, hy - 8), (hx + 2, -6)], 6.5, "#7a4b2a")
        curve(ctx, (hx, hy - 6), (hx - d * 4, hy - 26), (hx - d * 22, hy - 16), 7, "#7a4b2a")
    elif kind == "spear" and layer == "back":
        top = (hx + d * 6, hy - 300)
        bot = (hx - d * 2, -4)
        line(ctx, [bot, top], 12, OUTLINE)
        line(ctx, [bot, top], 6, "#6b3f22")
        poly(ctx, [(top[0] - 10, top[1]), (top[0], top[1] - 62), (top[0] + 10, top[1])], "#cfd6dc", 2.4)
        poly(ctx, [(top[0] - 9, top[1] + 4), (top[0] + 9, top[1] + 4), (top[0] + 12, top[1] + 46), (top[0] - 12, top[1] + 46)],
             "#d22a2f", 2.0)
    elif kind == "sword" and layer == "front":
        ang = -0.9 * d
        tip = (hx + math.sin(-ang) * 120 * d * -1, hy - math.cos(ang) * 120)
        line(ctx, [(hx, hy), tip], 12, OUTLINE)
        line(ctx, [(hx, hy), tip], 7, "#dfe5ea")
        line(ctx, [(hx - 12, hy + 2), (hx + 12, hy - 2)], 7, GOLD)
    elif kind == "hoe" and layer == "back":
        a = (hx - d * 70, hy + 40)
        bnd = (hx + d * 75, hy - 50)
        line(ctx, [a, bnd], 14, OUTLINE)
        line(ctx, [a, bnd], 8, "#7a4b2a")
        poly(ctx, [(a[0], a[1] - 8), (a[0] - d * 10, a[1] - 60), (a[0] - d * 34, a[1] - 40), (a[0] - d * 6, a[1] + 12)],
             "#9aa3ab", 2.4)
    elif kind == "alms_bowl" and layer == "front":
        mx = (hx + other[0]) / 2
        my = (hy + other[1]) / 2 - 18
        ctx.new_path()
        ctx.move_to(mx - 34, my - 6)
        ctx.curve_to(mx - 36, my + 40, mx + 36, my + 40, mx + 34, my - 6)
        ctx.close_path()
        fill_stroke(ctx, "#2b2b2b")
        ellipse(ctx, mx, my - 6, 34, 9, "#1a1a1a", 2.4)
        curve(ctx, (mx - 22, my + 4), (mx - 16, my + 18), (mx - 4, my + 22), 3, "#ffffff", 0.25)
    elif kind in ("basket", "rice_basket", "lotus_basket", "fruit_basket") and layer == "front":
        mx, my = hx + d * 6, hy - 10
        ctx.new_path()
        ctx.move_to(mx - 50, my - 18)
        ctx.curve_to(mx - 46, my + 36, mx + 46, my + 36, mx + 50, my - 18)
        ctx.close_path()
        fill_stroke(ctx, "#c99a55")
        for k in range(-3, 4):
            line(ctx, [(mx + k * 13, my - 16), (mx + k * 10, my + 22)], 1.5, "#8e6532")
        if kind in ("lotus_basket", "fruit_basket", "basket"):
            for k, cc in enumerate(["#3f9a3a", "#58b347", "#3f9a3a"]):
                ellipse(ctx, mx - 26 + k * 26, my - 24, 18, 10, cc, 2.0, rot=0.5 - k * 0.5)
        if kind == "lotus_basket":
            flower(ctx, mx + 6, my - 30, 13, "#f07fb6", "#f7d23e", 1.4)
        if kind == "fruit_basket":
            for k in range(3):
                circle(ctx, mx - 18 + k * 18, my - 26, 10, ["#f2a531", "#e4542e", "#f6d23a"][k], 2)
        if kind == "rice_basket":
            ellipse(ctx, mx, my - 20, 44, 12, "#f7f3e8", 2.0)
        ellipse(ctx, mx, my - 18, 50, 10, "#b5853f", 2.6)
    elif kind == "fish_trap" and layer == "front":
        mx, my = hx + d * 28, hy
        ctx.new_path()
        ctx.move_to(mx - 16, my - 26)
        ctx.curve_to(mx - 46, my + 40, mx - 40, my + 120, mx, my + 128)
        ctx.curve_to(mx + 40, my + 120, mx + 46, my + 40, mx + 16, my - 26)
        ctx.close_path()
        ctx.save()
        src(ctx, "#d9b77a", 0.35)
        ctx.fill_preserve()
        ctx.restore()
        fill_stroke(ctx, None, 3)
        for k in range(1, 6):
            yy = my - 20 + k * 24
            line(ctx, [(mx - 34, yy), (mx + 34, yy)], 1.8, "#8a6534")
        for k in range(-3, 4):
            line(ctx, [(mx + k * 4, my - 24), (mx + k * 11, my + 122)], 1.4, "#8a6534")
    elif kind in ("box", "pot", "bundle", "water_jar", "book", "rice_sack", "gift") and layer == "front":
        mx = (hx + other[0]) / 2
        my = (hy + other[1]) / 2 - 22
        if kind == "pot" or kind == "water_jar":
            blob(ctx, [(mx - 30, my - 30), (mx + 30, my - 30), (mx + 44, my + 10), (mx + 24, my + 40), (mx - 24, my + 40),
                       (mx - 44, my + 10)], "#b8643a")
            ellipse(ctx, mx, my - 30, 22, 7, "#7d3e22", 2.2)
        elif kind == "book":
            rrect(ctx, mx - 28, my - 20, 56, 40, 4, "#2f6fb2")
            line(ctx, [(mx, my - 20), (mx, my + 20)], 2, "#ffffff")
        elif kind == "rice_sack":
            blob(ctx, [(mx - 36, my - 34), (mx + 36, my - 34), (mx + 42, my + 30), (mx - 42, my + 30)], "#efe6cf")
            line(ctx, [(mx - 30, my - 28), (mx + 30, my - 28)], 3, "#9b8a63")
        elif kind == "bundle":
            blob(ctx, [(mx - 36, my - 10), (mx, my - 36), (mx + 36, my - 10), (mx + 30, my + 28), (mx - 30, my + 28)],
                 check_pattern("#2a5fa8", "#f4efe6", 7))
        else:
            rrect(ctx, mx - 38, my - 34, 76, 62, 6, "#c58b4e" if kind == "box" else "#d8333a")
            if kind == "gift":
                line(ctx, [(mx, my - 34), (mx, my + 28)], 6, GOLD)
    elif kind == "flower" and layer == "front":
        flower(ctx, hx, hy - 16, 12, "#f07fb6")
    elif kind == "lantern" and layer == "front":
        line(ctx, [(hx, hy), (hx, hy + 30)], 2)
        rrect(ctx, hx - 16, hy + 28, 32, 40, 8, "#f5b23a")
        ctx.save()
        ctx.set_source(rad := __import__("drawutil").rad_grad(hx, hy + 48, 0, 70, [(0, (1, 0.9, 0.5, 0.45)), (1, (1, 0.8, 0.3, 0))]))
        ctx.arc(hx, hy + 48, 70, 0, 2 * math.pi)
        ctx.fill()
        ctx.restore()


# --------------------------------------------------------------------------- main

def _lerp3(a, b, k):
    return tuple(lerp(a[i], b[i], k) for i in range(3))


def resolve_pose(rig, b, st):
    t = st.get("t", 0.0)
    talk = st.get("talk", 0.0)
    p1 = pose_targets(st.get("pose", "stand"), b, t, talk)
    if st.get("pose_from") and st.get("pose_k", 1.0) < 1.0:
        p0 = pose_targets(st["pose_from"], b, t, talk)
        k = smooth(st["pose_k"])
        out = dict(p1)
        for key in ("near", "far"):
            out[key] = _lerp3(p0[key], p1[key], k)
        for key in ("lean", "head_dy", "head_tilt", "bounce", "shake"):
            out[key] = lerp(p0[key], p1[key], k)
        return out
    return p1


def draw_character(ctx, character, st, x, y, scale, alpha=1.0):
    """Draw one character. character: bible entry (needs 'rig'). st: per-frame state dict:
    theta, pose, pose_from, pose_k, legs (stand|walk|run|sit|kneel), phase, expr, blink,
    viseme, mouth_open, talk, t, look, prop (override), carry (object kind), head_turn."""
    rig = character["_rig"] if "_rig" in character else merge_rig(character.get("rig"))
    b = dict(BUILDS.get(rig.get("build", "adult_m"), BUILDS["adult_m"]))
    theta = st.get("theta", 30.0)
    F = Frame(theta)
    t = st.get("t", 0.0)
    legs = st.get("legs", "stand")
    P = resolve_pose(rig, b, st)

    ctx.save()
    if alpha < 1.0:
        ctx.push_group()
    ctx.translate(x, y)
    ctx.scale(scale, scale)

    # contact shadow
    ctx.new_path()
    ellipse_path(ctx, 0, -2, b["sw"] * 0.62, 13)
    ctx.set_source_rgba(0, 0, 0, 0.13)
    ctx.fill()

    breathe = math.sin(t * 2.1 + zlib.crc32(character.get("character_id", "").encode()) % 7) * 1.4
    bob = 0.0
    if legs in ("walk", "run"):
        bob = -abs(math.sin(st.get("phase", 0.0))) * (5 if legs == "walk" else 10)
    shake = P.get("shake", 0.0)
    sx = math.sin(t * 40) * shake

    sit = legs in ("sit", "kneel")
    sit_drop = 0.0
    if sit:
        sit_drop = (-b["hip"] - 30) if legs == "sit" else (-b["hip"]) * 0.45
    ctx.translate(sx, sit_drop)

    legs_state = _leg_state(b, "stand" if sit else legs, st.get("phase", 0.0), F, 0)

    # --- lower body
    if legs == "sit":
        bc = rig["bottom"].get("color") if rig["top"].get("style") != "robe" else rig["top"].get("color")
        ellipse(ctx, F.s * 10, b["hip"] + 2, b["sw"] * 0.78, 30, bc)
        for side in (-1, 1):
            ellipse(ctx, side * b["sw"] * 0.55 + F.s * 10, b["hip"] + 18, 20, 9, rig.get("skin", SKIN), OL * 0.8)
    elif legs == "kneel":
        bc = rig["bottom"].get("color") if rig["top"].get("style") != "robe" else rig["top"].get("color")
        blob(ctx, [(-b["sw"] * 0.42, b["hip"] - 6), (b["sw"] * 0.42, b["hip"] - 6), (b["sw"] * 0.55 + F.s * 30, b["hip"] + 46),
                   (-b["sw"] * 0.55 + F.s * 30, b["hip"] + 46)], bc)
    else:
        for lg in sorted(legs_state, key=lambda l: l["depth"]):
            draw_leg(ctx, rig, b, lg, F)
        draw_skirt(ctx, rig, b, F, legs_state, t)

    # --- upper body (lean pivot at hips)
    lean = P.get("lean", 0.0) + b.get("stoop", 0) + (8 if legs == "run" else 0)
    ctx.save()
    ctx.translate(0, b["hip"] + bob - P.get("bounce", 0.0))
    ang = math.radians(lean) * F.s
    ctx.rotate(ang)
    squash = 1 - (1 - math.cos(math.radians(lean))) * abs(F.c)
    ctx.scale(1, squash * (1 + breathe * 0.002))
    ctx.translate(0, -b["hip"])

    # arms
    arms = []
    # "near" = lead arm on the side the character faces (gestures, held props)
    near_L = 1 if F.s > 0.05 else (-1 if F.s < -0.05 else 1)
    phase = st.get("phase", 0.0)
    for role, L in (("near", near_L), ("far", -near_L)):
        lat_out, fwd, dy = P[role]
        if legs in ("walk", "run") and st.get("pose", "stand") in ("stand", "walk", "run", "idle"):
            amp = 26 if legs == "walk" else 46
            sgn = 1 if role == "near" else -1
            fwd = fwd + amp * math.sin(phase) * sgn
            dy = dy - abs(math.sin(phase)) * (6 if legs == "walk" else 18)
            if legs == "run":
                dy -= 30
        lat = L * (b["sw"] / 2 + lat_out)
        shx = F.x(L * b["sw"] / 2 * 0.97, 0)
        shy = b["sh"] + b["aw"] * 0.45
        tx, ty = F.x(lat, fwd), shy + dy
        pref = (-F.s * 0.8 + L * F.c * 0.35 + 0.0001, 0.6)
        el, hd = ik2(shx, shy, tx, ty, b["a1"], b["a2"], pref)
        sh_depth = F.depth(L * b["sw"] / 2, 0)
        hd_depth = F.depth(lat, fwd)
        front = (sh_depth * 0.5 + hd_depth) > -b["sw"] * 0.18 or (abs(F.s) < 0.62 and F.c > 0)
        arms.append(dict(role=role, sh=(shx, shy), el=el, hand=hd, front=front, L=L))
    near = arms[0]
    far = arms[1]

    prop = st.get("prop", rig.get("prop"))
    carry = st.get("carry")
    hold = P.get("hold")

    draw_hair_back(ctx, rig, F.x(0, 0), b["sh"] - b["R"] * 0.95, b["R"], theta + st.get("head_turn", 0),
                   F.c >= 0, b["sh"], b["sw"])
    for a in arms:
        if not a["front"]:
            draw_arm(ctx, rig, b, a, F, False, robe_bare=(a["role"] == "near"))
    if prop in ("cane", "spear", "hoe"):
        draw_prop(ctx, prop, near["hand"], far["hand"], F, b, t, "back")
    w = draw_torso(ctx, rig, b, F)
    draw_scarf(ctx, rig, b, F, w, t)
    draw_necklace(ctx, rig, b, F)
    draw_sash(ctx, rig, b, F, w, t)
    for a in arms:
        if a["front"]:
            draw_arm(ctx, rig, b, a, F, True, robe_bare=(a["role"] == "near"))
    if prop and prop not in ("cane", "spear", "hoe"):
        draw_prop(ctx, prop, near["hand"], far["hand"], F, b, t, "front")
    if carry:
        draw_prop(ctx, carry, near["hand"], far["hand"], F, b, t, "front")

    # head
    R = b["R"]
    hx = F.x(0, 4) + P.get("head_tilt", 0) * 0.3
    hy = b["sh"] - R * 0.95 + P.get("head_dy", 0) + breathe * 0.4
    nod = st.get("nod", 0.0)
    hy += nod
    ctx.save()
    ctx.translate(hx, hy + R)
    ctx.rotate(math.radians(P.get("head_tilt", 0) + math.sin(t * 0.9) * 1.2))
    ctx.translate(-hx, -(hy + R))
    draw_head(ctx, rig, hx, hy, R, theta + st.get("head_turn", 0), st)
    ctx.restore()
    if carry == "basket_head" or hold == "carry_head":
        draw_prop(ctx, carry or "fruit_basket", (hx, hy - R * 1.05), (hx, hy - R * 1.05), F, b, t, "front")
    ctx.restore()  # lean

    if alpha < 1.0:
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(alpha)
    ctx.restore()


def character_height(character):
    rig = merge_rig(character.get("rig"))
    b = BUILDS.get(rig.get("build", "adult_m"), BUILDS["adult_m"])
    return -b["sh"] + b["R"] * 1.95


def head_center(character, x, y, scale):
    """Head centre and radius in the parent coordinate system (for camera framing)."""
    rig = merge_rig(character.get("rig"))
    b = BUILDS.get(rig.get("build", "adult_m"), BUILDS["adult_m"])
    return x, y + (b["sh"] - b["R"] * 0.95) * scale, b["R"] * scale
