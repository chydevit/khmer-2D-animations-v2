"""Subtitle cues from the final audio timing, SRT export and Khmer Unicode validation."""
import re
import unicodedata

from textrender import wrap_khmer

MAX_KM = 46     # characters per Khmer subtitle line
MAX_EN = 52


def _split_long(text, limit):
    """Split text into chunks that each fit in 2 lines."""
    if len(text) <= limit * 2:
        return [text]
    parts = re.split(r"(?<=[។៕!?\.,])\s*|\s+", text)
    chunks, cur = [], ""
    for p in parts:
        if not p:
            continue
        if len(cur) + len(p) + 1 > limit * 2 and cur:
            chunks.append(cur.strip())
            cur = p
        else:
            cur = (cur + " " + p) if cur else p
    if cur:
        chunks.append(cur.strip())
    return chunks or [text]


def build_cues(T):
    cues = []
    for sh in T["shots"]:
        for ln in sh["lines"]:
            km = (ln.get("km") or "").strip()
            en = (ln.get("en") or "").strip()
            t0 = sh["start"] + ln["start"]
            t1 = t0 + ln["dur"]
            km_chunks = _split_long(km, MAX_KM) if km else [""]
            en_chunks = _split_long(en, MAX_EN) if en else [""]
            n = max(len(km_chunks), len(en_chunks))
            km_chunks += [""] * (n - len(km_chunks))
            en_chunks += [""] * (n - len(en_chunks))
            weights = [max(len(a), 1) for a in km_chunks]
            tot = sum(weights)
            tt = t0
            for a, b, w in zip(km_chunks, en_chunks, weights):
                d = (t1 - t0) * w / tot
                cues.append(dict(t0=tt, t1=tt + d, km=a, en=b, line=ln["id"], speaker=ln.get("char")))
                tt += d
    # extend each cue a little for readability without overlapping the next
    cues.sort(key=lambda c: c["t0"])
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["t0"] if i + 1 < len(cues) else c["t1"] + 1.0
        c["t1"] = min(max(c["t1"] + 0.3, c["t0"] + 1.0), nxt - 0.04)
    return cues


def _ts(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s, ms = s + 1, 0
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def write_srt(cues, path, lang):
    out = []
    n = 0
    for c in cues:
        text = c["km"] if lang == "km" else c["en"]
        if not text:
            continue
        n += 1
        lines = wrap_khmer(text, MAX_KM) if lang == "km" else _wrap_en(text)
        out.append("%d\n%s --> %s\n%s\n" % (n, _ts(c["t0"]), _ts(c["t1"]), "\n".join(lines)))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return n


def _wrap_en(text, limit=MAX_EN):
    if len(text) <= limit:
        return [text]
    words = text.split()
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = max(len(a), len(b))
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1]


KHMER_DEP = set(range(0x17B6, 0x17D4)) | {0x17DD}
BASES = set(range(0x1780, 0x17B6))


def validate_khmer(text):
    """Return a list of problems (empty = OK)."""
    probs = []
    if not text:
        return probs
    if unicodedata.normalize("NFC", text) != text:
        probs.append("not NFC-normalised")
    if "◌" in text:
        probs.append("contains dotted circle U+25CC (broken cluster)")
    if "�" in text:
        probs.append("contains replacement character U+FFFD")
    prev = None
    for i, ch in enumerate(text):
        o = ord(ch)
        if o in KHMER_DEP and (prev is None or prev in " \n\t.,!?។" or not (0x1780 <= ord(prev) <= 0x17FF)):
            probs.append("dependent sign %s (U+%04X) without a base consonant at position %d" % (ch, o, i))
        if o == 0x17D2 and (i + 1 >= len(text) or ord(text[i + 1]) not in BASES):
            probs.append("COENG (U+17D2) not followed by a consonant at position %d" % i)
        prev = ch
    if any(0x0E00 <= ord(ch) <= 0x0E7F for ch in text):
        probs.append("contains Thai characters")
    return probs
