"""Project loading, line extraction and timeline compilation/evaluation.

A project folder contains story.json (scenes/shots/beats) and characters/character_bible.json.
The timeline is compiled from the beats plus the real duration of each voiced line.
"""
import json
import math
import os

import lipsync
import rig
from drawutil import ease_io, lerp, smooth

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FACING = {"right": 35, "left": -35, "front": 0, "back": 180, "side_right": 90, "side_left": -90,
          "back_right": 145, "back_left": -145, "3q_right": 35, "3q_left": -35, "front_right": 15,
          "front_left": -15}
GROUND_Y = 935.0
BASE_SCALE = 0.78
WALK_SPEED = 230.0  # world px / s for an adult at BASE_SCALE
RUN_SPEED = 520.0
HEAD_PAD = 0.45
TAIL_PAD = 0.55
LINE_GAP = 0.35
POSE_BLEND = 0.35
TURN_TIME = 0.30


class P:
    """Project paths."""

    def __init__(self, root):
        self.root = os.path.abspath(root)

    def __call__(self, *parts):
        return os.path.join(self.root, *parts)

    def ensure(self):
        for d in ["source/story", "characters/sheets", "characters/expressions", "characters/poses",
                  "characters/thumbnails", "backgrounds", "storyboard/storyboard_frames", "audio/voices",
                  "audio/dialogue", "audio/narration", "audio/music", "audio/ambience", "audio/sfx",
                  "animation/scenes", "animation/shots", "animation/lip_sync", "subtitles", "docs", "film",
                  "build/text", "build/chunks", "build/tts"]:
            os.makedirs(self(d), exist_ok=True)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_project(root):
    p = P(root)
    story = load_json(p("story.json"))
    bible = load_json(p("characters", "character_bible.json"))
    chars = {}
    for c in bible.get("characters", []):
        c = dict(c)
        c["_rig"] = rig.merge_rig(c.get("rig"))
        chars[c["character_id"]] = c
    voices = {v["voice_id"]: v for v in bible.get("voices", [])}
    return p, story, bible, chars, voices


def facing_to_theta(v, default=35.0):
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    return float(FACING.get(str(v), default))


# --------------------------------------------------------------------------- lines

def iter_shots(story):
    for si, sc in enumerate(story.get("scenes", [])):
        sc.setdefault("id", "S%02d" % (si + 1))
        for hi, sh in enumerate(sc.get("shots", [])):
            sh.setdefault("id", "%s_SH%02d" % (sc["id"], hi + 1))
            yield sc, sh


def extract_lines(story, chars):
    """All voiced lines in story order: dict(id, kind, char, voice_id, km, en, shot, scene)."""
    lines = []
    narr_voice = (story.get("narrator") or {}).get("voice_id", "v_narrator")
    for sc, sh in iter_shots(story):
        n = 0
        for b in sh.get("beats", []):
            if "say" in b or "narrate" in b:
                n += 1
                lid = b.get("id") or "%s_L%02d" % (sh["id"], n)
                b["id"] = lid
                if "say" in b:
                    cid = b["say"]
                    if cid not in chars:
                        raise ValueError("shot %s: unknown speaker '%s'" % (sh["id"], cid))
                    voice = b.get("voice_id") or chars[cid].get("voice_id")
                    km = b.get("km") or b.get("text")
                    lines.append(dict(id=lid, kind="dialogue", char=cid, voice_id=voice, km=km, en=b.get("en", ""),
                                      shot=sh["id"], scene=sc["id"], speed=b.get("speed")))
                else:
                    nb = b["narrate"]
                    km = nb if isinstance(nb, str) else nb.get("km")
                    en = b.get("en", "") if isinstance(nb, str) else nb.get("en", b.get("en", ""))
                    lines.append(dict(id=lid, kind="narration", char=None, voice_id=b.get("voice_id", narr_voice),
                                      km=km, en=en, shot=sh["id"], scene=sc["id"], speed=b.get("speed")))
    return lines


# --------------------------------------------------------------------------- compile

def _char_scale(ch, cast):
    depth = float(cast.get("depth", 0.0))
    return float(cast.get("scale", BASE_SCALE)) * (1 - 0.28 * depth)


def _char_y(cast):
    return GROUND_Y - 120.0 * float(cast.get("depth", 0.0))


def compile_timeline(story, chars, line_info):
    """line_info: {line_id: {"dur": seconds, "lipsync": path}}. Returns timeline dict."""
    fps = int(story.get("fps", 24))
    shots = []
    gt = 0.0
    for sc, sh in iter_shots(story):
        env = sh.get("background") or sc.get("location") or "village"
        tod = sh.get("time") or sc.get("time") or "day"
        cast = {}
        for cid, c in (sh.get("cast") or {}).items():
            if cid not in chars:
                raise ValueError("shot %s: unknown character '%s' in cast" % (sh["id"], cid))
            ch = chars[cid]
            c = dict(c)
            st = dict(x=float(c.get("x", 960)), y=_char_y(c), scale=_char_scale(ch, c),
                      theta=facing_to_theta(c.get("facing"), 35.0),
                      pose=c.get("pose") or ch.get("default_pose", "stand"),
                      expr=c.get("expr") or ch.get("default_expression", "neutral"),
                      legs=c.get("legs", "stand"), carry=c.get("carry"), prop=c.get("prop", "__default__"),
                      alpha=1.0 if c.get("visible", True) else 0.0)
            if st["expr"] not in rig.EXPRESSIONS:
                st["expr"] = "neutral"
            cast[cid] = dict(init=st, ev=[], moves=[], speech=[])
        lines, sfx, cams, cards = [], [], [], []
        cur = float(sh.get("head_pad", HEAD_PAD))
        prev_start = cur
        cur_pose = {cid: c["init"]["pose"] for cid, c in cast.items()}
        cur_x = {cid: c["init"]["x"] for cid, c in cast.items()}
        cur_theta = {cid: c["init"]["theta"] for cid, c in cast.items()}
        for b in sh.get("beats", []):
            start = prev_start if b.get("with") else cur + float(b.get("delay", 0.0))
            dur = 0.0
            if "say" in b or "narrate" in b:
                info = line_info.get(b["id"], {})
                dur = float(info.get("dur", 2.0))
                cid = b.get("say")
                lines.append(dict(id=b["id"], char=cid, start=start, dur=dur, km=b.get("km") or (
                    b["narrate"] if isinstance(b.get("narrate"), str) else (b.get("narrate") or {}).get("km")),
                    en=b.get("en") or ((b.get("narrate") or {}).get("en") if isinstance(b.get("narrate"), dict) else ""),
                    lipsync=info.get("lipsync")))
                if cid:
                    if cid not in cast:
                        raise ValueError("shot %s: speaker '%s' is not in the shot's cast" % (sh["id"], cid))
                    C = cast[cid]
                    C["speech"].append(dict(t0=start, t1=start + dur, line=b["id"], lipsync=info.get("lipsync")))
                    if b.get("expr"):
                        C["ev"].append(dict(t=start, k="expr", v=b["expr"]))
                    if b.get("to") and b["to"] in cast:
                        th = 35.0 if cur_x[b["to"]] >= cur_x[cid] else -35.0
                        C["ev"].append(dict(t=max(0.0, start - 0.25), k="theta", v=th))
                        cur_theta[cid] = th
                    if b.get("pose"):
                        C["ev"].append(dict(t=start, k="pose", v=b["pose"]))
                        if b.get("then_pose", True) is not False and b["pose"] in ("talk", "explain", "point", "wave"):
                            back = b.get("then_pose") if isinstance(b.get("then_pose"), str) else cur_pose[cid]
                            C["ev"].append(dict(t=start + dur + 0.1, k="pose", v=back))
                        else:
                            cur_pose[cid] = b["pose"]
                    elif cur_pose[cid] in ("stand", "idle") and b.get("gesture", True):
                        C["ev"].append(dict(t=start, k="pose", v="talk"))
                        C["ev"].append(dict(t=start + dur + 0.1, k="pose", v=cur_pose[cid]))
                    if b.get("then_expr"):
                        C["ev"].append(dict(t=start + dur + 0.1, k="expr", v=b["then_expr"]))
                if b.get("sfx"):
                    sfx.append(dict(name=b["sfx"], t=start + float(b.get("sfx_at", 0.0))))
                if not b.get("async"):
                    cur = start + dur + float(b.get("gap", LINE_GAP))
            elif "act" in b or "do" in b:
                cid = b.get("act") or b.get("do")
                if cid not in cast:
                    raise ValueError("shot %s: act on '%s' which is not in the cast" % (sh["id"], cid))
                C = cast[cid]
                dur = float(b.get("dur", 0.6))
                for k in ("pose", "expr", "legs", "carry", "prop"):
                    if k in b:
                        C["ev"].append(dict(t=start, k=k, v=b[k]))
                        if k == "pose":
                            cur_pose[cid] = b[k]
                        if k == "pose" and b[k] in ("bow", "sampeah", "sampeah_high", "give", "pick_up"):
                            sfx.append(dict(name="cloth", t=start, gain=0.5, x=cur_x[cid]))
                        if k == "legs" and b[k] in ("sit", "kneel", "stand"):
                            sfx.append(dict(name="cloth", t=start, gain=0.4, x=cur_x[cid]))
                if "emote" in b:
                    C["ev"].append(dict(t=start, k="expr", v=b["emote"]))
                if "facing" in b:
                    th = facing_to_theta(b["facing"])
                    C["ev"].append(dict(t=start, k="theta", v=th))
                    cur_theta[cid] = th
                if "look_at" in b and b["look_at"] in cur_x:
                    th = 35.0 if cur_x[b["look_at"]] >= cur_x[cid] else -35.0
                    C["ev"].append(dict(t=start, k="theta", v=th))
                    cur_theta[cid] = th
                if "nod" in b:
                    C["ev"].append(dict(t=start, k="nod", v=float(b.get("nod") or 1)))
                    dur = max(dur, 0.6) if "dur" not in b else dur
                for key, mode in (("walk_to", "walk"), ("run_to", "run"), ("enter", "walk"), ("exit", "walk")):
                    if key not in b:
                        continue
                    x0 = cur_x[cid]
                    if key == "enter":
                        side = b["enter"]
                        x0 = -260.0 if side == "left" else 2180.0
                        x1 = float(b.get("to_x", 600 if side == "left" else 1320))
                        C["ev"].append(dict(t=start, k="alpha", v=1.0))
                    elif key == "exit":
                        x1 = -300.0 if b["exit"] == "left" else 2220.0
                    else:
                        x1 = float(b[key])
                    mode = b.get("mode", mode)
                    sc_ = cast[cid]["init"]["scale"] / BASE_SCALE
                    speed = (RUN_SPEED if mode == "run" else WALK_SPEED) * sc_
                    mdur = float(b["dur"]) if "dur" in b else max(0.6, abs(x1 - x0) / speed)
                    d = 1 if x1 >= x0 else -1
                    C["moves"].append(dict(t0=start, t1=start + mdur, x0=x0, x1=x1, mode=mode,
                                           theta=float(b.get("walk_facing", 72 * d))))
                    end_th = facing_to_theta(b.get("end_facing"), 35.0 * d)
                    C["ev"].append(dict(t=start + mdur, k="theta", v=end_th, frm=float(b.get("walk_facing", 72 * d))))
                    cur_theta[cid] = end_th
                    cur_x[cid] = x1
                    if key == "exit":
                        C["ev"].append(dict(t=start + mdur, k="alpha", v=0.0))
                    dur = mdur
                    # footsteps on every step
                    stride_t = (95.0 * cast[cid]["init"]["scale"] * (1.6 if mode == "run" else 1.0)) / speed
                    tt = start + stride_t * 0.5
                    i = 0
                    surface = sh.get("surface") or ("wood" if env in ("house_interior",) else
                                                    "stone" if env in ("temple", "palace", "palace_hall", "angkor", "town") else "dirt")
                    while tt < start + mdur:
                        sfx.append(dict(name="footstep", t=tt, gain=0.55 if mode == "walk" else 0.8, seed=i,
                                        surface=surface, x=lerp(x0, x1, (tt - start) / mdur)))
                        tt += stride_t
                        i += 1
                if b.get("sfx"):
                    sfx.append(dict(name=b["sfx"], t=start + float(b.get("sfx_at", 0.0)), x=cur_x[cid]))
                if not b.get("async") and not b.get("with"):
                    cur = start + dur
                elif b.get("with"):
                    cur = max(cur, start + dur)
            elif "wait" in b:
                dur = float(b["wait"])
                cur = start + dur
            elif "sfx" in b:
                sfx.append(dict(name=b["sfx"], t=start, gain=float(b.get("gain", 1.0))))
            elif "camera" in b:
                cam = dict(b["camera"]) if isinstance(b["camera"], dict) else {"framing": b["camera"]}
                cam["t"] = start
                cams.append(cam)
            elif "card" in b or "title" in b:
                cd = b.get("card") or b.get("title")
                dur = float(b.get("dur", 3.0))
                cards.append(dict(t0=start, t1=start + dur, km=cd.get("km", "") if isinstance(cd, dict) else cd,
                                  en=cd.get("en", "") if isinstance(cd, dict) else "", style=b.get("style", "title")))
                if not b.get("async"):
                    cur = start + dur
            prev_start = start
        dur = max(cur + float(sh.get("tail_pad", TAIL_PAD)), float(sh.get("min_duration", 0.0)))
        if sh.get("duration"):
            dur = float(sh["duration"])
        for c in cast.values():
            c["ev"].sort(key=lambda e: e["t"])
        base_cam = dict(framing=sh.get("framing", "wide"), subject=sh.get("subject"), move=sh.get("move", "drift"),
                        focus=sh.get("focus"), zoom=sh.get("zoom"), t=0.0)
        shots.append(dict(id=sh["id"], scene=sc["id"], scene_title=sc.get("title", ""), env=env, tod=tod,
                          start=gt, dur=dur, cast=cast, lines=lines, sfx=sfx, cams=[base_cam] + cams, cards=cards,
                          transition=sh.get("transition", "cut"), transition_dur=float(sh.get("transition_dur", 0.6)),
                          music=sc.get("music"), ambience=sc.get("ambience"), fps=fps))
        gt += dur
    return dict(fps=fps, duration=gt, shots=shots, title=story.get("title", ""), title_km=story.get("title_km", ""))


# --------------------------------------------------------------------------- evaluate

_LIPSYNC_CACHE = {}


def _lipsync(path):
    if not path:
        return None
    if path not in _LIPSYNC_CACHE:
        try:
            _LIPSYNC_CACHE[path] = load_json(path)
        except OSError:
            _LIPSYNC_CACHE[path] = None
    return _LIPSYNC_CACHE[path]


def _blink(cid, t):
    import zlib
    seed = zlib.crc32(cid.encode()) % 1000
    period = 3.2 + (seed % 17) / 10.0
    ph = (t + seed * 0.37) % period
    return ph < 0.13


def char_state(C, cid, t, ch):
    init = C["init"]
    st = dict(init)
    st["t"] = t
    if st.get("prop") == "__default__":
        st.pop("prop")
    last = {}
    prev = {}
    for e in C["ev"]:
        if e["t"] > t:
            break
        if e["k"] in last:
            prev[e["k"]] = last[e["k"]]
        last[e["k"]] = e
    for k in ("expr", "legs", "carry", "prop"):
        if k in last:
            if k == "prop" and last[k]["v"] == "__default__":
                st.pop("prop", None)
            else:
                st[k] = last[k]["v"]
    if "pose" in last:
        e = last["pose"]
        frm = prev["pose"]["v"] if "pose" in prev else init["pose"]
        st["pose"] = e["v"]
        k = (t - e["t"]) / POSE_BLEND
        if k < 1.0 and frm != e["v"]:
            st["pose_from"] = frm
            st["pose_k"] = k
    if "theta" in last:
        e = last["theta"]
        frm = e.get("frm", prev["theta"]["v"] if "theta" in prev else init["theta"])
        st["theta"] = lerp(frm, e["v"], ease_io((t - e["t"]) / TURN_TIME))
    if "alpha" in last:
        st["alpha"] = last["alpha"]["v"]
    if "nod" in last:
        dt = t - last["nod"]["t"]
        if dt < 0.6:
            st["nod"] = math.sin(dt / 0.6 * math.pi) * 9 * last["nod"]["v"]
    # moves
    x = init["x"]
    for m in C["moves"]:
        if t < m["t0"]:
            break
        if t >= m["t1"]:
            x = m["x1"]
            continue
        k = (t - m["t0"]) / max(1e-6, m["t1"] - m["t0"])
        # gentle ease at the ends of a walk
        kk = k if 0.08 < k < 0.92 else (smooth(k / 0.16) * 0.08 if k <= 0.08 else 1 - smooth((1 - k) / 0.16) * 0.08)
        x = lerp(m["x0"], m["x1"], kk)
        dist = abs(x - m["x0"])
        stride = 95.0 * init["scale"] * (1.6 if m["mode"] == "run" else 1.0)
        st["legs"] = m["mode"]
        st["phase"] = dist / stride * math.pi
        th0 = st["theta"]
        st["theta"] = lerp(th0, m["theta"], ease_io(min(1.0, (t - m["t0"]) / TURN_TIME)))
        if m["t1"] - t < TURN_TIME:
            st["theta"] = m["theta"]
        if st.get("pose") in ("talk", "explain"):
            st["pose"] = "stand"
        break
    st["x"] = x
    # speech
    st["viseme"], st["mouth_open"], st["talk"] = "rest", 0.0, 0.0
    for s in C["speech"]:
        if s["t0"] <= t < s["t1"] + 0.05:
            tr = _lipsync(s["lipsync"])
            v, o = lipsync.sample(tr, t - s["t0"])
            st["viseme"], st["mouth_open"] = v, o
            st["talk"] = lipsync.talk_amount(tr, t - s["t0"])
            st["nod"] = st.get("nod", 0.0) + math.sin((t - s["t0"]) * 3.1) * 2.0 * st["talk"]
            break
    st["blink"] = _blink(cid, t)
    return st


def shot_at(T, t):
    shots = T["shots"]
    lo, hi = 0, len(shots) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if shots[mid]["start"] <= t:
            lo = mid
        else:
            hi = mid - 1
    return lo
