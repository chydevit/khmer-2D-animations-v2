"""Khmer voice system: locked voice profiles, VoxCPM2 (default) or edge-tts, line synthesis, lip-sync.

Voice locking: every voice_id gets ONE reference clip (audio/voices/<voice_id>.wav), designed once
from its description + seed (or taken from a human recording given as sample_reference).
Every line of that voice is cloned from that clip, so a character never changes voice.
"""
import asyncio
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

import lipsync
import project as PJ

SR = 48000
VOX_PY = os.path.join(PJ.SKILL_DIR, ".venv-vox", "bin", "python")
VOX_WORKER = os.path.join(PJ.SKILL_DIR, "scripts", "tts_vox.py")
SAMPLE_TEXT = "សួស្តី ខ្ញុំរីករាយណាស់ដែលបានជួបអ្នក។ ថ្ងៃនេះអាកាសធាតុល្អណាស់ ហើយយើងនឹងធ្វើការជាមួយគ្នា។"

DESIGN_PRESETS = {
    "adult_m": "A warm Cambodian man in his thirties, natural friendly mid-pitched voice, clear Khmer pronunciation",
    "adult_f": "A gentle Cambodian woman in her twenties, soft warm voice, clear Khmer pronunciation",
    "elder_m": "An old Cambodian grandfather, slow, low and slightly raspy voice, wise and kind",
    "elder_f": "An old Cambodian grandmother, slow soft voice, warm and caring",
    "child_m": "A cheerful young Cambodian boy about nine years old, bright high youthful voice",
    "child_f": "A sweet little Cambodian girl about eight years old, high clear youthful voice",
    "teen": "An energetic Cambodian teenage boy, light youthful voice",
    "monk": "A calm Buddhist monk, slow, peaceful, respectful low voice",
    "royal_m": "A Khmer king, confident, formal and dignified deep voice",
    "royal_f": "A young Khmer princess, graceful, formal and gentle voice",
    "narrator": "A warm Cambodian storyteller, calm and clear narration voice, medium pace",
}
EDGE_DEFAULT = {"male": "km-KH-PisethNeural", "female": "km-KH-SreymomNeural"}
PITCH_HZ = {"very_low": "-25Hz", "low": "-12Hz", "medium": "+0Hz", "high": "+18Hz", "very_high": "+38Hz"}
SPEED = {"very_slow": 0.82, "slow": 0.9, "medium": 1.0, "normal": 1.0, "fast": 1.08}


def default_profile(ch):
    """Suggest a voice profile for a character from its bible entry."""
    b = (ch.get("rig") or {}).get("build", "adult_m")
    g = (ch.get("gender") or "").lower()
    role = (ch.get("role") or "").lower()
    female = g.startswith("f") or b.endswith("_f") or (ch.get("rig") or {}).get("female")
    if "monk" in role:
        key, pitch, speed = "monk", "low", "slow"
    elif any(k in role for k in ("king", "prince")) and not female:
        key, pitch, speed = "royal_m", "low", "medium"
    elif any(k in role for k in ("queen", "princess")):
        key, pitch, speed = "royal_f", "medium", "medium"
    elif b == "child":
        key, pitch, speed = ("child_f" if female else "child_m"), "very_high", "medium"
    elif b.startswith("elder"):
        key, pitch, speed = ("elder_f" if female else "elder_m"), "low", "slow"
    elif b == "teen":
        key, pitch, speed = "teen", "high", "medium"
    else:
        key, pitch, speed = ("adult_f" if female else "adult_m"), "medium", "medium"
    return {"voice_id": ch.get("voice_id") or "v_" + ch["character_id"], "character_id": ch["character_id"],
            "gender": "female" if female else "male", "age": ch.get("age"), "pitch": pitch, "speed": speed,
            "energy": "medium", "emotion": ch.get("default_expression", "neutral"), "accent": "Khmer (Phnom Penh)",
            "engine": "voxcpm", "design": DESIGN_PRESETS[key], "sample_text": SAMPLE_TEXT,
            "seed": 1000 + sum(map(ord, ch["character_id"])), "sample_reference": None}


def narrator_profile(voice_id="v_narrator", gender="female"):
    return {"voice_id": voice_id, "character_id": None, "gender": gender, "age": 40, "pitch": "medium",
            "speed": "medium", "energy": "calm", "emotion": "warm", "accent": "Khmer (Phnom Penh)",
            "engine": "voxcpm", "design": DESIGN_PRESETS["narrator"], "sample_text": SAMPLE_TEXT, "seed": 777,
            "sample_reference": None}


def _sha(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:12]


def _to_wav(src, dst, sr=SR):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", str(sr), dst], check=True)


def _run_vox(jobs, job_path, log):
    if not os.path.exists(VOX_PY):
        raise RuntimeError("VoxCPM environment missing (%s). Run scripts/setup.sh, or set engine 'edge'." % VOX_PY)
    PJ.save_json(job_path, jobs)
    log("VoxCPM2: %d voice(s), %d line(s) to synthesise (model load ~1 min)..." %
        (len(jobs.get("voices", [])), len(jobs.get("lines", []))))
    p = subprocess.Popen([VOX_PY, VOX_WORKER, job_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in p.stdout:
        line = line.strip()
        if line.startswith("{"):
            log("  " + line)
    err = p.stderr.read()
    if p.wait() != 0:
        raise RuntimeError("VoxCPM worker failed:\n" + err[-3000:])


async def _edge_one(text, voice, rate, pitch, out_mp3):
    import edge_tts
    c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await c.save(out_mp3)


def _edge(text, prof, out_wav):
    voice = prof.get("edge_voice") or EDGE_DEFAULT.get(prof.get("gender", "male"), EDGE_DEFAULT["male"])
    pitch = prof.get("edge_pitch") or PITCH_HZ.get(prof.get("pitch", "medium"), "+0Hz")
    rate = prof.get("edge_rate") or "%+d%%" % int(round((SPEED.get(prof.get("speed", "medium"), 1.0) - 1) * 100))
    mp3 = out_wav[:-4] + ".mp3"
    asyncio.run(_edge_one(text, voice, rate, pitch, mp3))
    _to_wav(mp3, out_wav)
    os.remove(mp3)


def ensure_voices(p, bible, log=print, force=None, engine=None, defer=False):
    """Create/lock the reference clip of every voice profile. Returns {voice_id: profile+ref info}.
    defer=True: don't run VoxCPM now; pending voice jobs are stored in profiles["__pending__"] so the
    caller can run them in the same worker as the lines (one model load)."""
    profiles = {v["voice_id"]: dict(v) for v in bible.get("voices", [])}
    lock_path = p("audio", "voices", "voice_lock.json")
    lock = PJ.load_json(lock_path) if os.path.exists(lock_path) else {}
    jobs = {"voices": [], "lines": []}
    for vid, prof in profiles.items():
        eng = engine or prof.get("engine", "voxcpm")
        prof["engine"] = eng
        ref = p("audio", "voices", vid + ".wav")
        if force and (force == "all" or vid in force) and os.path.exists(ref):
            os.remove(ref)
            lock.pop(vid, None)
        if eng != "voxcpm":
            continue
        if prof.get("sample_reference"):
            srcp = prof["sample_reference"]
            srcp = srcp if os.path.isabs(srcp) else p(srcp)
            if not os.path.exists(ref) or lock.get(vid, {}).get("source") != srcp:
                _to_wav(srcp, ref)
                lock[vid] = {"source": srcp, "text": prof.get("sample_reference_text", ""), "sha": _sha(ref)}
            continue
        if os.path.exists(ref):
            l = lock.get(vid, {})
            if l.get("design") and l.get("design") != prof.get("design"):
                log("  NOTE voice %s is LOCKED; its design text changed but the locked clip is kept. "
                    "Use --force-voice %s to recreate it." % (vid, vid))
            continue
        jobs["voices"].append({"voice_id": vid, "design": prof.get("design") or DESIGN_PRESETS["adult_m"],
                               "sample_text": prof.get("sample_text") or SAMPLE_TEXT, "out_wav": ref,
                               "seed": int(prof.get("seed", 1234))})
    if jobs["voices"] and not defer:
        _run_vox(jobs, p("build", "tts", "voice_jobs.json"), log)
        _lock_new(p, jobs["voices"], lock)
    PJ.save_json(lock_path, lock)
    for vid, prof in profiles.items():
        ref = p("audio", "voices", vid + ".wav")
        pending = defer and any(j["voice_id"] == vid for j in jobs["voices"])
        prof["ref_wav"] = ref if (os.path.exists(ref) or pending) else None
        prof["ref_text"] = lock.get(vid, {}).get("text", prof.get("sample_text", SAMPLE_TEXT))
        prof["ref_sha"] = lock.get(vid, {}).get("sha")
    PJ.save_json(p("audio", "voices", "voice_profiles.json"), profiles)
    if defer:
        profiles["__pending__"] = jobs["voices"]
    return profiles


def _lock_new(p, voice_jobs, lock=None):
    lock_path = p("audio", "voices", "voice_lock.json")
    if lock is None:
        lock = PJ.load_json(lock_path) if os.path.exists(lock_path) else {}
    for j in voice_jobs:
        if os.path.exists(j["out_wav"]):
            lock[j["voice_id"]] = {"design": j["design"], "seed": j["seed"], "text": j["sample_text"],
                                   "sha": _sha(j["out_wav"])}
    PJ.save_json(lock_path, lock)
    return lock


def _clean(text):
    return " ".join((text or "").replace("\n", " ").split())


def _post(raw, dst, speed):
    w, sr = sf.read(raw, dtype="float32", always_2d=False)
    if w.ndim > 1:
        w = w.mean(axis=1)
    tmp = dst + ".tmp.wav"
    sf.write(tmp, w, sr)
    af = ["aresample=%d" % SR]
    if speed and abs(speed - 1.0) > 0.01:
        af.insert(0, "atempo=%.3f" % speed)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-af", ",".join(af), "-ac", "1", dst], check=True)
    os.remove(tmp)
    w, _ = sf.read(dst, dtype="float32")
    voiced = w[np.abs(w) > 0.02]
    rms = np.sqrt(np.mean(voiced ** 2)) if len(voiced) else 0.1
    g = min(10 ** (-18 / 20) / max(rms, 1e-5), 0.97 / max(np.max(np.abs(w)), 1e-5))
    w = np.concatenate([np.zeros(int(0.03 * SR), dtype=np.float32), w * g])
    sf.write(dst, w, SR)
    return len(w) / SR


def synth_lines(p, lines, profiles, log=print, engine=None):
    os.makedirs(p("build", "tts"), exist_ok=True)
    plan = []
    pending = profiles.pop("__pending__", [])
    vox_jobs = {"voices": list(pending), "lines": []}
    for ln in lines:
        vid = ln["voice_id"]
        if vid not in profiles:
            raise ValueError("line %s uses voice '%s' which has no profile in character_bible.json 'voices'" %
                             (ln["id"], vid))
        prof = profiles[vid]
        eng = engine or prof.get("engine", "voxcpm")
        text = _clean(ln["km"])
        if not text:
            raise ValueError("line %s has no Khmer text" % ln["id"])
        key_src = json.dumps([text, vid, eng, prof.get("ref_sha"), prof.get("cfg", 2.0), prof.get("steps", 10),
                              prof.get("clone_mode", "ref"), prof.get("edge_voice"), prof.get("pitch"),
                              prof.get("speed"), ln.get("seed")], ensure_ascii=False)
        key = hashlib.sha1(key_src.encode("utf-8")).hexdigest()[:16]
        raw = p("build", "tts", key + ".wav")
        sub = "dialogue" if ln["kind"] == "dialogue" else "narration"
        dst = p("audio", sub, ln["id"] + ".wav")
        speed = float(ln.get("speed") or SPEED.get(str(prof.get("speed", "medium")), 1.0))
        if eng == "edge":
            speed_post = 1.0  # rate already applied by edge
        else:
            speed_post = speed
        plan.append((ln, raw, dst, speed_post, key))
        if os.path.exists(raw):
            continue
        if eng == "voxcpm":
            if not prof.get("ref_wav"):
                raise RuntimeError("voice %s has no locked reference clip; run the 'voices' step first" % vid)
            vox_jobs["lines"].append({"id": ln["id"], "text": text, "ref_wav": prof["ref_wav"],
                                      "ref_text": prof.get("ref_text", SAMPLE_TEXT), "out_wav": raw,
                                      "seed": int(ln.get("seed") or 7), "cfg": prof.get("cfg", 2.0),
                                      "steps": prof.get("steps", 10), "clone_mode": prof.get("clone_mode", "ref")})
        else:
            log("  edge-tts %s (%s)" % (ln["id"], vid))
            _edge(text, prof, raw)
    if vox_jobs["lines"] or vox_jobs["voices"]:
        _run_vox(vox_jobs, p("build", "tts", "line_jobs.json"), log)
        if pending:
            lock = _lock_new(p, pending)
            for j in pending:
                profiles[j["voice_id"]]["ref_sha"] = lock.get(j["voice_id"], {}).get("sha")
            PJ.save_json(p("audio", "voices", "voice_profiles.json"), profiles)
    info = {}
    for ln, raw, dst, speed, key in plan:
        stamp = dst + ".key"
        if not (os.path.exists(dst) and os.path.exists(stamp) and open(stamp).read() == "%s|%s" % (key, speed)):
            _post(raw, dst, speed)
            with open(stamp, "w") as f:
                f.write("%s|%s" % (key, speed))
        w, sr = sf.read(dst, dtype="float32")
        ls_path = p("animation", "lip_sync", ln["id"] + ".json")
        if ln["kind"] == "dialogue":
            tr = lipsync.build_track(ln["km"], w, sr)
            tr["line"] = ln["id"]
            tr["char"] = ln["char"]
            PJ.save_json(ls_path, tr)
        info[ln["id"]] = {"dur": round(len(w) / sr, 3), "wav": dst, "voice_id": ln["voice_id"],
                          "lipsync": ls_path if ln["kind"] == "dialogue" else None, "kind": ln["kind"],
                          "char": ln["char"]}
    PJ.save_json(p("build", "line_info.json"), info)
    return info
