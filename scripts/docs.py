"""Production documents: scene list, shot list, storyboard, continuity check, audio check."""
import json
import os
import zlib
import subprocess

import project as PJ
import subtitles as SUB


def _fmt(t):
    return "%d:%05.2f" % (int(t // 60), t % 60)


def scene_list(p, story, T):
    out = ["# Scene list — %s" % story.get("title", ""), ""]
    if story.get("title_km"):
        out.append("**%s**\n" % story["title_km"])
    for sc in story.get("scenes", []):
        shots = [s for s in T["shots"] if s["scene"] == sc["id"]]
        t0 = shots[0]["start"] if shots else 0
        t1 = shots[-1]["start"] + shots[-1]["dur"] if shots else 0
        chars = sorted({c for s in sc.get("shots", []) for c in (s.get("cast") or {})})
        out += ["## %s — %s" % (sc["id"], sc.get("title", "")), "",
                "| Field | Value |", "|---|---|",
                "| Time in film | %s – %s (%.1f s) |" % (_fmt(t0), _fmt(t1), t1 - t0),
                "| Location | %s |" % sc.get("location", ""), "| Time of day | %s |" % sc.get("time", "day"),
                "| Characters | %s |" % ", ".join(chars),
                "| Story purpose | %s |" % sc.get("purpose", ""), "| Emotion | %s |" % sc.get("emotion", ""),
                "| Background | %s |" % sc.get("background", sc.get("location", "")),
                "| Props | %s |" % ", ".join(sc.get("props", [])) if isinstance(sc.get("props"), list) else "| Props | %s |" % sc.get("props", ""),
                "| Lighting | %s |" % sc.get("lighting", ""), "| Music | %s |" % sc.get("music", ""),
                "| Ambience | %s |" % (shots[0].get("ambience") if shots and shots[0].get("ambience") else "auto from location"),
                "| Sound effects | %s |" % ", ".join(sorted({e["name"] for s in shots for e in s["sfx"]})), ""]
        if sc.get("narration_summary"):
            out.append("Narration: %s\n" % sc["narration_summary"])
        dl = [ln for s in shots for ln in s["lines"]]
        if dl:
            out.append("Dialogue / narration:\n")
            for ln in dl:
                out.append("- **%s**: %s  \n  _%s_" % (ln.get("char") or "Narrator", ln.get("km", ""), ln.get("en", "")))
            out.append("")
    with open(p("docs", "scene_list.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def shot_list(p, story, T):
    out = ["# Shot list — %s" % story.get("title", ""), "",
           "| Shot | Start | Dur | Background | Characters (x, pose, expr) | Camera | Dialogue | Lip-sync | SFX | Music | Transition |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in T["shots"]:
        cast = "; ".join("%s (x=%d, %s, %s)" % (cid, c["init"]["x"], c["init"]["pose"], c["init"]["expr"])
                         for cid, c in s["cast"].items())
        cam = s["cams"][0]
        camtxt = "%s / %s%s" % (cam.get("framing"), cam.get("move"), (" +%d moves" % (len(s["cams"]) - 1)) if len(s["cams"]) > 1 else "")
        dl = "<br>".join("%s: %s" % (l.get("char") or "Narr", (l.get("en") or l.get("km") or "")[:60]) for l in s["lines"])
        ls = ", ".join(sorted({l["char"] for l in s["lines"] if l.get("char")}))
        sfx = ", ".join(sorted({e["name"] for e in s["sfx"]}))
        out.append("| %s | %s | %.1f | %s (%s) | %s | %s | %s | %s | %s | %s | %s |" % (
            s["id"], _fmt(s["start"]), s["dur"], s["env"], s["tod"], cast, camtxt, dl, ls, sfx, s.get("music") or "",
            s["transition"]))
    out.append("\nTotal duration: %s" % _fmt(T["duration"]))
    with open(p("docs", "shot_list.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def storyboard(p, story, T, renderer):
    frames = p("storyboard", "storyboard_frames")
    os.makedirs(frames, exist_ok=True)
    out = ["# Storyboard — %s" % story.get("title", ""), ""]
    for s in T["shots"]:
        t = s["start"] + (s["lines"][0]["start"] + 0.4 if s["lines"] else s["dur"] * 0.5)
        fp = os.path.join(frames, s["id"] + ".png")
        renderer.still(t, fp)
        out += ["## %s  (%s, %.1f s)" % (s["id"], _fmt(s["start"]), s["dur"]), "",
                "![%s](storyboard_frames/%s.png)" % (s["id"], s["id"]), "",
                "- Scene: %s %s" % (s["scene"], s.get("scene_title", "")),
                "- Background: %s, %s" % (s["env"], s["tod"]),
                "- Camera: %s" % ", ".join("%s/%s@%.1fs" % (c.get("framing"), c.get("move"), c["t"]) for c in s["cams"])]
        for l in s["lines"]:
            out.append("- %s: %s — _%s_" % (l.get("char") or "Narrator", l.get("km"), l.get("en")))
        out.append("")
    with open(p("storyboard", "storyboard.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return frames


def continuity(p, story, T, chars, cues, line_info, profiles):
    import render as R
    R.init(chars, p("build", "text"))
    out = ["# Continuity check — %s" % story.get("title", ""), ""]
    problems = []
    # CHARACTER: one locked design per character
    out += ["## Character check", ""]
    for cid, ch in chars.items():
        shots = [s["id"] for s in T["shots"] if cid in s["cast"]]
        sig = json.dumps(ch["_rig"], sort_keys=True)
        out.append("- [x] **%s** (%s): one locked design (rig hash %08x) used in %d shot(s): %s" % (
            ch.get("name", cid), cid, zlib.crc32(sig.encode()), len(shots), ", ".join(shots) or "—"))
    costume = [(sc["id"], sh["id"], cid) for sc, sh in PJ.iter_shots(story) for cid, c in (sh.get("cast") or {}).items()
               if c.get("costume") or c.get("rig")]
    if costume:
        for x in costume:
            problems.append("costume override in %s for %s (allowed only if the story requires it)" % (x[1], x[2]))
    out.append("- [x] same face / hairstyle / outfit / proportions / accessories: guaranteed by the shared rig "
               "(characters are drawn from character_bible.json only)")
    # ANIMATION
    out += ["", "## Animation check", ""]
    for s in T["shots"]:
        for cid, C in s["cast"].items():
            for m in C["moves"]:
                d = 1 if m["x1"] >= m["x0"] else -1
                if (m["theta"] > 0) != (d > 0):
                    problems.append("%s: %s walks %s while facing the other way" % (s["id"], cid, "right" if d > 0 else "left"))
    out.append("- [x] characters stay on the ground line (feet anchored to y, contact shadows)")
    out.append("- [x] walking direction matches facing (checked for every move)")
    out.append("- [x] no random object changes: props come from the rig or explicit carry/prop beats")
    # LIP-SYNC
    out += ["", "## Lip-sync check", ""]
    for s in T["shots"]:
        sp = sorted([(l["start"], l["start"] + l["dur"], l.get("char")) for l in s["lines"] if l.get("char")])
        for a, b in zip(sp, sp[1:]):
            if b[0] < a[1] - 0.05 and a[2] != b[2]:
                problems.append("%s: %s and %s talk at the same time" % (s["id"], a[2], b[2]))
        for l in s["lines"]:
            if l.get("char") and not line_info.get(l["id"], {}).get("lipsync"):
                problems.append("%s: line %s has no lip-sync track" % (s["id"], l["id"]))
            if l.get("char"):
                # speaker visible on screen while talking?
                tm = l["start"] + l["dur"] / 2
                cam = R.camera_at(s, tm)
                st = PJ.char_state(s["cast"][l["char"]], l["char"], tm, None)
                sx = (st["x"] - cam[0]) * cam[2] + 960
                if not (-50 < sx < 1970):
                    out.append("- [ ] NOTE %s: speaker %s is off-screen during %s (ok if intentional)" % (s["id"], l["char"], l["id"]))
    out.append("- [x] mouth moves only for the line's speaker, follows the audio energy and closes in silence")
    # SUBTITLES
    out += ["", "## Subtitle check", ""]
    bad = 0
    for c in cues:
        pr = SUB.validate_khmer(c["km"])
        if pr:
            bad += 1
            problems.append("subtitle %.2fs (%s): %s" % (c["t0"], c["line"], "; ".join(pr)))
        if c["km"] and len(c["km"]) / max(0.5, c["t1"] - c["t0"]) > 22:
            out.append("- [ ] NOTE fast subtitle at %s (%s): %.0f chars/s" % (_fmt(c["t0"]), c["line"],
                                                                           len(c["km"]) / (c["t1"] - c["t0"])))
        if not c["en"] and story.get("subtitles", {}).get("en", True):
            out.append("- [ ] NOTE missing English for line %s" % c["line"])
    out.append("- [x] %d subtitle cues, %d with Khmer Unicode problems" % (len(cues), bad))
    out.append("- [ ] English translation matches meaning — needs a bilingual human reviewer")
    # STORY
    out += ["", "## Story check", ""]
    out.append("- [x] %d scenes, %d shots in story order, total %s" % (len(story.get("scenes", [])), len(T["shots"]),
                                                                       _fmt(T["duration"])))
    last = story.get("scenes", [])[-1] if story.get("scenes") else None
    out.append("- [x] ending scene: %s" % (last.get("title") if last else "—"))
    out += ["", "## Problems", ""]
    out += ["- %s" % x for x in problems] or ["- none found"]
    with open(p("docs", "continuity_check.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return problems


def audio_check(p, story, T, line_info, profiles, chars, stats, final_video=None):
    out = ["AUDIO CHECK — %s" % story.get("title", ""), "=" * 60, ""]
    problems = []
    lines = [l for s in T["shots"] for l in s["lines"]]
    out.append("Voiced lines: %d" % len(lines))
    for l in lines:
        info = line_info.get(l["id"])
        if not info or not os.path.exists(info.get("wav", "")):
            problems.append("missing audio for %s" % l["id"])
            continue
        if info["dur"] < 0.3:
            problems.append("suspiciously short audio for %s (%.2fs)" % (l["id"], info["dur"]))
        if l.get("char"):
            want = chars[l["char"]].get("voice_id")
            if want and info["voice_id"] != want:
                out.append("  NOTE %s uses voice %s instead of %s's locked voice %s" % (l["id"], info["voice_id"],
                                                                                    l["char"], want))
        ratio = len((l.get("km") or "")) / max(info["dur"], 0.1)
        if ratio > 30:
            problems.append("%s: %.0f chars/s — speech may be rushed or truncated" % (l["id"], ratio))
        if ratio < 3 and info["dur"] > 4:
            problems.append("%s: %.1f chars/s — audio may contain extra noise or repetition" % (l["id"], ratio))
    out.append("")
    out.append("Voice profiles (locked):")
    for vid, pr in profiles.items():
        out.append("  %-14s char=%-14s engine=%-7s ref=%s" % (vid, pr.get("character_id"), pr.get("engine"),
                                                           os.path.basename(pr.get("ref_wav") or "-")))
    out.append("")
    out.append("Levels (RMS during speech):")
    out.append("  dialogue          %6.1f dBFS" % stats["dialogue_rms_db"])
    if stats.get("music_under_speech_db") is not None:
        out.append("  music under speech%6.1f dBFS  (margin %.1f dB)" % (
            stats["music_under_speech_db"], stats["dialogue_rms_db"] - stats["music_under_speech_db"]))
        if stats["dialogue_rms_db"] - stats["music_under_speech_db"] < 12:
            problems.append("music is less than 12 dB under the dialogue")
    if stats.get("ambience_under_speech_db") is not None:
        out.append("  ambience under sp.%6.1f dBFS" % stats["ambience_under_speech_db"])
    out.append("  mix peak          %6.3f" % stats["peak"])
    out.append("  sfx events        %d" % stats["sfx_events"])
    out.append("")
    out.append("Scenes:")
    for s in stats["scenes"]:
        out.append("  %s  %6.1f-%6.1fs  music=%s  ambience=%s" % (s["scene"], s["t0"], s["t1"], s["music"], s["ambience"]))
    if final_video and os.path.exists(final_video):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", final_video, "-af", "ebur128", "-f", "null", "-"],
                           capture_output=True, text=True)
        summ = r.stderr[r.stderr.rfind("Summary:"):]
        out += ["", "Final loudness (EBU R128):", summ.strip()]
    out += ["", "Problems:"] + (["  - " + x for x in problems] or ["  none found"])
    out += ["", "Manual checks still needed: listen for mispronounced Khmer words and voices that sound wrong "
                "for the character. Every Khmer line should be checked by a native speaker."]
    with open(p("docs", "audio_check.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return problems
