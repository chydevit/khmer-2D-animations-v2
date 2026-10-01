---
name: khmer-2d-animation
description: Khmer 2D Character Animation & Video Builder. Turns a Khmer (or English) story, script, PDF/TXT/DOCX, URL text or historical/educational topic into a finished Cambodian 2D cartoon. The output is an MP4 with locked chibi characters matching the reference sheet, Khmer voices (VoxCPM2, consistent per character), audio-driven Khmer lip-sync, camera moves, SFX, ambience, original Cambodian-inspired music, and Khmer + English subtitles (SRT and burned in). It also produces a character bible, character sheets (turnaround, expressions, poses), storyboard, scene/shot lists and QC reports. Use it whenever the user wants a Cambodian or Khmer cartoon, animation, animated story, folk tale, Jataka, history lesson or kids' video in Khmer. Also use it for Khmer character sheets in this style, or for continuing or editing a project made with it, even if they don't name the skill.
---

# Khmer 2D Character Animation & Video Builder

You are a 2D animation production agent for Khmer/Cambodian cartoons. The locked visual style is
`assets/reference_character.png`: cute chibi figures with large round heads, small black-dot eyes, no nose,
clean black outlines, warm yellow skin (#FED06F), simple bodies and Khmer traditional clothing.
Everything is drawn by code (`scripts/rig.py`, `scripts/backgrounds.py`) in that style. Characters
are vector rigs defined only by the character bible, so face, hair, outfit, proportions and accessories
are identical in every shot by construction. Never describe or render them any other way: no
photorealism, no 3D, no anime.

Skill folder: `~/.claude/skills/khmer-2d-animation` (called `SK` below). All commands:
`SK/.venv/bin/python SK/scripts/kh2d.py <command> <project>`.

## Critical rule: never jump straight to the final movie

Work in this order and show the user the intermediate results (sheets, storyboard, preview) before the
expensive steps:

STORY → CHARACTER BIBLE → CHARACTER SHEETS → VOICES → STORYBOARD → SHOTS → AUDIO → ANIMATION →
LIP-SYNC → SFX/MUSIC → SUBTITLES → QC → FINAL MP4

## Setup (once)

`SK/scripts/setup.sh` checks ffmpeg, cairo, pango and the Khmer font, and builds the two venvs:
`.venv` for rendering and `.venv-vox` for VoxCPM2 with PyTorch/MPS. The ~5 GB model is downloaded on first use.
On this Mac everything is already installed.

## Workflow

### Step 1: analyse the story
- Read the **complete** source first. For PDF/DOCX use the pdf/docx skills or `textutil -convert txt`.
  For URLs, fetch the text. Save the original under `<project>/source/story/`.
- List every character, location, dialogue line and important event. Divide the story into scenes, then
  shots. Do not skip important events, and keep the ending.
- If the source is English, write natural Khmer dialogue and keep the English as the translation line.
  Use the right Khmer register:
  - to elders: លោកតា / លោកយាយ, with the speaker calling themselves ចៅ
  - to monks: ព្រះតេជគុណ, with the speaker calling themselves ខ្ញុំព្រះករុណា / យើងខ្ញុំ; monks call themselves អាត្មា
  - to royalty: ព្រះករុណា / ទូលបង្គំ
  - between friends: ឯង / ខ្ញុំ
- Tell the user that the Khmer should be checked by a native speaker before publishing.

### Step 2: create the project
```
kh2d.py init <project> --title "..." --title-km "..." --cast boy,girl,grandpa,monk
```
`--cast` copies ready-made characters from `assets/reference_cast.json` (12 figures matching the
reference sheet). Leave it out to build the bible by hand. This creates the full output folder structure
(`source/ characters/ backgrounds/ storyboard/ audio/ animation/ subtitles/ docs/ film/`).

### Steps 3–4: character bible + sheets (lock identities)
- Edit `characters/character_bible.json`. Read `references/character-bible.md` for every rig option and
  the required human-readable fields.
- Run `kh2d.py bible <project>` to fill in missing voice profiles and validate. Then run
  `kh2d.py sheets <project>` to write the turnaround (front, 3/4, side, 3/4 back, back), the expression sheet
  (10 expressions), the pose sheet (10 poses) and thumbnails for each character, plus `sheets/_cast_lineup.png`.
- **Look at the lineup and turnarounds** (Read the PNGs). Check that the characters are easy to tell apart and
  culturally right. Fix the bible, re-run, and only then continue. From here on the bible is locked: change
  it only when the user asks.

### Step 5: write story.json (scenes, shots, beats)
Read `references/story-format.md` for the format, all catalogues (poses, expressions, environments,
camera, transitions, music, ambience, SFX, props) and staging patterns. Start from
`assets/example_story.json`. For every scene, fill in purpose, emotion, location, time, music and
ambience. Vary the shot sizes (wide, two-shot, medium, close, reaction). Most shots drift gently by default;
use push_in, pan and track for emphasis. Avoid excessive camera movement.

### Steps 6–9: voices + dialogue (VoxCPM2)
```
kh2d.py voices <project>      # designs + LOCKS one reference clip per voice_id (audio/voices/)
kh2d.py dialogue <project>    # clones every line from its locked clip; builds lip-sync
```
- Every recurring character has exactly one locked voice. A voice is designed once from its
  description and seed, then every line is cloned from that clip, so a voice never changes.
  `--force-voice <id>` redesigns a voice; only do it when the user asks.
- A human recording can replace a designed voice: set `sample_reference` and `sample_reference_text` in the
  bible's voice profile.
- Validate the voices: list them for the user (character → voice description) and suggest they listen to
  `audio/voices/*.wav`. Read `references/voices.md` if a voice sounds wrong or synthesis fails.
- Speed: VoxCPM2 runs on MPS at roughly 5–20 s per line, plus about 1 min to load the model. Run long
  batches in the background. Results are cached, so a rerun only synthesises new or changed lines.
- Fallback: `--engine edge` uses Microsoft edge-tts (needs internet, only 2 Khmer voices).

### Steps 10–14: storyboard, stills, timing
```
kh2d.py plan <project>                 # timeline from real audio, docs/scene_list.md, docs/shot_list.md,
                                       # storyboard/storyboard.md + storyboard_frames/*.png
kh2d.py stills <project> S02_SH01@1.5 S03_SH02 ...   # full-res stills + grid.png
```
Look at the storyboard frames before rendering. Check for:
- a speaker off-screen or cut by the frame
- characters overlapping
- wrong facing (people talking should face each other)
- the subtitle covering a face in close-ups
- the wrong background or time of day

Fix `story.json` and re-run `plan`. This takes seconds; a render takes minutes.

### Steps 15–19: audio + subtitles
```
kh2d.py audio <project>   # SFX (footsteps/cloth automatic) + ambience + music, ducked under speech
kh2d.py subs <project>    # subtitles/subtitles_km.srt + subtitles_en.srt from the final audio timing
```
The audio priority is dialogue > important SFX > ambience > music. Music ducks about 9 dB under speech.
All music and effects are synthesised originals, so there are no copyright issues.

### Steps 20–22: preview, QC, final
```
kh2d.py render <project> --preview   # film/preview.mp4 (960x540), fast
kh2d.py qc <project>                 # docs/continuity_check.md + docs/audio_check.txt
kh2d.py render <project>             # film/final_movie.mp4 1920x1080 H.264 + AAC 48 kHz, -16 LUFS,
                                     # burned Khmer+English subtitles + soft subtitle tracks
kh2d.py export <project> --formats vertical,square   # 1080x1920 and 1080x1080 versions
```
`kh2d.py all <project>` runs every step. Use it only after the bible and storyboard have been reviewed.
Rendering is parallel and cached per chunk, so after an edit only the changed chunks re-render.
On an M1 Pro, the 51 s demo renders in about 10 s (preview) and 25 s (final 1080p), so a 10-minute film takes a few minutes. VoxCPM voice synthesis is the slow step.
Use the Bash tool's `run_in_background` for renders.

Before calling the film done, read `docs/continuity_check.md` and `docs/audio_check.txt`, fix
anything listed under Problems, and extract 3–6 stills from `final_movie.mp4` with ffmpeg to look at the
real output.

## Reporting to the user

Give the user:
- the paths to `film/final_movie.mp4`, `film/preview.mp4`, `subtitles/*.srt`,
  `characters/sheets/_cast_lineup.png`, `storyboard/storyboard.md` and `docs/`
- the runtime, number of scenes and shots, and the voices used
- anything the QC flagged

Be honest about the limitations:
- The voices are AI (VoxCPM2) and may mispronounce some Khmer words.
- Lip-sync is energy and text based (Khmer viseme groups), not phoneme-aligned.
- The Khmer text and English translations need native-speaker review.

## Files

- `scripts/kh2d.py`: the CLI. `project.py`: timeline compiler. `rig.py`: the character rig.
  `backgrounds.py`: 16 environments. `render.py`: camera, frames and encoding. `voices.py` + `tts_vox.py`:
  the voice system. `lipsync.py`: Khmer visemes. `sound.py` + `mix.py`: audio. `subtitles.py`, `docs.py`,
  `sheets.py`, `textrender.py` (pango Khmer shaping).
- `assets/reference_character.png`: the visual source of truth.
  `assets/reference_cast.json`: 12 template characters. `assets/example_story.json`: a complete 4-scene example.
- `references/story-format.md`, `references/character-bible.md`, `references/voices.md`.

## Extending

- **New environment**: add a function to `backgrounds.py` (draw SKY/BG/MG/GROUND/FG in world coordinates,
  x from −520 to 2440, characters stand at y 780–1010) and register it in `ENVIRONMENTS`. Reuse its helpers:
  stilt_house, pagoda, stupa, angkor, sugar_palm, coconut, tree, market_stall, water, boat, lotus, and others.
- **New pose**: add a branch to `rig.pose_targets` (hand targets in body space) and add it to `POSES`.
- **New prop**: add it to `rig.draw_prop`.
- After changing drawing code, cached render chunks are invalidated automatically.
