# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl"]
# ///
"""Build app/data/names.js from the Statbel newborn first-name files.

Sources (data/raw/):
  Firstnames_Boys_1995-.xlsx / Firstnames_Girls_1995-.xlsx  (Statbel, one sheet per year,
      columns: Belgium rank/name/count, Flanders ..., Wallonia ..., Brussels ...)
  us_baby_names.csv  (US top-1000 per year 1880-2008, mirror of SSA data; used as the
      "English speakers know this name" signal)

Output: app/data/names.js  ->  window.NF_DATA = {years, totals, fields, names}
  names: one row per (name, sex):
    [name, sex, counts[per year], syllables, vowels, vowelGroups, englishScore, variantKey, inUS, total1995_2025, group]
  Names that never reach 5 births in a single year but do over the whole period come from the
  aggregate sheet with all-zero yearly counts and only a total.

Run:  uv run build_data.py
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "app" / "data" / "names.js"

FILES = {"m": RAW / "Firstnames_Boys_1995-.xlsx", "f": RAW / "Firstnames_Girls_1995-.xlsx"}

VOWELS = set("aeiou")
# vowel pairs pronounced as two syllables (hiatus) in Dutch/French names
HIATUS = {"ia", "io", "ea", "eo", "oa", "ua", "ae", "ao"}


# ---------------------------------------------------------------- helpers
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def letters_only(s: str) -> str:
    return re.sub(r"[^a-z]", "", strip_accents(s).lower())


def phonemes(name: str) -> list[tuple[str, bool, bool]]:
    """Return [(letter, is_vowel, forced_split_before)] for the lowercase name.

    'y' counts as a vowel unless it sits between two vowels or starts the name before a vowel.
    A diaeresis (ë ï ü ÿ) forces a syllable split before that vowel (Raphaël, Loïc, Maël).
    """
    low = name.lower()
    out = []
    raw = [c for c in low if c.isalpha()]
    base = [strip_accents(c) for c in raw]
    for i, c in enumerate(base):
        orig = raw[i]
        split = unicodedata.normalize("NFD", orig).find("̈") >= 0  # diaeresis
        if c in VOWELS:
            out.append((c, True, split))
        elif c == "y":
            prev_v = i > 0 and base[i - 1] in VOWELS
            next_v = i + 1 < len(base) and base[i + 1] in VOWELS
            is_vowel = not ((prev_v and next_v) or (i == 0 and next_v))
            out.append(("i" if is_vowel else "y", is_vowel, split))
        else:
            out.append((c, False, False))
    return out


def vowel_groups(ph) -> list[str]:
    groups, cur = [], ""
    for c, v, _ in ph:
        if v:
            cur += c
        elif cur:
            groups.append(cur)
            cur = ""
    if cur:
        groups.append(cur)
    return groups


def count_syllables(name: str) -> int:
    ph = phonemes(name)
    if not ph:
        return 0
    n = 0
    i = 0
    L = len(ph)
    groups_seen = []
    while i < L:
        c, v, split = ph[i]
        if not v:
            i += 1
            continue
        # consume a vowel cluster, splitting on hiatus pairs / diaeresis
        cluster = c
        n += 1
        i += 1
        while i < L and ph[i][1]:
            nc, _, nsplit = ph[i]
            pair = cluster[-1] + nc
            nxt = ph[i + 1][0] if i + 1 < L and ph[i + 1][1] else ""
            is_eau = (cluster[-1] + nc + nxt == "eau") or (cluster[-2:] + nc == "eau")
            if nsplit or (pair in HIATUS and not is_eau) or (len(cluster) >= 2 and not is_eau):
                n += 1
                cluster = nc
            else:
                cluster += nc
            i += 1
        groups_seen.append(cluster)
    # final-e rule (Dutch reading): a final 'e' after a consonant is pronounced (Lot-te, Fen-ne),
    # except "-es" after a single other syllable (Jules, Charles).
    base = "".join(c for c, _, _ in ph)
    if base.endswith("es") and len(base) > 3 and not ph[-3][1] and n == 2:
        n -= 1
    return max(1, n)


def count_vowels(name: str) -> int:
    return sum(1 for _, v, _ in phonemes(name) if v)


def count_vowel_groups(name: str) -> int:
    return len(vowel_groups(phonemes(name)))


def diacritic_count(name: str) -> int:
    return sum(1 for c in unicodedata.normalize("NFD", name) if unicodedata.category(c) == "Mn") + name.lower().count("ç") + name.lower().count("ø") + name.lower().count("æ")


EN_PENALTIES = [
    (r"ij", 0.45), (r"ui", 0.3), (r"oe", 0.3), (r"eu", 0.3), (r"uu", 0.3), (r"aa", 0.2), (r"ee", 0.2),
    (r"oo", 0.1), (r"sch", 0.35), (r"tj", 0.35), (r"dj", 0.2), (r"sj", 0.35), (r"^j", 0.2),
    (r"g[ei]", 0.1), (r"gn", 0.2), (r"ch", 0.1), (r"ou", 0.1), (r"ei", 0.1), (r"ill", 0.25),
    (r"[bcdfghjklmnpqrstvwxz]{4}", 0.2), (r"^[bcdfghjklmnpqrstvwxz]{3}", 0.1), (r"ç", 0.2), (r"x", 0.05),
]


def english_score(name: str, in_us: bool) -> float:
    low = strip_accents(name).lower()
    dia = min(diacritic_count(name), 3)
    if in_us:
        return round(max(0.0, 1.0 - 0.08 * dia), 2)
    s = 0.9  # unknown to English speakers starts a little lower than a familiar name
    s -= 0.12 * dia
    for pat, pen in EN_PENALTIES:
        if re.search(pat, low):
            s -= pen
    if len(low) > 9:
        s -= 0.1
    return round(min(1.0, max(0.0, s)), 2)


def variant_key(name: str) -> str:
    """Collapse spelling variants onto one phonetic-ish key (rafael/raphael/raphaël -> 'rafael')."""
    s = letters_only(name)
    s = s.replace("ph", "f").replace("th", "t").replace("ck", "k").replace("chl", "cl").replace("chr", "cr")
    s = s.replace("qu", "k").replace("k", "c").replace("ou", "u").replace("ay", "ai").replace("ey", "ei")
    s = s.replace("y", "i").replace("w", "v").replace("z", "s").replace("x", "cs")
    s = re.sub(r"(.)\1+", r"\1", s)  # collapse doubles
    s = re.sub(r"h$", "", s)  # Noah / Noa, Sarah / Sara
    s = re.sub(r"h", "", s) if len(s) > 3 else s  # Thomas/Tomas already via th; silent h elsewhere
    if len(s) > 3 and s.endswith("e") and s[-2] not in "aeiou":
        s = s[:-1]  # Anne / An, Elise / Elis
    return s


# ---------------------------------------------------------------- load
def load_statbel(path: Path):
    wb = openpyxl.load_workbook(path, read_only=True)
    years = sorted(int(n) for n in wb.sheetnames if n.isdigit())
    counts: dict[str, dict[int, int]] = defaultdict(dict)
    totals: dict[str, int] = {}
    agg = [n for n in wb.sheetnames if "-" in n]
    if agg:
        for i, row in enumerate(wb[agg[0]].iter_rows(values_only=True)):
            if i and row[1] and row[2] is not None:
                totals[str(row[1]).strip()] = int(row[2])
    for y in years:
        ws = wb[str(y)]
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue
            name, cnt = row[1], row[2]
            if not name or cnt is None:
                continue
            name = str(name).strip()
            counts[name][y] = int(cnt)
    for name in totals:
        counts.setdefault(name, {})
    return years, counts, totals


def load_us(path: Path, since: int = 1950) -> set[str]:
    names = set()
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["year"]) >= since:
                names.add(row["name"].lower())
    return names


GROUPS = {"dutch","french","english","german","scandinavian","celtic","italian","spanish_portuguese","greek","slavic",
          "hebrew","arabic","turkish","african","asian","international","other"}


def load_groups() -> dict[str, str]:
    """Merge data/groups/batch_*.json (name -> group code), written by the classification agents."""
    out: dict[str, str] = {}
    for f in sorted((ROOT / "data" / "groups").glob("batch_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"skipping {f.name}: {e}")
            continue
        for k, v in d.items():
            v = str(v).strip().lower()
            out[k.strip()] = v if v in GROUPS else "other"
    return out


def main():
    us = load_us(RAW / "us_baby_names.csv")
    groups = load_groups()
    all_years = None
    rows = []
    totals = {}
    for sex, path in FILES.items():
        years, counts, agg_totals = load_statbel(path)
        all_years = years if all_years is None else sorted(set(all_years) | set(years))
        totals[sex] = [sum(c.get(y, 0) for c in counts.values()) for y in years]
        for name, by_year in counts.items():
            in_us = letters_only(name) in us
            rows.append([
                name, sex, [by_year.get(y, 0) for y in years],
                count_syllables(name), count_vowels(name), count_vowel_groups(name),
                english_score(name, in_us), variant_key(name), 1 if in_us else 0,
                agg_totals.get(name, sum(by_year.values())),
            ])
    # group: direct classification, else the most common group among classified spelling variants, else unknown
    from collections import Counter
    by_key: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        g = groups.get(r[0])
        if g:
            by_key[r[7]][g] += 1
    n_direct = n_inherit = 0
    for r in rows:
        g = groups.get(r[0])
        if g:
            n_direct += 1
        elif by_key.get(r[7]):
            g = by_key[r[7]].most_common(1)[0][0]
            n_inherit += 1
        r.append(g or "unknown")
    print(f"groups: {n_direct} classified directly, {n_inherit} inherited from a variant, {len(rows)-n_direct-n_inherit} unknown")
    rows.sort(key=lambda r: (-sum(r[2][-3:]), -r[9], r[0]))
    data = {
        "years": all_years,
        "totals": totals,
        "fields": ["name", "sex", "counts", "syllables", "vowels", "vowelGroups", "english", "variantKey", "inUS", "total", "group"],
        "names": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    js = "window.NF_DATA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    OUT.write_text(js, encoding="utf-8")
    # precomputed origin/meaning notes (data/meanings/batch_*.json, written by Claude agents) -> app/data/meanings.js
    meanings: dict[str, str] = {}
    for f in sorted((ROOT / "data" / "meanings").glob("batch_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"skipping {f.name}: {e}")
            continue
        for k, v in d.items():
            if isinstance(v, str) and v.strip():
                meanings[k.strip()] = v.strip()
    MOUT = OUT.parent / "meanings.js"
    MOUT.write_text("window.NF_MEANINGS=" + json.dumps(meanings, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"wrote {MOUT} ({MOUT.stat().st_size/1e6:.2f} MB), {len(meanings)} meaning notes")
    print(f"wrote {OUT} ({OUT.stat().st_size/1e6:.2f} MB), {len(rows)} name rows, years {all_years[0]}-{all_years[-1]}")
    # sanity samples
    for n in ["Noah", "Emma", "Louise", "Raphaël", "Jules", "Lotte", "Maya", "Lyam", "Mia", "Beau", "Charlotte", "Thijs", "Sjoerd", "Mathéo", "Liam"]:
        print(f"{n:10s} syl={count_syllables(n)} vow={count_vowels(n)} grp={count_vowel_groups(n)} en={english_score(n, letters_only(n) in us)} key={variant_key(n)}")


if __name__ == "__main__":
    main()
