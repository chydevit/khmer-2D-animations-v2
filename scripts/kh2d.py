#!/usr/bin/env python3
"""Khmer 2D animation pipeline CLI.

  kh2d.py init <project> [--title T] [--title-km T] [--cast man_green,girl,...]
  kh2d.py bible <project>            fill missing voice profiles, validate the bible
  kh2d.py sheets <project>           character sheets (turnaround, expressions, poses, thumbnails)
  kh2d.py voices <project>           create + lock one reference voice per voice_id
  kh2d.py dialogue <project>         synthesise every line (cached), build lip-sync
  kh2d.py plan <project>             timeline + scene list, shot list, storyboard frames
  kh2d.py stills <project> <t|shot_id[@t]> ...
  kh2d.py audio <project>            sfx + ambience + music + mix
  kh2d.py subs <project>             subtitles_km.srt / subtitles_en.srt
  kh2d.py render <project> [--preview] [--workers N] [--no-burn] [--range a-b]
  kh2d.py qc <project>               continuity_check.md + audio_check.txt
  kh2d.py export <project> [--formats vertical,square]
  kh2d.py all <project> [--preview-only]
Options for voices/dialogue/all: --engine voxcpm|edge, --force-voice <id|all>
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import project as PJ  # noqa: E402

REF_IMG = os.path.join(PJ.SKILL_DIR, "assets", "reference_character.png")
REF_CAST = os.path.join(PJ.SKILL_DIR, "assets", "reference_cast.json")


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------- steps

def cmd_init(a):
    p = PJ.P(a.project)
    p.ensure()
    if not os.path.exists(p("source", "reference_character.png")):
        shutil.copy(a.reference or REF_IMG, p("source", "reference_character.png"))
    if not os.path.exists(p("characters", "character_bible.json")):
        cast = PJ.load_json(REF_CAST)["characters"]
        ids = [x.strip() for x in (a.cast or "").split(",") if x.strip()]
        chosen = [c for c in cast if c["character_id"] in ids] if ids else []
        import voices as V
        bible = {"style": "Locked Khmer chibi style from source/reference_character.png: large round heads, small "
                          "black dot eyes, no nose, clean black outlines, warm yellow skin (#FED06F), simple bodies, "
                          "Khmer traditional clothing.",
                 "characters": chosen,
                 "voices": [V.default_profile(c) for c in chosen] + [V.narrator_profile()]}
        PJ.save_json(p("characters", "character_bible.json"), bible)
    if not os.path.exists(p("story.json")):
        story = {"title": a.title or "Untitled", "title_km": a.title_km or "", "language": "km", "fps": 24,
                 "resolution": [1920, 1080], "subtitles": {"km": True, "en": True, "burn": True},
                 "narrator": {"voice_id": "v_narrator"}, "scenes": []}
        PJ.save_json(p("story.json"), story)
    log("project ready: %s" % p.root)
    log("  edit story.json and characters/character_bible.json, then run: kh2d.py all %s" % a.project)


def cmd_bible(a):
    import voices as V
    p = PJ.P(a.project)
    bible = PJ.load_json(p("characters", "character_bible.json"))
    story = PJ.load_json(p("story.json"))
    have = {v["voice_id"] for v in bible.get("voices", [])}
    added = []
    for c in bible.get("characters", []):
        if not c.get("voice_id"):
            c["voice_id"] = "v_" + c["character_id"]
        if c["voice_id"] not in have:
            bible.setdefault("voices", []).append(V.default_profile(c))
            have.add(c["voice_id"])
            added.append(c["voice_id"])
    nv = (story.get("narrator") or {}).get("voice_id", "v_narrator")
    if nv not in have and _story_has_narration(story):
        bible.setdefault("voices", []).append(V.narrator_profile(nv))
        added.append(nv)
    # check: no two characters share a voice id
    seen = {}
    for c in bible.get("characters", []):
        if c["voice_id"] in seen:
            log("  WARNING %s and %s share voice %s" % (seen[c["voice_id"]], c["character_id"], c["voice_id"]))
        seen[c["voice_id"]] = c["character_id"]
    import rig
    for c in bible.get("characters", []):
        r = rig.merge_rig(c.get("rig"))
        if r["build"] not in rig.BUILDS:
            log("  ERROR %s: unknown build %s" % (c["character_id"], r["build"]))
        for k in ("default_pose",):
            if c.get(k) and c[k] not in rig.POSES:
                log("  WARNING %s: unknown %s %s" % (c["character_id"], k, c[k]))
    PJ.save_json(p("characters", "character_bible.json"), bible)
    log("bible ok: %d characters, %d voices%s" % (len(bible.get("characters", [])), len(bible.get("voices", [])),
                                                 (" (added %s)" % ", ".join(added)) if added else ""))


def _story_has_narration(story):
    return any("narrate" in b for sc in story.get("scenes", []) for sh in sc.get("shots", []) for b in sh.get("beats", []))


def cmd_sheets(a):
    import sheets
    p, story, bible, chars, voices = PJ.load_project(a.project)
    only = set(a.only.split(",")) if getattr(a, "only", None) else None
    lst = [c for c in chars.values() if not only or c["character_id"] in only]
    paths = sheets.build_all(lst, p("characters"))
    log("sheets: %d files in %s" % (len(paths), p("characters")))


def cmd_voices(a):
    import voices as V
    p, story, bible, chars, voices = PJ.load_project(a.project)
    force = None
    if a.force_voice:
        force = "all" if a.force_voice == "all" else set(a.force_voice.split(","))
    prof = V.ensure_voices(p, bible, log, force=force, engine=a.engine)
    for vid, pr in prof.items():
        log("  %-14s %-8s %s" % (vid, pr.get("engine"), pr.get("ref_wav") or "(edge-tts, no clip)"))
    return prof


def cmd_dialogue(a):
    import voices as V
    p, story, bible, chars, voices = PJ.load_project(a.project)
    prof = V.ensure_voices(p, bible, log, engine=a.engine, defer=True)
    lines = PJ.extract_lines(story, chars)
    log("dialogue: %d lines" % len(lines))
    info = V.synth_lines(p, lines, prof, log, engine=a.engine)
    tot = sum(v["dur"] for v in info.values())
    log("dialogue done: %.1f s of speech" % tot)
    return info


def _line_info(p, story, chars):
    path = p("build", "line_info.json")
    info = PJ.load_json(path) if os.path.exists(path) else {}
    for ln in PJ.extract_lines(story, chars):
        if ln["id"] not in info:
            info[ln["id"]] = {"dur": max(1.2, len(ln["km"] or "") / 9.0), "estimated": True}
    return info


def _timeline(a):
    p, story, bible, chars, voices = PJ.load_project(a.project)
    info = _line_info(p, story, chars)
    T = PJ.compile_timeline(story, chars, info)
    PJ.save_json(p("build", "timeline.json"), T)
    return p, story, bible, chars, info, T


def _renderer(p, story, chars, T, scale=1.0, burn=None):
    import render as R
    import subtitles as SUB
    cues = SUB.build_cues(T)
    subs = story.get("subtitles", {})
    langs = tuple(l for l in ("km", "en") if subs.get(l, True))
    burn = subs.get("burn", True) if burn is None else burn
    return R.Renderer(T, chars, p("build", "text"), cues, burn, langs, scale), cues


def cmd_plan(a):
    import docs
    p, story, bible, chars, info, T = _timeline(a)
    est = [k for k, v in info.items() if v.get("estimated")]
    if est:
        log("  NOTE %d line durations are estimates (run 'dialogue' for real timing)" % len(est))
    docs.scene_list(p, story, T)
    docs.shot_list(p, story, T)
    r, cues = _renderer(p, story, chars, T, 0.5)
    docs.storyboard(p, story, T, r)
    log("plan: %d shots, %.1f s -> docs/scene_list.md, docs/shot_list.md, storyboard/" % (len(T["shots"]), T["duration"]))


def cmd_stills(a):
    p, story, bible, chars, info, T = _timeline(a)
    r, _ = _renderer(p, story, chars, T, 1.0)
    out = p("build", "stills")
    os.makedirs(out, exist_ok=True)
    paths = []
    for spec in a.times:
        if spec[0].isdigit() and "_" not in spec:
            t = float(spec)
        else:
            sid, _, off = spec.partition("@")
            sh = [s for s in T["shots"] if s["id"] == sid]
            if not sh:
                log("  unknown shot %s" % sid)
                continue
            t = sh[0]["start"] + (float(off) if off else sh[0]["dur"] / 2)
        fp = os.path.join(out, "still_%07.2f.png" % t)
        r.still(t, fp)
        paths.append(fp)
        log("  %s" % fp)
    if len(paths) > 1:
        grid = os.path.join(out, "grid.png")
        n = len(paths)
        cols = 3 if n > 4 else 2
        inputs = sum([["-i", x] for x in paths], [])
        rows = (n + cols - 1) // cols
        layout = "|".join("%d_%d" % ((i % cols) * 640, (i // cols) * 360) for i in range(n))
        fc = "".join("[%d]scale=640:360[s%d];" % (i, i) for i in range(n)) + "".join("[s%d]" % i for i in range(n)) + \
            "xstack=inputs=%d:layout=%s:fill=black" % (n, layout)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + inputs + ["-filter_complex", fc, grid], check=True)
        log("  grid: %s" % grid)


def cmd_audio(a):
    import mix
    p, story, bible, chars, info, T = _timeline(a)
    if any(v.get("estimated") for v in info.values()):
        raise SystemExit("run the 'dialogue' step first (some lines have no audio yet)")
    path, stats = mix.build_mix(p, T, info, story.get("levels"), log)
    PJ.save_json(p("build", "audio_stats.json"), stats)
    log("audio: %s  (dialogue %.1f dBFS, music under speech %s dBFS)" % (
        path, stats["dialogue_rms_db"], "%.1f" % stats["music_under_speech_db"] if stats["music_under_speech_db"] else "-"))


def cmd_subs(a):
    import subtitles as SUB
    p, story, bible, chars, info, T = _timeline(a)
    cues = SUB.build_cues(T)
    n1 = SUB.write_srt(cues, p("subtitles", "subtitles_km.srt"), "km")
    n2 = SUB.write_srt(cues, p("subtitles", "subtitles_en.srt"), "en")
    log("subtitles: %d Khmer, %d English cues" % (n1, n2))


def cmd_render(a):
    import render as R
    p, story, bible, chars, info, T = _timeline(a)
    preview = a.preview
    scale = 0.5 if preview else 1.0
    import subtitles as SUB
    cues = SUB.build_cues(T)
    subs = story.get("subtitles", {})
    langs = tuple(l for l in ("km", "en") if subs.get(l, True))
    burn = subs.get("burn", True) and not a.no_burn
    vid = p("build", "video_preview.mp4" if preview else "video_master.mp4")
    workers = a.workers or max(1, (os.cpu_count() or 4) - 2)
    R.render_video(T, chars, p("build", "text"), cues, vid, p("build", "chunks"), burn, langs, scale, workers,
                   crf=23 if preview else 17, log=log)
    out = p("film", "preview.mp4" if preview else "final_movie.mp4")
    mixwav = p("audio", "mix.wav")
    if not os.path.exists(mixwav):
        log("  no audio mix yet; writing silent video")
        shutil.copy(vid, out)
        return out
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", vid, "-i", mixwav]
    srt_km, srt_en = p("subtitles", "subtitles_km.srt"), p("subtitles", "subtitles_en.srt")
    soft = [x for x in (srt_km, srt_en) if os.path.exists(x)] if not preview else []
    for s in soft:
        cmd += ["-i", s]
    cmd += ["-map", "0:v", "-map", "1:a"]
    for i in range(len(soft)):
        cmd += ["-map", "%d:s" % (2 + i)]
    cmd += ["-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-ac", "2"]
    if soft:
        cmd += ["-c:s", "mov_text"]
        for i, s in enumerate(soft):
            lang = "khm" if s.endswith("_km.srt") else "eng"
            cmd += ["-metadata:s:s:%d" % i, "language=%s" % lang]
    cmd += ["-t", "%.3f" % T["duration"], "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    log("render: %s" % out)
    return out


def cmd_qc(a):
    import docs
    import subtitles as SUB
    p, story, bible, chars, info, T = _timeline(a)
    cues = SUB.build_cues(T)
    profiles = PJ.load_json(p("audio", "voices", "voice_profiles.json")) if os.path.exists(
        p("audio", "voices", "voice_profiles.json")) else {}
    pr1 = docs.continuity(p, story, T, chars, cues, info, profiles)
    stats = PJ.load_json(p("build", "audio_stats.json")) if os.path.exists(p("build", "audio_stats.json")) else None
    pr2 = []
    if stats:
        final = p("film", "final_movie.mp4")
        pr2 = docs.audio_check(p, story, T, info, profiles, chars, stats, final if os.path.exists(final) else None)
    log("qc: %d continuity problem(s), %d audio problem(s) -> docs/continuity_check.md, docs/audio_check.txt" % (
        len(pr1), len(pr2)))
    for x in pr1 + pr2:
        log("  - " + x)


def cmd_export(a):
    p = PJ.P(a.project)
    src = p("film", "final_movie.mp4")
    if not os.path.exists(src):
        raise SystemExit("render the final movie first")
    fm = (a.formats or "vertical,square").split(",")
    for f in fm:
        if f == "vertical":
            w, h, out = 1080, 1920, p("film", "final_movie_9x16.mp4")
        elif f == "square":
            w, h, out = 1080, 1080, p("film", "final_movie_1x1.mp4")
        else:
            continue
        fc = ("[0:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=24:2,eq=brightness=-0.08[bg];"
              "[0:v]scale=%d:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2" % (w, h, w, h, w))
        if f == "square":
            fc = ("[0:v]scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080,boxblur=24:2,"
                  "eq=brightness=-0.08[bg];[0:v]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-filter_complex", fc, "-c:v", "libx264",
                        "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags",
                        "+faststart", out], check=True)
        log("export: %s" % out)


def cmd_all(a):
    cmd_bible(a)
    cmd_sheets(a)
    cmd_dialogue(a)  # designs/locks missing voices and synthesises lines in one model load
    cmd_plan(a)
    cmd_audio(a)
    cmd_subs(a)
    a.preview = True
    cmd_render(a)
    if not a.preview_only:
        a.preview = False
        cmd_render(a)
        cmd_qc(a)
    else:
        cmd_qc(a)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command")
    ap.add_argument("project")
    ap.add_argument("times", nargs="*")
    ap.add_argument("--title")
    ap.add_argument("--title-km")
    ap.add_argument("--cast")
    ap.add_argument("--reference")
    ap.add_argument("--only")
    ap.add_argument("--engine", choices=["voxcpm", "edge"])
    ap.add_argument("--force-voice")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--preview-only", action="store_true")
    ap.add_argument("--no-burn", action="store_true")
    ap.add_argument("--workers", type=int)
    ap.add_argument("--formats")
    a = ap.parse_args()
    fn = globals().get("cmd_" + a.command)
    if not fn:
        raise SystemExit("unknown command %s" % a.command)
    fn(a)


if __name__ == "__main__":
    main()
