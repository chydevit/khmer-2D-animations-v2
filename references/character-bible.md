# Character bible (characters/character_bible.json)

The bible is the single source of truth for how every character looks and sounds. The renderer
draws characters only from it, so a character cannot drift between shots.

## Contents
1. File layout
2. Character entry (human-readable fields + `rig`)
3. Rig reference (build, hair, top, bottom, sash, scarf, headwear, jewelry, props)
4. Voice profiles
5. Designing a new character from a story

## 1. File layout

```json
{
  "style": "Locked Khmer chibi style from source/reference_character.png ...",
  "characters": [ {character}, ... ],
  "voices": [ {voice profile}, ... ]
}
```
`assets/reference_cast.json` holds 12 ready-made characters that copy the reference sheet:
man_green, woman_gold, boy, girl, grandpa, grandma, monk, soldier, princess, farmer, fisher, market_woman.
`kh2d.py init --cast boy,girl,...` copies them into a new project. Rename them and change their colours
freely; each `rig` block works as a template.

## 2. Character entry

Fill in **all** the human-readable fields (the skill spec requires them), plus `rig`:

```json
{"character_id": "boy", "name": "Vibol", "name_km": "វិបុល", "age": 9, "gender": "male", "role": "child",
 "height": "child", "body_shape": "small", "skin_tone": "#FED06F", "hair_style": "short", "hair_color": "black",
 "eye_style": "black dot", "top": "cream short-sleeve shirt", "bottom": "brown trousers", "shoes": "sandals",
 "scarf": "red waist sash", "jewelry": "none", "headwear": "none", "props": "none", "special_mark": "none",
 "personality": "curious, brave", "default_expression": "happy", "voice_id": "v_boy", "default_pose": "stand",
 "rig": {"build": "child", "hair": {"style": "short", "color": "#151515"},
         "top": {"style": "shortsleeve", "color": "#F7F0DC"}, "bottom": {"style": "pants", "color": "#7A5236"},
         "sash": "#E8403F"}}
```

## 3. Rig reference

| Key | Values |
|---|---|
| `build` | `adult_m`, `adult_f`, `elder_m`, `elder_f` (slightly stooped), `teen`, `child` |
| `female` | `true` for a female child (`child` build) |
| `skin` | hex colour, default `#FED06F` (the reference skin tone). Keep it for every character unless the story needs otherwise |
| `hair.style` | `short` (side-swept fringe), `bun` (low back bun), `bun_top`, `long`, `shaved` (monk), `none` |
| `hair.color` | `#151515` black, `#AFAFAE` grey |
| `hair.flower` | flower colour in the hair/bun, e.g. `#EC3F86` pink, `#FFFFFF` white |
| `hair.fringe` | `false` = no fringe (elders) |
| `beard` | colour (small goatee) or null |
| `top.style` | `longsleeve`, `shortsleeve`, `blouse`, `none` (shirtless), `wrap` (chest wrap), `sbai` (diagonal shoulder cloth), `royal` (white/gold top), `robe` (monk, one shoulder bare), `armor` (tunic with gold trim) |
| `top.color` / `top.accent` / `top.pattern` | colour, trim colour, `stripes` |
| `bottom.style` | `pants` (cropped), `longpants`, `chang_kben` (baggy wrapped trousers), `shorts`, `sampot` (ankle-length wrap skirt), `robe` |
| `bottom.color` / `bottom.pattern` / `bottom.hem` | colour, `stripes`, hem trim colour |
| `sash` | waist sash colour (red `#E8403F` is the classic) or null |
| `scarf` | `{"color": "#B3263E"}` red checked krama over the shoulder |
| `headwear` | `conical_hat`, `mokot`/`crown` (tall royal crown), `helmet`, `tiara`, `krama_head`, `headband`, or `{"type": ..., "color": ...}` |
| `jewelry` | list from `earrings`, `necklace`, `bracelets`, `anklets` |
| `shoes` | `sandals`, `barefoot` |
| `prop` | always-held prop: `cane`, `spear`, `hoe`, `alms_bowl`, `lotus_basket`, `fruit_basket`, `basket`, `fish_trap`, `sword`, `flower`, `lantern` |

Royalty: a king is `adult_m` + `top.style: royal` or `armor` with a gold accent + `headwear: mokot` + jewelry.
A queen is `adult_f` + `royal` + `sampot` with a gold hem + `tiara`/`mokot` + full jewelry.

**Costume changes**: if the story requires a costume change, create a second character entry
(`dara_wedding`) with the same name, build, hair and skin, and note it in `special_mark`. Never edit the
original mid-story. The continuity check lists costume variants.

## 4. Voice profiles

```json
{"voice_id": "v_boy", "character_id": "boy", "gender": "male", "age": 9, "pitch": "very_high",
 "speed": "medium", "energy": "medium", "emotion": "happy", "accent": "Khmer (Phnom Penh)",
 "engine": "voxcpm",
 "design": "A cheerful young Cambodian boy about nine years old, bright high youthful voice",
 "sample_text": "សួស្តី ខ្ញុំរីករាយណាស់ដែលបានជួបអ្នក។ ...", "seed": 1321,
 "sample_reference": null, "sample_reference_text": null,
 "clone_mode": "ref", "cfg": 2.0, "steps": 10}
```
- `kh2d.py bible` adds a sensible profile for every character that lacks one, plus the narrator.
- `design` is the VoxCPM2 voice-design prompt, written in English. It sets the voice's age, gender, timbre and pace.
- `speed`: `very_slow | slow | medium | fast`, or a number. It is applied after synthesis without changing pitch.
- `sample_reference`: the path to a **human recording** of this character (a 5–15 s wav or mp3), with
  `sample_reference_text` as its exact Khmer transcript. The profile then clones that real voice instead of a designed one.
- `engine: "edge"` uses Microsoft edge-tts instead (it has only 2 Khmer voices; `edge_voice`,
  `edge_pitch` like `+20Hz` and `edge_rate` like `-8%` tell characters apart).
- Children sound lighter and younger, elders slower, monks calm and respectful, royalty confident and formal.
  The presets in `scripts/voices.py` (`DESIGN_PRESETS`) already follow this.

## 5. Designing a new character from a story

1. Read the whole story. List every speaking or recurring character with age, role and status.
2. Pick the closest reference_cast entry as a template and change only colours and accessories.
   Main characters should be easy to tell apart at a glance: give each a different top colour, and a
   different hair or headwear where you can.
3. Be accurate to Cambodian culture: monks wear saffron robes with a shaved head and no jewelry. Farmers
   wear the krama and a conical hat or headband. Elders wear a krama scarf and plain colours. Royalty wears
   gold, a mokot and jewelry. Women wear a sampot.
4. Run `kh2d.py sheets` and look at `characters/sheets/_cast_lineup.png` plus each turnaround before going further.
