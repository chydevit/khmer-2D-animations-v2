"""Audio assembly: dialogue > important SFX > ambience > music, with music ducked under speech."""
import os

import numpy as np
import soundfile as sf

import sound as S

SR = S.SR
LEVELS = {"dialogue": 1.0, "sfx": 0.55, "ambience": 0.20, "music": 0.34, "music_duck": 0.09}


def _db(x):
    return 20 * np.log10(max(x, 1e-9))


def scene_spans(T):
    spans = []
    for sh in T["shots"]:
        if spans and spans[-1]["scene"] == sh["scene"]:
            spans[-1]["t1"] = sh["start"] + sh["dur"]
        else:
            spans.append(dict(scene=sh["scene"], t0=sh["start"], t1=sh["start"] + sh["dur"], music=sh.get("music"),
                              ambience=sh.get("ambience") or ("night" if sh["tod"] == "night" else
                                                              S.AMBIENCE_FOR_ENV.get(sh["env"], "village"))))
    return spans


def build_mix(p, T, line_info, levels=None, log=print):
    L = dict(LEVELS)
    L.update(levels or {})
    n = int((T["duration"] + 0.5) * SR)
    dlg = np.zeros(n)
    sfx = np.zeros((n, 2))
    amb = np.zeros((n, 2))
    mus = np.zeros((n, 2))
    speech = np.zeros(n)
    # dialogue / narration
    for sh in T["shots"]:
        for ln in sh["lines"]:
            info = line_info.get(ln["id"])
            if not info:
                continue
            w, sr = sf.read(info["wav"], dtype="float32")
            t0 = sh["start"] + ln["start"]
            S.place(dlg, w.astype(np.float64), t0)
            s, e = int(t0 * SR), min(n, int((t0 + len(w) / SR) * SR))
            speech[s:e] = 1.0
    # sfx
    sfx_log = []
    for sh in T["shots"]:
        for i, ev in enumerate(sh["sfx"]):
            name = ev["name"]
            try:
                if name == "footstep":
                    x = S.sfx_footstep(ev.get("seed", i), ev.get("surface", "dirt"))
                else:
                    x = S.make_sfx(name, ev.get("seed", i))
            except KeyError as err:
                log("  WARNING %s" % err)
                continue
            t0 = sh["start"] + ev["t"]
            pan = ((ev.get("x", 960) - 960) / 960.0) * 0.6
            gl, gr = np.sqrt(0.5 * (1 - pan)), np.sqrt(0.5 * (1 + pan))
            g = ev.get("gain", 1.0)
            S.place(sfx[:, 0], x, t0, g * gl * 1.41)
            S.place(sfx[:, 1], x, t0, g * gr * 1.41)
            sfx_log.append((round(t0, 2), name))
    # ambience + music per scene, crossfaded
    spans = scene_spans(T)
    xf = 1.5
    for k, sp in enumerate(spans):
        t0 = max(0.0, sp["t0"] - (xf / 2 if k else 0))
        t1 = sp["t1"] + (xf / 2 if k < len(spans) - 1 else 0)
        d = t1 - t0
        a = S.ambience(sp["ambience"], d, seed=k + 3)
        a2 = S.ambience(sp["ambience"], d, seed=k + 103)
        m = S.music(sp["music"], d, seed=k) if sp.get("music") else np.zeros(int(d * SR))
        for arr, buf in (((a, a2), amb), ((m, m), mus)):
            l_, r_ = arr
            fade = np.ones(len(l_))
            fi = int(xf * SR)
            if k:
                fade[:fi] = np.linspace(0, 1, min(fi, len(fade)))[:len(fade[:fi])]
            if k < len(spans) - 1:
                fade[-fi:] = np.minimum(fade[-fi:], np.linspace(1, 0, fi)[-len(fade[-fi:]):])
            S.place(buf[:, 0], l_ * fade, t0)
            S.place(buf[:, 1], r_ * fade, t0)
        sf.write(p("audio", "music", "%s_%s.wav" % (sp["scene"], sp.get("music") or "none")), m.astype(np.float32), SR)
        sf.write(p("audio", "ambience", "%s_%s.wav" % (sp["scene"], sp["ambience"])), a.astype(np.float32), SR)
    # ducking envelope (attack 0.12 s, release 0.6 s)
    env = np.zeros(n)
    att, rel = 1 - np.exp(-1 / (0.12 * SR)), 1 - np.exp(-1 / (0.6 * SR))
    hop = 240
    cur = 0.0
    for i in range(0, n, hop):
        target = speech[i:i + hop].max() if i < n else 0
        k = att if target > cur else rel
        cur += (target - cur) * (1 - (1 - k) ** hop)
        env[i:i + hop] = cur
    mus_gain = L["music"] + (L["music_duck"] - L["music"]) * env
    amb_gain = L["ambience"] * (1 - 0.35 * env)
    out = np.zeros((n, 2))
    out += dlg[:, None] * L["dialogue"]
    out += sfx * L["sfx"]
    out += amb * amb_gain[:, None]
    out += mus * mus_gain[:, None]
    peak = np.max(np.abs(out))
    if peak > 0.98:
        out *= 0.98 / peak
    sf.write(p("audio", "mix.wav"), out.astype(np.float32), SR)
    sf.write(p("audio", "sfx", "sfx_track.wav"), (sfx * L["sfx"]).astype(np.float32), SR)
    sf.write(p("audio", "dialogue_track.wav"), (dlg * L["dialogue"]).astype(np.float32), SR)
    # stats for the audio check
    sp_mask = speech > 0
    def rms(x):
        return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    stats = dict(
        duration=T["duration"],
        dialogue_rms_db=_db(rms(dlg[sp_mask] * L["dialogue"])),
        music_under_speech_db=_db(rms((mus[:, 0] * mus_gain)[sp_mask])) if sp_mask.any() else None,
        ambience_under_speech_db=_db(rms((amb[:, 0] * amb_gain)[sp_mask])) if sp_mask.any() else None,
        music_open_db=_db(rms((mus[:, 0] * mus_gain)[~sp_mask])) if (~sp_mask).any() else None,
        peak=float(np.max(np.abs(out))), sfx_events=len(sfx_log),
        scenes=[dict(scene=s["scene"], music=s.get("music"), ambience=s["ambience"], t0=round(s["t0"], 2),
                     t1=round(s["t1"], 2)) for s in spans])
    return p("audio", "mix.wav"), stats
