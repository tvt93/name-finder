# Name Finder

Rank Belgian newborn first names against our own criteria.

Live page on claude.ai (owner only, org policy blocks public links): https://claude.ai/artifact/5oKxax2nBJPrBvsuSae3xF
Public copy for the family: https://tvt93.github.io/name-finder/ (GitHub Pages, served from `docs/`, repo https://github.com/tvt93/name-finder).

## Layout

- `data/raw/` – source files
  - `Firstnames_Boys_1995-.xlsx`, `Firstnames_Girls_1995-.xlsx` – Statbel, first names of newborns per year (names with 5+ births), national + regional columns. Source page: https://statbel.fgov.be/en/themes/population/family-names-and-first-names/first-names-boys-and-girls
  - `us_baby_names.csv` – US top-1000 names per year 1880–2008 (mirror of SSA data), used as the "familiar to English speakers" signal.
- `data/groups/` – name-group classification. `input_NN.txt` are the batches that were sent to Claude agents, `batch_NN.json` their answers (name → group code), `batch_13_manual.json` hand fixes. Edit a batch file (or add another `batch_*.json`, later files win) and rebuild to correct a group.
- `data/meanings/` – origin-and-meaning notes. `input_NN.txt` are the batches sent to Claude agents (every spelling seen 2016–2025), `batch_NN_a/b.json` their notes, `batch_15_manual.json` hand fixes. Edit or add a `batch_*.json` and rebuild to correct a note.
- `build_data.py` – turns the raw files into `app/data/names.js` and `app/data/meanings.js` (`uv run build_data.py`).
- `make_dist.py` – wraps `app/index.html` in a full HTML document and copies the data files into `docs/`, the folder GitHub Pages serves.
- `docs/` – generated standalone build. Do not edit by hand; run `python make_dist.py`.
- `app/index.html` – the app. `app/data/names.js` and `app/data/meanings.js` are loaded as plain scripts so the page also opens from disk.

## Per-name fields

`[name, sex, counts per year 1995–2025, syllables, vowels, vowelGroups, englishScore, variantKey, inUS, total, group]`

- syllables: heuristic, Dutch reading (final -e pronounced; "-es" after one syllable silent, so Jules = 1), diaeresis forces a split (Raphaël = 3), hiatus pairs ia/io/ea/eo/oa/ua/ae/ao split.
- vowels: vowel letters, y counted when it acts as a vowel.
- vowelGroups: vowel clusters separated by consonants (Noah = 1, Emma = 2).
- englishScore: 1.0 for names in the US top-1000 since 1950 (minus a little per diacritic); otherwise 0.9 minus penalties for Dutch/French spellings English speakers misread (ij, ui, oe, eu, sch, tj, ill, ...).
- variantKey: phonetic-ish key that groups spellings (rafael / raphael / raphaël).
- total: births 1995–2025 from the aggregate sheet; names with only a total never reached 5 in a single year.
- group: cultural sphere the spelling signals in Belgium today (dutch, french, english, german, scandinavian, celtic, italian, spanish_portuguese, greek, slavic, hebrew, arabic, turkish, african, asian, international, other). Assigned by Claude for every name with yearly data; rare names inherit the group of a classified spelling variant, else `unknown`.

## Criteria in the app

sex · name groups to exclude · number of letters · syllables · vowels · vowel groups · popularity last year · popularity last 3 years · pronounceable in English · letters to exclude · last letters to exclude · first letters to exclude.

Each criterion is either a hard filter or a weighted preference (weight 1–5). Score = weighted average of the soft scores over names that pass every hard filter. Ties break on 3-year popularity.

Adding a criterion = one entry in the `CRIT` object in `app/index.html` (label, defaults, `score(row, params)` in 0..1, `hard(row, params)` boolean, and its parameter inputs).

## Favourites

♥ and ✕ on any row mark a name as liked or disliked. Disliked names are hidden from the results (toggle in the results header). The Favourites tab lists liked names, summarises what they share (sex, syllables, letters, group, first/last letters, endings, popularity, English score, vowels), ranks the 20 closest names in the data by a similarity score, and can ask Claude for 25 more ideas, showing those that exist in the Belgian data. Likes and dislikes are stored in the artifact's shared database (`prefs/current`) for signed-in editors, with a localStorage fallback. The page is shared by public link, so a signed-out viewer keeps likes on their own device. Origin and meaning come from the built-in notes for the ~5,500 names seen in the last ten years; only rarer names fall back to a live Claude lookup (signed-in viewers) or to the Behind the Name / Wikipedia links. The Claude suggestions button needs a signed-in viewer.

## Hosting

The repository lives on a personal github.com account (never the Verity GitHub). GitHub Pages publishes the `docs/` folder of `main`. After changing the page: `python make_dist.py`, commit, push. The claude.ai artifact is republished separately from `app/index.html`.

## Updating the data

Download the two Statbel files again into `data/raw/` and run `uv run build_data.py`, then republish `app/index.html` with `data/names.js` and `data/meanings.js`.
