# story.json format

`story.json` is the production script: scenes → shots → beats. Beats run one after another; the
timeline is computed from the **real audio length** of every voiced line, so you never type
dialogue timings.

## Contents
1. Top level
2. Scenes
3. Shots (cast, camera, transitions)
4. Beats (say, narrate, act, wait, sfx, camera, title/card)
5. Catalogues: poses, expressions, facing, environments, music, ambience, SFX, props
6. Patterns that work

## 1. Top level

```json
{
  "title": "The Lotus Offering", "title_km": "ផ្កាឈូកថ្វាយវត្ត",
  "language": "km", "fps": 24, "resolution": [1920, 1080],
  "subtitles": {"km": true, "en": true, "burn": true},
  "narrator": {"voice_id": "v_narrator"},
  "levels": {"music": 0.34, "music_duck": 0.09, "ambience": 0.20, "sfx": 0.55},
  "scenes": [ ... ]
}
```
`burn: true` draws subtitles into the picture; the SRT files are always written and also muxed as
soft subtitle tracks into `final_movie.mp4`.

## 2. Scenes

```json
{"id": "S01", "title": "Morning in the village", "location": "village", "time": "morning",
 "purpose": "...", "emotion": "...", "props": ["cane"], "lighting": "soft morning sun",
 "music": "opening", "ambience": "village", "shots": [ ... ]}
```
`location` = default background for its shots. `time`: `morning | day | evening | night`.
`ambience` defaults from the location (night → crickets). The descriptive fields
(purpose, emotion, props, lighting) feed `docs/scene_list.md`.

## 3. Shots

```json
{"id": "S01_SH02", "background": "village", "time": "morning",
 "framing": "two_shot", "subject": ["boy", "grandpa"], "move": "push_in",
 "transition": "dissolve", "transition_dur": 0.8, "min_duration": 3,
 "cast": {
   "boy":     {"x": 820,  "facing": "right", "pose": "stand", "expr": "happy"},
   "grandpa": {"x": 1250, "facing": "left",  "pose": "hold_staff", "expr": "calm", "depth": 0}
 },
 "beats": [ ... ]}
```

**cast** (state at the start of the shot; repeat it in every shot, since shots do not inherit):
- `x`: 0–1920 world pixels (the stage is 1920 wide; −260 / 2180 are just off-screen).
- `depth`: 0 = front line (y 935), 1 = further back (smaller, higher). Use 0–1.
- `facing`: see §5. `pose`, `expr`, `legs` (`stand | sit | kneel`), `carry` (object in hands),
  `prop` (override the bible prop; `null` removes it), `visible: false` (for characters who enter later),
  `scale` (default 0.78).

**Camera**: `framing`: `wide | full | medium | medium_close | close | two_shot | ots | insert`.
- `subject`: a character id or a list of ids (default: the whole cast). For `ots`, use `[foreground, speaker]`.
- `insert` uses `focus: [x, y]` and `zoom`.
- `move`: `static | drift | push_in | pull_out | pan_left | pan_right | tilt_up | tilt_down | track | shake`.
  The default is `drift`, a slow gentle move, so no shot is ever fully static.
- `amount` scales the move, and `zoom` overrides the zoom.

**transition** (into this shot): `cut | dissolve | fade` (fade = dip to black). `transition_dur` sets its length.
The film always fades in at the start and fades out at the end.

## 4. Beats

| Beat | Example | Notes |
|---|---|---|
| say | `{"say": "boy", "km": "ជម្រាបសួរ លោកតា!", "en": "Good morning, Grandpa!", "expr": "happy", "pose": "point", "to": "grandpa"}` | Voiced with the character's locked voice; lip-sync and gestures follow the audio. With no `pose`, a standing speaker uses `talk` gestures (`"gesture": false` turns this off). `pose` talk/point/wave/explain reverts after the line (set `then_pose` to choose the pose it returns to). `to` turns the speaker toward someone. `then_expr` sets the expression after the line. |
| narrate | `{"narrate": "នៅភូមិមួយ...", "en": "In a village..."}` | Narrator voice, with no lip-sync. |
| act | `{"act": "boy", "walk_to": 900}` | Keys: `pose`, `expr`/`emote`, `facing`, `look_at`, `legs`, `carry`, `prop`, `nod`, `walk_to`, `run_to`, `enter: "left"/"right"` (+`to_x`), `exit`, `end_facing`, `dur`, `sfx`. Footsteps are added automatically for every step. |
| wait | `{"wait": 1.0}` | Pause. |
| sfx | `{"sfx": "temple_bell", "gain": 0.8}` | Plays at that point; doesn't take time. |
| camera | `{"camera": {"framing": "close", "subject": "grandpa", "move": "push_in", "dur": 0.8}}` | Camera change within the shot; `dur` > 0 blends from the previous framing. |
| title / card | `{"title": {"km": "...", "en": "..."}, "dur": 3}` | A centred title card. `"style": "caption"` puts it at the top instead. |

Timing modifiers on any beat:
- `"with": true` starts the beat together with the previous one (e.g. two people bowing).
- `"async": true` starts the beat at the cursor without waiting for it (e.g. one person walks while the next beat begins).
- `"delay": 0.3` adds a small delay.
- `"gap": 0.6` sets the pause after a line (default 0.35 s).

## 5. Catalogues

- **Facing**: `right` (3/4 right), `left`, `front`, `back`, `side_right`, `side_left`, `back_right`,
  `back_left`, `front_right`, `front_left`, or any angle in degrees (0 = front, 90 = profile right, 180 = back).
- **Poses**: stand, clasp, sampeah, sampeah_high (to monks and royalty), bow, point, talk,
  explain, wave, think, afraid, cry, laugh, angry, arms_crossed, carry, carry_head, hold_bowl,
  give, pick_up, shoulder_tool, hold_staff, hip_basket, dance, work (hoe cycle), fight
  (thrust cycle), sit_hands (with `legs: sit`).
- **Legs**: stand, walk, run (set automatically by walk_to/run_to), sit (cross-legged on the floor), kneel.
- **Expressions**: neutral, happy, smile, sad, angry, afraid, surprised, laughing, crying, thinking,
  worried, calm, determined, shy.
- **Environments**: village, rice_field, rice_field_harvest, farm, forest, temple, market, palace,
  palace_hall, river, pond, mountain, house_interior, angkor, school, town.
  Each one is drawn in layers (SKY, BG, MG, GROUND, FG) with parallax. Combine them with `time` for lighting.
- **Music moods** (original, synthesised, Cambodian-inspired): opening, happy, playful, calm, sad,
  danger, tension, royal, temple, ending, none.
- **Ambience**: village, forest, temple, market, farm, palace, river, pond, night, interior, town,
  rain, battle, none.
- **SFX**: footstep (automatic), whoosh, cloth (automatic on bows and sitting), bell, temple_bell, gong, chime,
  sparkle, thud, basket, tool_hit, hoe, clang, sword, swish, splash, water, door, pop, boing, bird,
  chicken, cow, horse, crowd_gasp, gasp, magic, drum.
- **Carry / props**: cane, spear, sword, hoe, alms_bowl, basket, rice_basket, lotus_basket,
  fruit_basket, fish_trap, box, pot, water_jar, bundle, book, rice_sack, gift, flower, lantern.

## 6. Patterns that work

- **Establish, then cover**: wide establishing shot → two_shot → medium or close on the speaker → reaction close-up.
- **Shot length**: keep each shot to 1–3 lines. Cut to a new shot rather than piling up camera beats.
- **Respect**: when children greet an elder, have them `sampeah` before speaking. With monks, use
  `legs: kneel` + `sampeah_high`. Monks keep `hold_bowl` and the `calm` expression.
- **Entering**: give the character `visible: false` in the cast and an `act ... enter` beat
  (`"with": true` lets it overlap the narration).
- **Recurring characters**: repeat the same cast entry (the same x and facing) in the next shot to keep continuity.
  Changing sides breaks the 180° rule, so keep each speaker on the same side of the screen throughout a scene.
- **Spacing**: about 350–450 px between two adults talking, and 250 px for children.
- **Pauses**: add `{"wait": 0.5–1.0}` before emotional reactions, so the beat can land.
