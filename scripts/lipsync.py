"""Khmer-aware lip-sync: text -> viseme units, aligned to the real audio's voiced regions.

Viseme groups: rest, A, E, I, O, U, MBP, FV, LR.
The Khmer script is parsed into consonant clusters with their dependent vowels. Each
cluster becomes (onset viseme, vowel viseme[, coda viseme]). The units are spread over
the voiced stretches of the actual audio (energy based), so the mouth only moves while
the voice is sounding and closes during pauses.
"""
import numpy as np

CONS = {chr(c) for c in range(0x1780, 0x17A3)}
COENG = "្"
LABIAL = set("បពភផម")
LR = set("លរ")
FV = set("វហ")  # វ is a labio-dental /v~w/
VOWEL_SIGN = {
    "ា": "A",   # ា
    "ិ": "I", "ី": "I",  # ិ ី
    "ឹ": "I", "ឺ": "I",  # ឹ ឺ
    "ុ": "U", "ូ": "U",  # ុ ូ
    "ួ": "O",   # ួ
    "ើ": "E",   # ើ
    "ឿ": "E", "ៀ": "E",  # ឿ ៀ
    "េ": "E", "ែ": "E",  # េ ែ
    "ៃ": "A",   # ៃ
    "ោ": "O", "ៅ": "O",  # ោ ៅ
}
CODA_SIGN = {"ំ": "MBP", "ះ": "A", "ៈ": "A"}  # ំ ះ ៈ
INDEP = {"ឥ": "I", "ឦ": "I", "ឧ": "U", "ឩ": "U", "ឪ": "O", "ឫ": "LR", "ឬ": "LR", "ឭ": "LR",
         "ឮ": "LR", "ឯ": "E", "ឰ": "A", "ឱ": "O", "ឲ": "O", "ឳ": "O", "អ": "A"}
LATIN = {"a": "A", "e": "E", "i": "I", "o": "O", "u": "U", "y": "I", "m": "MBP", "b": "MBP", "p": "MBP",
         "f": "FV", "v": "FV", "w": "U", "l": "LR", "r": "LR"}


def onset_vis(ch):
    if ch in LABIAL:
        return "MBP"
    if ch in LR:
        return "LR"
    if ch in FV:
        return "FV" if ch == "វ" else "A"
    return None


def khmer_units(text):
    """Return list of viseme units, each a list of (viseme, weight)."""
    units = []
    i, n = 0, len(text)
    prev_had_vowel = False
    while i < n:
        ch = text[i]
        if ch in CONS:
            onset = onset_vis(ch)
            j = i + 1
            # subscript consonants
            while j + 1 < n and text[j] == COENG and text[j + 1] in CONS:
                if onset is None:
                    onset = onset_vis(text[j + 1])
                j += 2
            vowel = None
            coda = None
            while j < n and (text[j] in VOWEL_SIGN or text[j] in CODA_SIGN or 0x17C9 <= ord(text[j]) <= 0x17D1
                             or text[j] in "់៌៍៎៏័៝"):
                if text[j] in VOWEL_SIGN and vowel is None:
                    vowel = VOWEL_SIGN[text[j]]
                elif text[j] in CODA_SIGN:
                    coda = CODA_SIGN[text[j]]
                j += 1
            if vowel is None and coda is None and prev_had_vowel and units:
                # bare consonant after a vowelled syllable: treat as a final consonant
                if onset:
                    units[-1].append((onset, 0.35))
                prev_had_vowel = False
            else:
                u = []
                if onset:
                    u.append((onset, 0.35))
                u.append((vowel or "A", 1.0))
                if coda:
                    u.append((coda, 0.4))
                units.append(u)
                prev_had_vowel = vowel is not None
            i = j
            continue
        if ch in INDEP:
            units.append([(INDEP[ch], 1.0)])
            prev_had_vowel = True
        elif ch.lower() in LATIN:
            v = LATIN[ch.lower()]
            if v in ("A", "E", "I", "O", "U"):
                units.append([(v, 1.0)])
            elif units:
                units[-1].append((v, 0.35))
        i += 1
    return units or [[("A", 1.0)]]


def envelope(wav, sr, fps=100):
    hop = int(sr / fps)
    n = max(1, len(wav) // hop)
    w = wav[: n * hop].reshape(n, hop)
    rms = np.sqrt((w.astype(np.float64) ** 2).mean(axis=1) + 1e-12)
    if rms.max() > 0:
        rms = rms / np.percentile(rms, 95).clip(1e-6)
    # light smoothing
    k = np.array([0.25, 0.5, 0.25])
    rms = np.convolve(rms, k, mode="same")
    return rms


def voiced_regions(env, fps=100, thr=0.18, min_gap=0.12, min_len=0.06):
    on = env > thr
    regs = []
    i, n = 0, len(on)
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]:
                j += 1
            regs.append([i / fps, j / fps])
            i = j
        else:
            i += 1
    merged = []
    for r in regs:
        if merged and r[0] - merged[-1][1] < min_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [r for r in merged if r[1] - r[0] >= min_len]


def build_track(text, wav, sr, fps=100):
    """Return dict(fps, frames=[[viseme, openness], ...]) aligned to the audio."""
    env = envelope(wav, sr, fps)
    regs = voiced_regions(env, fps)
    units = khmer_units(text)
    total_voiced = sum(r[1] - r[0] for r in regs) or 1e-6
    nfr = len(env)
    frames = [["rest", 0.0] for _ in range(nfr)]
    if not regs:
        return {"fps": fps, "frames": frames, "units": len(units)}
    # allocate units to regions proportionally to region length
    alloc = []
    remaining = len(units)
    for k, r in enumerate(regs):
        if k == len(regs) - 1:
            cnt = remaining
        else:
            cnt = int(round(len(units) * (r[1] - r[0]) / total_voiced))
            cnt = max(1 if remaining > 0 else 0, min(cnt, remaining - (len(regs) - k - 1)))
            cnt = max(cnt, 0)
        alloc.append(cnt)
        remaining -= cnt
    ui = 0
    for r, cnt in zip(regs, alloc):
        if cnt <= 0:
            # region with no unit: generic open mouth
            seq = [("A", 1.0)]
        else:
            seq = [v for u in units[ui:ui + cnt] for v in u]
            ui += cnt
        wsum = sum(w for _, w in seq)
        t = r[0]
        for vis, w in seq:
            d = (r[1] - r[0]) * w / wsum
            f0, f1 = int(t * fps), int((t + d) * fps)
            for f in range(f0, min(max(f1, f0 + 1), nfr)):
                o = float(min(1.0, env[f] / 1.0))
                frames[f] = [vis, round(o, 3)]
            t += d
    # gate by energy (mouth closes in micro-pauses)
    for f in range(nfr):
        if env[f] < 0.10:
            frames[f] = ["rest", 0.0]
    return {"fps": fps, "frames": frames, "units": len(units)}


def sample(track, t):
    if not track:
        return "rest", 0.0
    f = int(t * track["fps"])
    if f < 0 or f >= len(track["frames"]):
        return "rest", 0.0
    v, o = track["frames"][f]
    return v, o


def talk_amount(track, t, window=0.35):
    """0..1 how much the speaker is talking around time t (drives gestures)."""
    if not track:
        return 0.0
    fps = track["fps"]
    f0, f1 = int((t - window) * fps), int((t + window) * fps)
    fr = track["frames"]
    cnt = 0
    tot = 0
    for f in range(max(0, f0), min(len(fr), f1)):
        tot += 1
        if fr[f][0] != "rest":
            cnt += 1
    return cnt / tot if tot else 0.0
