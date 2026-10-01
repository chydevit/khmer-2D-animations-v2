"""Frame renderer: camera, parallax layers, characters, cards, subtitles, transitions, encoding."""
import math
import os
import subprocess
import sys

import cairocffi as cairo

import backgrounds as BG
import project as PJ
import rig
import textrender as TR
from drawutil import clamp, ease_io, lerp

W, H = 1920, 1080


def _code_version():
    import hashlib
    h = hashlib.sha1()
    d = os.path.dirname(os.path.abspath(__file__))
    for n in ("rig.py", "backgrounds.py", "render.py", "drawutil.py", "project.py", "textrender.py", "lipsync.py"):
        with open(os.path.join(d, n), "rb") as f:
            h.update(f.read())
    return h.hexdigest()[:8]


RENDER_VERSION = _code_version()  # cached chunks are invalidated when drawing code changes


# --------------------------------------------------------------------------- camera

def _subjects(shot, subj, t):
    cast = shot["cast"]
    if not subj:
        ids = [cid for cid, c in cast.items() if c["init"].get("alpha", 1.0) > 0]
    elif isinstance(subj, str):
        ids = [subj]
    else:
        ids = list(subj)
    out = []
    for cid in ids:
        if cid not in cast:
            continue
        C = cast[cid]
        st = PJ.char_state(C, cid, t, None)
        ch = _CHARS[cid]
        hx, hy, hr = rig.head_center(ch, st["x"], st["y"], st["scale"])
        h = rig.character_height(ch) * st["scale"]
        out.append(dict(x=st["x"], y=st["y"], h=h, hx=hx, hy=hy, hr=hr))
    return out


def frame_for(shot, cam, t):
    fr = cam.get("framing", "wide")
    S = _subjects(shot, cam.get("subject"), t)
    if fr == "wide" or not S:
        z, cx, cy = 1.0, 960.0, 540.0
        if cam.get("focus"):
            cx, cy = cam["focus"]
            z = float(cam.get("zoom") or 1.0)
    elif fr == "insert":
        cx, cy = cam.get("focus") or (S[0]["x"], S[0]["y"] - S[0]["h"] * 0.5)
        z = float(cam.get("zoom") or 2.4)
    else:
        xs = [s["x"] for s in S]
        span = max(xs) - min(xs)
        mx = (max(xs) + min(xs)) / 2
        maxh = max(s["h"] for s in S)
        top = min(s["y"] - s["h"] for s in S)
        if fr == "full":
            h = (max(s["y"] for s in S) + maxh * 0.10) - (top - maxh * 0.15)
            z = min(H / h, W / (span + maxh * 1.4))
            cx, cy = mx, (top - maxh * 0.15 + max(s["y"] for s in S) + maxh * 0.10) / 2
        elif fr in ("medium", "two_shot", "group"):
            bottom = max(s["y"] for s in S) - maxh * 0.22
            h = (bottom - (top - maxh * 0.16)) * 1.08
            z = min(H / h, W / (span + maxh * 1.5))
            cx, cy = mx, (top - maxh * 0.16 + bottom) / 2
        elif fr in ("medium_close", "mcu"):
            bottom = max(s["y"] for s in S) - maxh * 0.45
            h = (bottom - (top - maxh * 0.12)) * 1.05
            z = min(H / h, W / (span + maxh * 1.2))
            cx, cy = mx, (top - maxh * 0.12 + bottom) / 2
        elif fr == "close":
            s = S[0]
            z = H / (s["hr"] * 2 * 2.5)
            cx, cy = s["hx"], s["hy"] + s["hr"] * 0.55
        elif fr == "ots":
            # cam.subject = [foreground listener, speaker]
            fg, sp = S[0], S[-1]
            bottom = sp["y"] - sp["h"] * 0.5
            h = bottom - (sp["y"] - sp["h"] - sp["h"] * 0.1)
            z = H / h * 0.92
            cx = sp["x"] + (fg["x"] - sp["x"]) * 0.42
            cy = (sp["y"] - sp["h"] * 1.1 + bottom) / 2
        else:
            z, cx, cy = 1.0, 960.0, 540.0
        if cam.get("zoom"):
            z = float(cam["zoom"])
    return [cx, cy, z]


def camera_at(shot, t):
    cams = shot["cams"]
    idx = 0
    for i, c in enumerate(cams):
        if c["t"] <= t:
            idx = i
    cam = cams[idx]
    seg_t0 = cam["t"]
    seg_t1 = cams[idx + 1]["t"] if idx + 1 < len(cams) else shot["dur"]
    track = cam.get("move") == "track"
    base = frame_for(shot, cam, t if track else seg_t0)
    p = ease_io((t - seg_t0) / max(0.01, seg_t1 - seg_t0))
    cx, cy, z = _apply_move(base, cam.get("move", "drift"), p, t, cam)
    # blend from the previous camera
    bd = float(cam.get("dur", 0.0))
    if idx > 0 and bd > 0 and t - seg_t0 < bd:
        pc = cams[idx - 1]
        pb = frame_for(shot, pc, seg_t0)
        pcx, pcy, pz = _apply_move(pb, pc.get("move", "static"), 1.0, t, pc)
        k = ease_io((t - seg_t0) / bd)
        cx, cy, z = lerp(pcx, cx, k), lerp(pcy, cy, k), math.exp(lerp(math.log(pz), math.log(z), k))
    return _clamp_cam(cx, cy, z)


def _apply_move(base, move, p, t, cam):
    cx, cy, z = base
    amt = float(cam.get("amount", 1.0))
    if move == "drift":
        z *= 1 + 0.035 * p * amt
        cx += 18 * (p - 0.5) * amt
    elif move == "push_in":
        z *= 1 + 0.20 * p * amt
    elif move == "pull_out":
        z *= 1 + 0.20 * (1 - p) * amt
    elif move == "pan_left":
        cx += 140 * (0.5 - p) * 2 * amt / z
    elif move == "pan_right":
        cx += 140 * (p - 0.5) * 2 * amt / z
    elif move == "tilt_up":
        cy += 90 * (0.5 - p) * 2 * amt / z
    elif move == "tilt_down":
        cy += 90 * (p - 0.5) * 2 * amt / z
    elif move == "shake":
        cx += math.sin(t * 37) * 6 * amt
        cy += math.cos(t * 29) * 5 * amt
    return cx, cy, z


def _clamp_cam(cx, cy, z):
    z = clamp(z, 1.0, 6.0)
    hw, hh = W / 2 / z, H / 2 / z
    cx = clamp(cx, BG.X0 + 140 + hw, BG.X1 - 140 - hw) if hw < (BG.X1 - BG.X0 - 280) / 2 else 960
    cy = clamp(cy, hh - 60, 1100 - hh)
    return cx, cy, z


def layer_transform(ctx, cam, f):
    cx, cy, z = cam
    zf = 1 + (z - 1) * f
    cfx = 960 + (cx - 960) * f
    cfy = 540 + (cy - 540) * f
    ctx.translate(W / 2, H / 2)
    ctx.scale(zf, zf)
    ctx.translate(-cfx, -cfy)


# --------------------------------------------------------------------------- frame

_CHARS = {}
_TEXT_DIR = None


def init(chars, text_dir):
    global _TEXT_DIR
    _CHARS.clear()
    _CHARS.update(chars)
    _TEXT_DIR = text_dir


def draw_shot(ctx, shot, t):
    cam = camera_at(shot, t)
    for layer in BG.LAYERS:
        ctx.save()
        layer_transform(ctx, cam, BG.PARALLAX[layer])
        BG.draw_layer(ctx, shot["env"], layer, t + shot["start"], shot["tod"])
        if layer == "GROUND":
            states = []
            for cid, C in shot["cast"].items():
                st = PJ.char_state(C, cid, t, _CHARS[cid])
                if st.get("alpha", 1.0) <= 0.01:
                    continue
                states.append((st["y"], cid, st))
            for _, cid, st in sorted(states, key=lambda s: s[0]):
                rig.draw_character(ctx, _CHARS[cid], st, st["x"], st["y"], st["scale"], st.get("alpha", 1.0))
        ctx.restore()
    BG.apply_tint(ctx, shot["tod"], W, H)
    # soft vignette
    ctx.save()
    g = cairo.RadialGradient(W / 2, H / 2, H * 0.45, W / 2, H / 2, H * 1.05)
    g.add_color_stop_rgba(0, 0, 0, 0, 0)
    g.add_color_stop_rgba(1, 0, 0, 0, 0.22)
    ctx.set_source(g)
    ctx.paint()
    ctx.restore()
    draw_cards(ctx, shot, t)


def draw_cards(ctx, shot, t):
    for cd in shot["cards"]:
        if not (cd["t0"] <= t < cd["t1"]):
            continue
        a = clamp(min((t - cd["t0"]) / 0.5, (cd["t1"] - t) / 0.5), 0, 1)
        style = cd.get("style", "title")
        if style == "title":
            ctx.save()
            ctx.set_source_rgba(0.08, 0.05, 0.03, 0.45 * a)
            ctx.rectangle(0, H * 0.33, W, H * 0.34)
            ctx.fill()
            ctx.restore()
            km = TR.render(cd["km"], 92, _TEXT_DIR, color="#ffe9a8", width_px=1700) if cd["km"] else None
            en = TR.render(cd["en"], 46, _TEXT_DIR, color="#ffffff", width_px=1700) if cd["en"] else None
            y = H * 0.36
            if km:
                TR.draw_outlined(ctx, km, (W - km.get_width()) / 2, y, 5, alpha=a)
                y += km.get_height() + 4
            if en:
                TR.draw_outlined(ctx, en, (W - en.get_width()) / 2, y, 4, alpha=a)
        else:  # caption at the top
            km = TR.render(cd["km"], 48, _TEXT_DIR, width_px=1600) if cd["km"] else None
            en = TR.render(cd["en"], 32, _TEXT_DIR, width_px=1600) if cd["en"] else None
            y = 50
            for s in (km, en):
                if s:
                    TR.draw_outlined(ctx, s, (W - s.get_width()) / 2, y, 4, alpha=a)
                    y += s.get_height()


def draw_subtitles(ctx, cues, t, langs=("km", "en")):
    for c in cues:
        if c["t0"] <= t < c["t1"]:
            surfs = []
            if "km" in langs and c["km"]:
                surfs.append(TR.render("\n".join(TR.wrap_khmer(c["km"])), 50, _TEXT_DIR, width_px=1700))
            if "en" in langs and c["en"]:
                surfs.append(TR.render(c["en"], 36, _TEXT_DIR, color="#fff4c8", width_px=1700, bold=True))
            total = sum(s.get_height() for s in surfs if s)
            y = H - 48 - total
            for s in surfs:
                if s:
                    TR.draw_outlined(ctx, s, (W - s.get_width()) / 2, y, 4)
                    y += s.get_height() - 4
            break


class Renderer:
    def __init__(self, T, chars, text_dir, cues=None, burn_subs=True, sub_langs=("km", "en"), scale=1.0):
        self.T = T
        init(chars, text_dir)
        self.cues = cues or []
        self.burn = burn_subs
        self.langs = sub_langs
        self.scale = scale
        self.w, self.h = int(W * scale), int(H * scale)
        self.surf = cairo.ImageSurface(cairo.FORMAT_RGB24, self.w, self.h)
        self.ctx = cairo.Context(self.surf)
        self.tmp = cairo.ImageSurface(cairo.FORMAT_RGB24, self.w, self.h)
        self.tctx = cairo.Context(self.tmp)

    def _draw(self, ctx, si, t_local):
        ctx.save()
        ctx.scale(self.scale, self.scale)
        draw_shot(ctx, self.T["shots"][si], t_local)
        ctx.restore()

    def frame(self, tg):
        T = self.T
        si = PJ.shot_at(T, tg)
        sh = T["shots"][si]
        tl = tg - sh["start"]
        self._draw(self.ctx, si, tl)
        # transitions (dissolve into this shot / fades)
        tr = sh["transition"]
        d = sh["transition_dur"]
        if tr in ("dissolve", "crossfade") and si > 0 and tl < d / 2:
            prev = T["shots"][si - 1]
            k = 0.5 + tl / d
            self._draw(self.tctx, si - 1, prev["dur"] + tl)
            self.ctx.set_source_surface(self.tmp, 0, 0)
            self.ctx.paint_with_alpha(1 - k)
        if si + 1 < len(T["shots"]):
            nxt = T["shots"][si + 1]
            if nxt["transition"] in ("dissolve", "crossfade") and sh["dur"] - tl < nxt["transition_dur"] / 2:
                k = 0.5 - (sh["dur"] - tl) / nxt["transition_dur"]
                self._draw(self.tctx, si + 1, -(sh["dur"] - tl))
                self.ctx.set_source_surface(self.tmp, 0, 0)
                self.ctx.paint_with_alpha(clamp(k, 0, 1))
        fade = 0.0
        if tr in ("fade", "fade_in", "dip") and tl < d:
            fade = max(fade, 1 - tl / d)
        if si == 0 and tl < 0.6:
            fade = max(fade, 1 - tl / 0.6)
        nxt_tr = T["shots"][si + 1]["transition"] if si + 1 < len(T["shots"]) else "fade_out_end"
        if (nxt_tr in ("fade", "dip") or sh.get("transition_out") == "fade") and sh["dur"] - tl < d:
            fade = max(fade, 1 - (sh["dur"] - tl) / d)
        if si == len(T["shots"]) - 1 and sh["dur"] - tl < 1.0:
            fade = max(fade, 1 - (sh["dur"] - tl) / 1.0)
        if fade > 0:
            self.ctx.set_source_rgba(0, 0, 0, clamp(fade, 0, 1))
            self.ctx.paint()
        if self.burn and self.cues:
            self.ctx.save()
            self.ctx.scale(self.scale, self.scale)
            draw_subtitles(self.ctx, self.cues, tg, self.langs)
            self.ctx.restore()
        self.surf.flush()
        return self.surf

    def still(self, tg, path):
        self.frame(tg).write_to_png(path)


# --------------------------------------------------------------------------- encoding

def encode_chunk(args):
    (T, chars, text_dir, cues, burn, langs, scale, f0, f1, fps, out, crf) = args
    r = Renderer(T, chars, text_dir, cues, burn, langs, scale)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr0", "-s", "%dx%d" % (r.w, r.h),
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
           "-g", str(fps * 2), "-movflags", "+faststart", out + ".tmp.mp4"]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(f0, f1):
        s = r.frame(f / fps)
        p.stdin.write(bytes(s.get_data()))
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed for chunk %s" % out)
    os.replace(out + ".tmp.mp4", out)
    return out


def render_video(T, chars, text_dir, cues, out_path, chunk_dir, burn=True, langs=("km", "en"), scale=1.0,
                 workers=6, crf=18, chunk_frames=240, log=print):
    import multiprocessing as mp
    fps = T["fps"]
    nframes = int(round(T["duration"] * fps))
    os.makedirs(chunk_dir, exist_ok=True)
    jobs = []
    tag = "p" if scale < 1 else "f"
    import hashlib
    import json
    rigs = json.dumps({k: v.get("_rig") for k, v in sorted(chars.items())}, sort_keys=True, default=str)
    for i, f0 in enumerate(range(0, nframes, chunk_frames)):
        f1 = min(nframes, f0 + chunk_frames)
        ta, tb = f0 / fps - 1.0, f1 / fps + 1.0
        sh = [s for s in T["shots"] if s["start"] < tb and s["start"] + s["dur"] > ta]
        cu = [c for c in cues if c["t0"] < tb and c["t1"] > ta]
        sig = hashlib.sha1(json.dumps([sh, cu, burn, list(langs), scale, crf, fps, rigs, RENDER_VERSION],
                                      sort_keys=True, default=str).encode()).hexdigest()[:10]
        out = os.path.join(chunk_dir, "%s_%05d_%d_%d_%s.mp4" % (tag, i, f0, f1, sig))
        jobs.append((T, chars, text_dir, cues, burn, langs, scale, f0, f1, fps, out, crf))
    todo = [j for j in jobs if not os.path.exists(j[10])]
    log("render: %d frames, %d chunks (%d cached), %d workers" % (nframes, len(jobs), len(jobs) - len(todo), workers))
    if todo:
        ctx = mp.get_context("spawn")
        with ctx.Pool(workers) as pool:
            for k, out in enumerate(pool.imap_unordered(encode_chunk, todo)):
                log("  chunk %d/%d done (%s)" % (k + 1, len(todo), os.path.basename(out)))
    lst = os.path.join(chunk_dir, "%s_list.txt" % tag)
    with open(lst, "w") as f:
        for j in jobs:
            f.write("file '%s'\n" % os.path.abspath(j[10]))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                    out_path], check=True)
    return out_path
