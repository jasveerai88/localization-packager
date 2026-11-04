# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** localization-packager's promise
  is "clone and run". Pull requests that add a third-party
  dependency will not be merged.
- **Local only.** No network calls, no telemetry, no uploads
  of user files. The tool reads a project file, a source SRT
  and package folders, and prints; it never sends anything
  anywhere.
- **It never translates.** Do not add a translation API,
  machine translation, or a "fill the target column" feature.
  The blank target column is the product: packaging and
  checking for human translators is the whole job.
- **COMPLETE means structure, never quality.** Wording that
  presents a COMPLETE verdict as translation quality
  ("verified translation", "ready to publish") will not be
  merged. The check reads presence, parseability, lengths
  and timings, and its output must keep saying so.
- **Boundaries stay exact and documented.** The title limit
  (100 characters), the drift limit (2.0s) and the cue-count
  tolerance (25%) are stated product rules, each pinned by a
  test at its exact edge (pass at the limit, flag one step
  past it). Changing one needs the README, the changelog,
  the SKILL.md rules and the boundary tests updated together.
- **Time math stays integer milliseconds.** No float seconds
  in comparisons — drift at exactly 2000 ms must pass and
  2100 ms must flag, reproducibly.
- **Both directions tested.** A behaviour change needs a test
  where good input succeeds and bad input fails cleanly — not
  just one side. Expected numbers need hand-computed values,
  not numbers copied from the tool's own output.

## Getting started

```bash
git clone https://github.com/jasveerai88/localization-packager
cd localization-packager
python3 -m unittest discover -s tests -v
python3 src/localization_packager.py check examples/project.json
```

## Pull requests

1. Fork, branch, and keep the change to one topic.
2. Add or update tests under `tests/`; the full suite must pass.
3. Note the change in `CHANGELOG.md` under an "Unreleased" heading.
4. Describe the behaviour change with a real before/after run if
   the CLI output changes.
