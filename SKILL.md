---
name: localization-packager
description: Package one video (or app) for many languages without translating anything. `manifest` prints the per-language delivery plan (one folder per language code, 4 owed files: title.txt, description.txt, subtitles.srt, thumbnail.txt, each with the source facts it is translated from); `sheet` exports the translator hand-off sheet (title, description, thumbnail text, then every subtitle cue with SRT timing and source text, blank target column; Markdown or CSV, one language or all); `check` validates a filled package per language — files present and non-empty, title within YouTube's 100 characters (100 passes, 101 flags), subtitles parse as SRT, cue-count gap over 25% of the source flagged, any cue start drifted over 2.0s from the source cue flagged (exactly 2.0s passes, 2.1s flags) — and reports each language COMPLETE or INCOMPLETE with exact problems, exit 1 when any language is incomplete. The check is structural only and never judges translation quality. Use when packaging content for translators or gating what they return. Exit 1 is a finding, not a failure.
---

# localization-packager — agent skill

## Purpose

Going multilingual is a packaging problem around the
translating: every language owes the same 4 files, and what
comes back needs checking — presence, title length, subtitle
parseability, cue counts, cue timing drift. This tool makes
the plan, the hand-off sheet, and the structural check from
ONE project JSON. Pure Python standard library; local only.

**The honesty core of this tool:** it translates nothing and
judges no translation. `check` verifies structure — file
presence, parseability, lengths, timings. A COMPLETE package
can still hold a bad translation; only a reader of the
language can judge that. Never report a COMPLETE verdict as
"the translation is good" or "ready to publish" — it is
"structurally complete, ready for a human quality read".

## When to use / not use

Use when:
- A video or app is being released in additional languages
  and the work is handed to translators: `manifest` for the
  plan, `sheet` for the hand-off, `check` as the gate on
  what returns.
- A pipeline needs a per-language yes/no: `check` exit 0 =
  every language structurally complete; exit 1 = the output
  names each incomplete language and its exact problems.

Do NOT use when:
- You need the translation itself — this tool calls no
  translation API and produces no translated text. The blank
  target column is for a human translator.
- You need translation quality assurance — no spell-check,
  back-translation or quality scoring exists here, by design.
- You need channel-level assets (banners, end screens) or
  app-store metadata beyond the 4 packaged files — out of
  scope, deliberately.

## Commands

Every command takes the project file as a positional argument
and supports `--json`.

```bash
# The per-language delivery plan
python3 src/localization_packager.py manifest PROJECT.json

# Translator hand-off sheet (Markdown default, or CSV;
# one language or every target)
python3 src/localization_packager.py sheet PROJECT.json \
    [--format md|csv] [--language CODE]

# Validate a filled package (exit 1 when any language is
# incomplete; --root when the folders live elsewhere)
python3 src/localization_packager.py check PROJECT.json \
    [--root DIR]
```

Project fields: `project` (name), `source_language`,
`source_title`, `source_description`,
`source_thumbnail_text`, `source_subtitles` (path to the
source SRT, relative to the project file), `targets` — list
of `{"language", "name", "translator"?}`; language codes
must be unique. The file is validated on every read;
structural problems (missing fields, a duplicate language, a
missing or unparseable source SRT) are exit-2 errors that
name the problem.

Package layout: one folder per language code holding
`title.txt`, `description.txt`, `subtitles.srt`,
`thumbnail.txt`.

## Check rules (exact)

Per language, in file order:

- `title.txt` — missing or empty is a problem; the stripped
  text longer than **100 characters** is a problem (100
  passes, 101 flags). Characters are Unicode code points.
- `description.txt` — missing or empty is a problem.
- `subtitles.srt` — missing or empty is a problem; text that
  does not parse as SRT is a problem (the parse error is
  quoted); a cue count differing from the source by more
  than **25%** of the source count is a problem (a gap of
  exactly 25% passes, and a smaller gap is noted, not
  flagged); the largest per-position start drift over
  **2000 ms** is a problem naming the cue and the drift
  (exactly 2000 ms passes; 2100 ms flags as "2.1s"). Drift
  pairs cues by position over the first min(source, target)
  cues, starts only.
- `thumbnail.txt` — missing or empty is a problem.

Verdicts: a language with zero problems is COMPLETE, else
INCOMPLETE with the problem count. `check` exits 0 only when
every language is COMPLETE.

## Output JSON schema (`--json`)

Common fields: `tool` (`"localization-packager"`),
`version`, `command`, `project_file` (file name), `project`.

`manifest`: `source_language`, `source_title`, `source_cues`,
`languages` — each `{language, name, translator, folder,
files}` where `files` is the 4 owed files, each `{file, what,
source_fact}`.
`check`: `source_cues`, `root`, `languages` — each
`{language, name, translator, status ("complete" |
"incomplete"), items, problems}` where `items` is the 4
per-file results `{file, ok, detail}` and `problems` lists
the failing details — plus `complete`, `total`,
`all_complete`, and a `note` restating that the check is
structural only.
`sheet`: `sheets` — one per target language, each
`{language, name, translator, rows}`; `rows` is
`{n, item, timing, source, target}` — 3 string rows (title,
description, thumbnail) then one row per source cue
(`item` = "cue N", `timing` = SRT "start --> end"); `target`
is always "" — the blank column the translator fills.

On error, stdout is a single object: `{"error": "<message>"}`
with exit code 2 — including argparse usage errors in
`--json` mode. Never plain text, never a traceback.

## Exit codes

- `0` — command succeeded; for `check`, every language is
  COMPLETE.
- `1` — a finding: `check` found at least one incomplete
  language. Not a crash — the problems list is the fix list
  to send back to the translator.
- `2` — ERROR: project file missing or not valid JSON, a
  required field missing, a duplicate target language, the
  source subtitles missing or unparseable, an unknown
  `--language`, an invalid flag. No output facts may be
  quoted from a failed run.

## Limits & honesty rules the agent must respect

- **COMPLETE means structurally complete — nothing more.**
  Never upgrade it to "the translation is correct", "good"
  or "publishable". The release still needs a reader of the
  language; say so when reporting a COMPLETE package.
- **INCOMPLETE is a fix list, not a failure of the
  translator.** Report the exact problems (file, cue number,
  drift, character count) — they are written to be forwarded
  as-is.
- **The tool produces no translated text.** A sheet's target
  column is blank on purpose. Never fill it by machine
  translation and present the result as this tool's output,
  and never claim a language package exists until its 4
  files are actually on disk and `check` has run on them.
- **Drift flags are positional.** If a translator split one
  cue in two, later cues shift position and may flag; the
  cue-count note in the output gives the context. Report
  both facts, not just the flag.
- Local only: the tool reads only the project file, the
  source SRT and the package folders named on the command
  line, and sends nothing anywhere.
