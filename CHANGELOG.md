# Changelog

## v0.1.0 — 2026-11-04

First release.

- **One project JSON in, the whole packaging job out** — a
  project file holding `project`, `source_language`,
  `source_title`, `source_description`,
  `source_thumbnail_text`, `source_subtitles` and `targets`
  (language code, name, translator). The package shape is
  one folder per language code, each owing the same 4 files:
  `title.txt`, `description.txt`, `subtitles.srt`,
  `thumbnail.txt`. The project is validated on every read,
  with errors that name the offending field or target; a
  malformed file is a clean exit-2 error, never a traceback.
- **`manifest PROJECT`** — the delivery plan: per language,
  the folder, the translator, and the 4 owed files with the
  source fact each is translated from (source title with its
  character count against the 100-character limit, source
  description length, source cue count, source thumbnail
  text).
- **`sheet PROJECT [--format md|csv] [--language CODE]`** —
  the translator hand-off sheet: title, description and
  thumbnail text, then every subtitle cue with its SRT
  timing and source text, and a blank target column. One
  sheet per target language (or just the one named);
  Markdown escapes pipes, CSV uses real quoting.
- **`check PROJECT [--root DIR]`** — the structural gate on
  what comes back, per language: all 4 files present and
  non-empty; title within YouTube's 100-character limit
  (exactly 100 passes, 101 flags); subtitles parse as SRT
  (a corrupt target file is a finding, exit 1 — a corrupt
  *source* file is an error, exit 2); cue-count gap over
  25% of the source count flagged (exactly 25% passes, a
  smaller gap is noted); per-position cue-start drift over
  2.0 seconds flagged with the cue number (exactly 2000 ms
  passes, 2100 ms flags). All time math is integer
  milliseconds. Each language is reported COMPLETE or
  INCOMPLETE with the exact problems; exit 1 when any
  language is incomplete. The check is structural only and
  says so in its own output — it cannot judge whether a
  translation is accurate or well written.
- **`--json` on every command** — one JSON object with the
  same facts and exit codes as the text view; errors are
  `{"error": ...}` objects, argparse usage errors included.
- **`SKILL.md`** at the repo root for AI coding agents:
  commands, the check rules at their exact boundaries, the
  JSON schemas, exit codes, and the honesty rules (COMPLETE
  means structurally complete, never "the translation is
  good"; the tool produces no translated text).
- Bundled sample project (`examples/project.json`): one
  winter-ride video packaged for Hindi and Punjabi — a
  6-cue English source, a complete Hindi package, and a
  Punjabi package with exactly 3 planted problems (a
  101-character title, cue 4 drifted 2.5s, a missing
  thumbnail file), every number worked out by hand in the
  test-suite header.
- 48 stdlib-unittest tests: SRT parsing at millisecond
  precision, the manifest's source facts, the sample check
  in both directions, the drift/title/cue-count boundaries
  at their exact edges, missing/empty/corrupt package files
  as findings, both sheet formats, and the clean-error shape
  in both modes.
- Pure Python standard library; local only; no translation
  API and no network code; MIT licence.
