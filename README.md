# localization-packager

**Going multilingual is not the translating. It is the
packaging around the translating.**

Every language needs the same set of pieces — a title, a
description, a subtitle file, thumbnail text — in the same
shape, in its own folder. And when the pieces come back from
translators, someone has to notice that one language is
missing its thumbnail text, another's title is too long for
YouTube, and a third's subtitles drift seconds away from the
source timings. That noticing usually happens late, by eye,
or not at all.

`localization-packager` does the packaging. `manifest` prints
the delivery plan — per language, the folder and the 4 files
it owes, with the source facts each file is translated from.
`sheet` exports the translator hand-off sheet: every string
and subtitle cue, with timings and a blank column to fill.
`check` validates what comes back, per language — files
present, title inside YouTube's 100-character limit, subtitles
parsing as SRT, cue counts sane, and no cue start drifted
more than 2.0 seconds from the source.

**It translates nothing.** There is no translation API in
this tool, no machine translation, no network code at all.
It packages work for human translators and checks the shape
of what returns.

- Pure Python 3 standard library — no dependencies, no install step
- Local only — your project files never leave your machine
- Script-friendly exit codes: `0` = ok, `1` = a finding
  (a language is incomplete), `2` = error

## The one idea: one project file, one folder per language

```json
{
  "project": "Kelowna Trail Loop — Winter Ride",
  "source_language": "en",
  "source_title": "Kelowna Trail Loop in Winter | Full Ride",
  "source_description": "A full winter ride...",
  "source_thumbnail_text": "WINTER RIDE!",
  "source_subtitles": "source/en.srt",
  "targets": [{"language": "hi", "name": "Hindi",
               "translator": "Priya Sharma"},
              {"language": "pa", "name": "Punjabi",
               "translator": "Harpreet Gill"}]
}
```

| Field | Meaning |
|---|---|
| `project` | the project name |
| `source_language` | language code of the source material |
| `source_title` | the source title (its character count is shown against the 100-character limit) |
| `source_description` | the source description |
| `source_thumbnail_text` | the text burned into the source thumbnail |
| `source_subtitles` | path to the source SRT, relative to the project file |
| `targets` | list of `{"language", "name", "translator"}` — translator optional |

The package layout is one folder per language code, beside
the project file (or under `--root`):

```text
hi/title.txt        the translated title
hi/description.txt  the translated description
hi/subtitles.srt    the translated subtitles
hi/thumbnail.txt    the thumbnail text
```

## What `check` verifies — and what it cannot

Per language, `check` verifies:

1. **All 4 files exist and are non-empty.**
2. **The title fits YouTube's limit** — 100 characters.
   Exactly 100 passes; 101 is flagged.
3. **The subtitles parse as SRT** — a broken file is named,
   not silently skipped.
4. **The cue count is not wildly off** — a gap over 25% of
   the source cue count is flagged (translators merging two
   cues is normal; half the cues vanishing is not).
5. **No cue start drifted more than 2.0 seconds** from the
   source cue at the same position. Exactly 2.0s passes;
   2.1s is flagged, with the cue number and the drift.

What it **cannot** do is judge the translation. It reads
structure — presence, parseability, lengths, timings. A
package can be COMPLETE and still be a bad translation; only
a reader of the language can judge that, and the check
output says so every time.

## Usage

```bash
# 1. The delivery plan
python3 src/localization_packager.py manifest examples/project.json

# 2. The translator hand-off sheet (Markdown; --format csv for a spreadsheet)
python3 src/localization_packager.py sheet examples/project.json --language hi
python3 src/localization_packager.py sheet examples/project.json --format csv

# 3. Check what came back (exit 1 = some language is incomplete)
python3 src/localization_packager.py check examples/project.json
python3 src/localization_packager.py check project.json --root ./returned-packages

# 4. Drive it from a script
python3 src/localization_packager.py check project.json || echo "a language is incomplete"
```

## Use with AI agents

Every command takes `--json`: one JSON object with the same
facts and exit codes as the text view (errors come back as
`{"error": ...}`, argparse usage errors included):

```bash
python3 src/localization_packager.py check \
    examples/project.json --json
```

Agents: read [SKILL.md](SKILL.md) first — commands, the full
JSON schemas, exit codes, and the honesty rules (a COMPLETE
verdict is about structure, never translation quality).

## Real run (verbatim)

The bundled sample is one winter-ride video being packaged
for Hindi and Punjabi. The plan:

```text
$ python3 src/localization_packager.py manifest examples/project.json
localization-packager v0.1.0 — manifest · project project.json
Kelowna Trail Loop — Winter Ride · source language: en · 2 target language(s) · 6 source cues

Every language gets its own folder and owes the same 4 files:

hi/ — Hindi · translator: Priya Sharma
  [ ] title.txt        the translated title — source title "Kelowna Trail Loop in Winter | Full Ride" — 40 characters (limit 100)
  [ ] description.txt  the translated description — source description is 186 characters
  [ ] subtitles.srt    the translated subtitles — source has 6 cues — keep the source timings
  [ ] thumbnail.txt    the thumbnail text — source thumbnail text: "WINTER RIDE!"

pa/ — Punjabi · translator: Harpreet Gill
  [ ] title.txt        the translated title — source title "Kelowna Trail Loop in Winter | Full Ride" — 40 characters (limit 100)
  [ ] description.txt  the translated description — source description is 186 characters
  [ ] subtitles.srt    the translated subtitles — source has 6 cues — keep the source timings
  [ ] thumbnail.txt    the thumbnail text — source thumbnail text: "WINTER RIDE!"

Hand each translator their sheet (the `sheet` command), then run `check` on what comes back.
(exit code: 0)
```

The hand-off sheet for the Hindi translator (the Punjabi
sheet has the same rows and a `Punjabi (pa)` column;
`--format csv` produces the same 9 rows as a spreadsheet):

```text
$ python3 src/localization_packager.py sheet examples/project.json --language hi
# Translation sheet — Hindi (hi)

Project: Kelowna Trail Loop — Winter Ride · Translator: Priya Sharma · Source language: en

| # | Item | Timing | Source (en) | Hindi (hi) |
|---|------|--------|-------------|-------------|
| 1 | title |  | Kelowna Trail Loop in Winter \| Full Ride |  |
| 2 | description |  | A full winter ride around the Kelowna trail loop: deep snow, a frozen lake, icy north-facing corners, and a coffee stop at the halfway point. Filmed in one take on a cold, clear morning. |  |
| 3 | thumbnail |  | WINTER RIDE! |  |
| 4 | cue 1 | 00:00:00,000 --> 00:00:03,500 | Welcome back to the channel. |  |
| 5 | cue 2 | 00:00:04,000 --> 00:00:07,000 | Today we ride the Kelowna trail loop. |  |
| 6 | cue 3 | 00:00:07,500 --> 00:00:11,000 | The snow is deep, but the light is perfect. |  |
| 7 | cue 4 | 00:00:11,500 --> 00:00:15,000 | Watch for ice on the north-facing corners. |  |
| 8 | cue 5 | 00:00:15,500 --> 00:00:19,000 | We stop at the lake for coffee. |  |
| 9 | cue 6 | 00:00:19,500 --> 00:00:23,000 | See you on the next ride. |  |

Fill the last column. Keep the subtitle timings exactly as given — the package check flags cues that drift from them.
(exit code: 0)
```

And the check on what "came back". The Hindi package is
complete. The Punjabi package has exactly three problems —
a 101-character title, cue 4 starting 2.5 seconds late, and
no thumbnail text — and the command exits 1:

```text
$ python3 src/localization_packager.py check examples/project.json
localization-packager v0.1.0 — check · project project.json
Kelowna Trail Loop — Winter Ride · source language: en · 2 target language(s) · 6 source cues

hi — Hindi · translator: Priya Sharma — COMPLETE
  title.txt        41 characters (limit 100)
  description.txt  present, 226 characters
  subtitles.srt    6 cues, largest timing drift 0.0s (limit 2.0s)
  thumbnail.txt    present — "सर्दियों की सवारी!"

pa — Punjabi · translator: Harpreet Gill — INCOMPLETE (3 problem(s))
  title.txt        PROBLEM: 101 characters — over the 100-character YouTube title limit
  description.txt  present, 225 characters
  subtitles.srt    PROBLEM: cue 4 starts 2.5s away from the source cue (limit 2.0s)
  thumbnail.txt    PROBLEM: missing

1 of 2 language(s) complete.
This check covers structure only — file presence, parseability, lengths and timings. It cannot judge whether a translation is accurate or well written; a COMPLETE package still needs a reader of the language before it ships.
(exit code: 1)
```

Read the verdict the way it is meant: the Hindi package is
ready to hand to a Hindi reader for the quality pass. The
Punjabi package goes back to the translator with three exact
fixes — not a vague "something's off".

## Tests

```bash
python3 -m unittest discover -s tests -v
# Ran 48 tests — OK
```

The suite covers both directions: SRT parsing (millisecond
precision, malformed blocks, backwards cues); the manifest's
source facts against hand-counted characters; the sample
check (Hindi complete, Punjabi's exactly 3 problems); the
exact boundaries — drift of 2000 ms passes and 2100 ms flags,
a 100-character title passes and 101 flags, a cue-count gap
of exactly 25% passes and a bigger one flags; missing,
empty and corrupt package files as findings (exit 1), never
crashes; the sheet in both formats (row counts, CSV quoting,
the blank target column); and the error shape (malformed
project files, duplicate languages and argparse errors all
exit 2 cleanly, as `{"error": ...}` under `--json`, never a
traceback).

## Internal use

This tool does real jobs for its author: the author's own
channels publish in English and are being packaged for Hindi
and Punjabi editions — the bundled sample is shaped exactly
like that job. `manifest` is the plan each multilingual
release starts from, `sheet` is what goes to the translator,
and `check` is the gate a returned package passes before an
edition is assembled.

## Known limits

- One project file at a time, and the 4-file package shape is
  fixed: title, description, subtitles, thumbnail text.
  Channel-level assets (banners, end screens) are out of
  scope, deliberately.
- Drift is compared cue-by-position, starts only. If a
  translator legitimately splits one long cue in two, every
  later cue shifts position and the check will flag drift —
  that is the tool working as designed: a human looks, and
  the cue-count note explains the context.
- Character counts are Unicode code points, which is how
  YouTube's title limit behaves for most scripts; combining
  characters count individually.
- The tool checks structure, not meaning — there is no
  spell-check, no back-translation, no quality score, by
  design.

## Privacy

What it touches: only the project file and package folders
you point it at. What it sends: nothing — there is no network
code in this tool.

## Support

If this catches one broken language package before it ships,
consider sponsoring: **https://github.com/sponsors/jasveerai88**

## Licence

MIT — see [LICENSE](LICENSE).
