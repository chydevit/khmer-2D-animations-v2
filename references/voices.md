# Khmer voices (VoxCPM2)

## How it works
- Engine: **VoxCPM2** (openbmb/VoxCPM2, open-source, 2B parameters, 48 kHz). It runs locally in
  `SK/.venv-vox` on Apple MPS and supports 30 languages, Khmer included. Website: https://voxcpm.com/en/
- **Voice design**: the voice is created from an English description in parentheses before the text, e.g.
  `(A sweet little Cambodian girl about eight years old, high clear youthful voice)សួស្តី...`.
  The design is used only **once per voice**, to make the reference clip `audio/voices/<voice_id>.wav`.
- **Cloning**: every line is generated with `reference_wav_path=<that clip>` (`clone_mode: "ref"`), which keeps the
  same timbre for that character throughout the film. Other modes:
  - `"prompt"` (continuation; faster, but copies the prompt's prosody)
  - `"both"` (strongest similarity, slowest)
- `audio/voices/voice_lock.json` records the design text, seed and checksum of each locked clip. Changing the
  design text later does **not** change a locked voice. Use `kh2d.py voices <p> --force-voice <id>` to redesign it.
- The cache key for every line is text + voice + settings, so rerunning `dialogue` only synthesises new or changed lines.

## Timing
On an M1 Pro (16 GB): model load is about 60–70 s, and each line takes about 5–20 s (roughly 4–8× real time).
A 10-minute film with about 150 lines takes about 30–45 minutes. Run it in the background.

## When a voice sounds wrong
- **Wrong age or gender**: edit the profile's `design` (be explicit: "elderly man, about seventy, low slow voice"),
  then run `--force-voice <id>`. You can also try another `seed`.
- **Rushed**: set `speed: "slow"` (0.9×) or a number like `0.85` in the profile, or `"speed": 0.9` on a single
  line beat. Speed is applied with ffmpeg `atempo`, so the pitch stays the same.
- **A garbled or truncated line**: change the line's text slightly (add a comma or ។ at phrase breaks), or give
  the beat a `"seed": 11` to re-roll it. Very long lines are worse, so split anything over ~40 Khmer syllables
  into two beats.
- **English words inside Khmer lines** get a Khmer accent. Write loanwords in Khmer script where possible.
- **Numbers**: write them as Khmer words (ប្រាំពីរ), not digits, for reliable pronunciation.
- **A real voice actor**: record 5–15 s of clean speech, then set `sample_reference: "source/voices/dara.wav"`
  and `sample_reference_text` (its exact transcript) and rerun `voices`.

## Fallback engine
`--engine edge` (or `"engine": "edge"` per profile) uses Microsoft edge-tts neural voices
(`km-KH-PisethNeural` male, `km-KH-SreymomNeural` female). It needs internet and offers only two voices.
Characters are told apart by `edge_pitch` (e.g. `+30Hz` for a child) and `edge_rate` (e.g. `-10%` for an elder).

## Pronunciation and register
- Monks: calm, slow (`speed: slow`). Monks say អាត្មា for "I"; laypeople address monks as ព្រះតេជគុណ.
- Royal speech: formal vocabulary (ព្រះករុណា, ទូលបង្គំ), with a confident, formal design.
- Children: `pitch: very_high`, a youthful design, simple vocabulary.
- Always ask for native-speaker review of the Khmer before publishing.
