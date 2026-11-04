#!/usr/bin/env python3
"""localization-packager — package one video (or app) for many
languages: the folder plan, the translator hand-off sheet, and a
structural check of what comes back.

Pure Python standard library. Local only: no network, no
uploads, no accounts. And NO TRANSLATION: this tool never calls
a translation API — it packages work for a human translator
and checks the shape of what comes back.

Going multilingual is not the translating. It is the packaging
around the translating: every language needs the same set of
pieces (a title, a description, a subtitle file, thumbnail
text), in the same shape, in its own folder — and when the
pieces come back, someone has to notice that one language is
missing its thumbnail text, another's title is too long for
YouTube, and a third's subtitles drift seconds away from the
source timings. That noticing is this tool:

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

The package layout is one folder per language code, beside the
project file (or under --root), each holding the same 4 files:
title.txt, description.txt, subtitles.srt, thumbnail.txt.

Commands:
  manifest PROJECT
            the delivery plan: per language, the folder, the
            translator, and the 4 files each language owes —
            with the source facts each file is translated from
            (source title + its character count, source
            description length, source cue count).
  sheet PROJECT [--format md|csv] [--language CODE]
            the translator hand-off sheet: every string to
            translate — title, description, thumbnail text,
            then every subtitle cue with its timing and source
            text — with a blank target column. One sheet per
            target language (or just the one named).
  check PROJECT [--root DIR]
            validate a filled package, per language: the 4
            files exist and are non-empty; the title fits
            YouTube's 100-character limit; the subtitles parse
            as SRT; the cue count is not wildly off the source
            (a gap over 25% is flagged); and no cue's start has
            drifted more than 2.0 seconds from the source cue.
            Each language is reported COMPLETE or INCOMPLETE
            with the exact problems. Exit 1 when any language
            is incomplete.

What `check` CANNOT do: judge the translation. It reads
structure — presence, parseability, lengths, timings. A
package can be COMPLETE and still be a bad translation; only a
reader of the language can judge that. The check output says
so every time.

All time math is integer milliseconds, hand-checkable. The
drift of a cue is |translated start − source start| over cues
paired by position; exactly 2.0s of drift passes, 2.1s flags.

Exit codes: 0 = ok (for `check`, every language COMPLETE) ·
1 = a finding: `check` found an incomplete language ·
2 = ERROR — clean message, never a traceback; with --json the
error is {"error": ...}. Every command takes --json: one JSON
object with the same facts and exit codes as the text view.
"""
import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

__version__ = "0.1.0"
TOOL = "localization-packager"

TITLE_LIMIT = 100            # YouTube's title limit, characters
DRIFT_LIMIT_MS = 2000        # a cue start may move at most 2.0s
CUE_COUNT_MAX_GAP = 0.25     # cue-count gap over 25% is flagged

PACKAGE_FILES = ("title.txt", "description.txt", "subtitles.srt",
                 "thumbnail.txt")


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# --------------------------------------------------------------------------
# SRT parsing (shared shape with the sibling caption tools)
# --------------------------------------------------------------------------

_SRT_TIMING_RE = re.compile(
    r"^(\d{1,2}):([0-5]\d):([0-5]\d)[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):([0-5]\d):([0-5]\d)[,.](\d{1,3})")


def _ts_ms(hours, minutes, seconds, frac):
    """SRT timestamp parts -> integer milliseconds."""
    millis = int(frac.ljust(3, "0"))
    return ((int(hours) * 3600 + int(minutes) * 60
             + int(seconds)) * 1000) + millis


def fmt_srt_ms(ms):
    """Integer milliseconds -> "00:00:03,500" (SRT style)."""
    return (f"{ms // 3600000:02d}:{(ms // 60000) % 60:02d}:"
            f"{(ms // 1000) % 60:02d},{ms % 1000:03d}")


def fmt_seconds(ms):
    """Integer milliseconds -> "2.5" style seconds text."""
    return f"{ms / 1000:.1f}"


def parse_srt(text, label):
    """Parse SRT text -> list of {"start_ms", "end_ms", "text"}.
    Malformed input is a ToolError naming the block — never a
    silent drop and never a traceback."""
    if not text.strip():
        raise ToolError(f"{label}: no cues found (the file is "
                        f"empty)")
    blocks = re.split(r"\r?\n[ \t]*\r?\n", text.strip())
    cues = []
    for i, block in enumerate(blocks, start=1):
        lines = [ln.rstrip("\r")
                 for ln in block.strip().split("\n")]
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines:
            raise ToolError(f"{label}: block {i} is empty")
        m = _SRT_TIMING_RE.match(lines[0].strip())
        if not m:
            raise ToolError(f"{label}: block {i} has no valid "
                            f"timing line (got "
                            f"{lines[0].strip()!r})")
        start = _ts_ms(*m.groups()[:4])
        end = _ts_ms(*m.groups()[4:])
        if end <= start:
            raise ToolError(f"{label}: cue {i} ends at "
                            f"{fmt_srt_ms(end)} — not after its "
                            f"start {fmt_srt_ms(start)}")
        body = "\n".join(lines[1:]).strip()
        if not body:
            raise ToolError(f"{label}: cue {i} has no text")
        cues.append({"start_ms": start, "end_ms": end,
                     "text": body})
    return cues


def load_srt_file(path, label):
    if not path.exists():
        raise ToolError(f"{label} not found: {path}")
    return parse_srt(path.read_text(encoding="utf-8"), label)


# --------------------------------------------------------------------------
# project loading + structural validation (failures here are exit 2)
# --------------------------------------------------------------------------

def _require_str(data, field):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"project {field!r} must be a non-empty "
                        f"string")
    return value.strip()


def _optional_str(data, field, label):
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolError(f"{label} {field!r} must be a string")
    return value.strip() or None


def load_project(path):
    """Load + validate the project file. Returns a dict with the
    source facts, the parsed source cues, and the target list."""
    if not path.exists():
        raise ToolError(f"project file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolError(f"project file is not valid JSON: {path} "
                        f"({exc.msg} at line {exc.lineno})")
    if not isinstance(data, dict):
        raise ToolError(f"project file must hold one JSON "
                        f"object: {path}")
    project = {
        "title": _require_str(data, "project"),
        "source_language": _require_str(data, "source_language"),
        "source_title": _require_str(data, "source_title"),
        "source_description":
            _require_str(data, "source_description"),
        "source_thumbnail_text":
            _require_str(data, "source_thumbnail_text"),
    }
    sub_rel = _require_str(data, "source_subtitles")
    sub_path = Path(sub_rel)
    if not sub_path.is_absolute():
        sub_path = path.parent / sub_path
    project["source_subtitles_path"] = sub_path
    project["source_cues"] = load_srt_file(
        sub_path, f"source subtitles ({sub_rel})")

    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ToolError("project 'targets' must be a non-empty "
                        "list of target languages")
    targets, seen = [], set()
    for i, entry in enumerate(raw_targets, start=1):
        if not isinstance(entry, dict):
            raise ToolError(f"target {i} must be an object with "
                            f"'language' and 'name'")
        language = entry.get("language")
        if not isinstance(language, str) or not language.strip():
            raise ToolError(f"target {i} has no 'language' code")
        language = language.strip()
        if language in seen:
            raise ToolError(f"target language {language!r} "
                            f"appears twice — each language gets "
                            f"exactly one folder")
        seen.add(language)
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ToolError(f"target {language!r} has no 'name'")
        targets.append({
            "language": language,
            "name": name.strip(),
            "translator": _optional_str(entry, "translator",
                                        f"target {language!r}"),
        })
    project["targets"] = targets
    return project


def _translator_of(target):
    return target["translator"] or "unassigned"


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------

def manifest_rows(project):
    rows = []
    for t in project["targets"]:
        rows.append({
            "language": t["language"], "name": t["name"],
            "translator": _translator_of(t),
            "folder": t["language"] + "/",
            "files": [
                {"file": "title.txt",
                 "what": "the translated title",
                 "source_fact":
                     f"source title "
                     f"\"{project['source_title']}\" — "
                     f"{len(project['source_title'])} "
                     f"characters (limit {TITLE_LIMIT})"},
                {"file": "description.txt",
                 "what": "the translated description",
                 "source_fact":
                     f"source description is "
                     f"{len(project['source_description'])} "
                     f"characters"},
                {"file": "subtitles.srt",
                 "what": "the translated subtitles",
                 "source_fact":
                     f"source has "
                     f"{len(project['source_cues'])} cues — "
                     f"keep the source timings"},
                {"file": "thumbnail.txt",
                 "what": "the thumbnail text",
                 "source_fact":
                     f"source thumbnail text: "
                     f"\"{project['source_thumbnail_text']}\""},
            ],
        })
    return rows


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------

def _read_package_file(folder, name):
    """(text, problem) — problem is None when the file exists and
    is non-empty after stripping."""
    path = folder / name
    if not path.exists():
        return None, "missing"
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return None, "the file is empty"
    return text, None


def check_language(project, root, target):
    """Check one language folder. Returns a dict with per-file
    items ({"file", "ok", "detail"}) and the problem list."""
    folder = root / target["language"]
    items, problems = [], []

    def add(fname, ok, detail):
        items.append({"file": fname, "ok": ok, "detail": detail})
        if not ok:
            problems.append(f"{fname} — {detail}")

    # title.txt — present, non-empty, within the YouTube limit
    text, problem = _read_package_file(folder, "title.txt")
    if problem:
        add("title.txt", False, problem)
    else:
        title = text.strip()
        if len(title) > TITLE_LIMIT:
            add("title.txt", False,
                f"{len(title)} characters — over the "
                f"{TITLE_LIMIT}-character YouTube title limit")
        else:
            add("title.txt", True,
                f"{len(title)} characters (limit "
                f"{TITLE_LIMIT})")

    # description.txt — present and non-empty
    text, problem = _read_package_file(folder, "description.txt")
    if problem:
        add("description.txt", False, problem)
    else:
        add("description.txt", True,
            f"present, {len(text.strip())} characters")

    # subtitles.srt — present, parses, sane counts + drift
    text, problem = _read_package_file(folder, "subtitles.srt")
    if problem:
        add("subtitles.srt", False, problem)
    else:
        try:
            cues = parse_srt(
                text, f"{target['language']} subtitles")
        except ToolError as exc:
            add("subtitles.srt", False,
                f"does not parse as SRT — {exc}")
        else:
            source = project["source_cues"]
            sub_problems = []
            gap = abs(len(cues) - len(source))
            if gap * 4 > len(source):  # gap over 25% of source
                sub_problems.append(
                    f"{len(cues)} cues vs {len(source)} in the "
                    f"source — a gap over 25% (cues were "
                    f"probably dropped or merged)")
            worst, worst_cue = 0, None
            for i in range(min(len(cues), len(source))):
                drift = abs(cues[i]["start_ms"]
                            - source[i]["start_ms"])
                if drift > worst:
                    worst, worst_cue = drift, i + 1
            if worst > DRIFT_LIMIT_MS:
                sub_problems.append(
                    f"cue {worst_cue} starts "
                    f"{fmt_seconds(worst)}s away from the "
                    f"source cue (limit "
                    f"{fmt_seconds(DRIFT_LIMIT_MS)}s)")
            if sub_problems:
                add("subtitles.srt", False,
                    "; ".join(sub_problems))
            else:
                detail = (f"{len(cues)} cues, largest timing "
                          f"drift {fmt_seconds(worst)}s (limit "
                          f"{fmt_seconds(DRIFT_LIMIT_MS)}s)")
                if gap:
                    detail += (f"; cue count differs from the "
                               f"source by {gap} (within the "
                               f"25% tolerance)")
                add("subtitles.srt", True, detail)

    # thumbnail.txt — present and non-empty
    text, problem = _read_package_file(folder, "thumbnail.txt")
    if problem:
        add("thumbnail.txt", False, problem)
    else:
        add("thumbnail.txt", True,
            f"present — \"{text.strip()}\"")

    return {"language": target["language"], "name": target["name"],
            "translator": _translator_of(target),
            "status": "incomplete" if problems else "complete",
            "items": items, "problems": problems}


# --------------------------------------------------------------------------
# sheet
# --------------------------------------------------------------------------

def sheet_rows(project):
    """Every string to translate, in hand-off order."""
    rows = [{"item": "title", "timing": "",
             "source": project["source_title"]},
            {"item": "description", "timing": "",
             "source": project["source_description"]},
            {"item": "thumbnail", "timing": "",
             "source": project["source_thumbnail_text"]}]
    for i, cue in enumerate(project["source_cues"], start=1):
        rows.append({
            "item": f"cue {i}",
            "timing": f"{fmt_srt_ms(cue['start_ms'])} --> "
                      f"{fmt_srt_ms(cue['end_ms'])}",
            "source": cue["text"]})
    for i, row in enumerate(rows, start=1):
        row["n"] = i
        row["target"] = ""
    return rows


def _md_cell(text):
    return text.replace("\r\n", " ").replace("\n", " ") \
               .replace("|", "\\|")


def render_sheet_md(project, target, rows):
    lines = [f"# Translation sheet — {target['name']} "
             f"({target['language']})",
             "",
             f"Project: {project['title']} · Translator: "
             f"{_translator_of(target)} · Source language: "
             f"{project['source_language']}",
             "",
             f"| # | Item | Timing | Source "
             f"({project['source_language']}) | "
             f"{target['name']} ({target['language']}) |",
             "|---|------|--------|-------------|-------------|"]
    for r in rows:
        lines.append(f"| {r['n']} | {r['item']} | "
                     f"{r['timing']} | {_md_cell(r['source'])} "
                     f"|  |")
    lines.append("")
    lines.append("Fill the last column. Keep the subtitle "
                 "timings exactly as given — the package check "
                 "flags cues that drift from them.")
    return "\n".join(lines) + "\n"


def render_sheet_csv(project, target, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["n", "item", "timing",
                     f"source_{project['source_language']}",
                     f"target_{target['language']}"])
    for r in rows:
        writer.writerow([r["n"], r["item"], r["timing"],
                         r["source"], ""])
    return buf.getvalue()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in --json
    mode ({"error": ...} on stdout, same exit code 2) — an agent
    driving this tool with --json never gets plain text or a
    traceback. The flag lives on the class so subparsers share
    it."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def _json_arg(p):
    p.add_argument("--json", action="store_true",
                   help="print one JSON object instead of text")


def _header(command, path, project):
    print(f"{TOOL} v{__version__} — {command} · project "
          f"{path.name}")
    print(f"{project['title']} · source language: "
          f"{project['source_language']} · "
          f"{len(project['targets'])} target language(s) · "
          f"{len(project['source_cues'])} source cues")
    print()


def cmd_manifest(a):
    path = Path(a.project)
    project = load_project(path)
    rows = manifest_rows(project)
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__,
            "command": "manifest", "project_file": path.name,
            "project": project["title"],
            "source_language": project["source_language"],
            "source_title": project["source_title"],
            "source_cues": len(project["source_cues"]),
            "languages": rows,
        }, indent=2))
        return 0
    _header("manifest", path, project)
    print("Every language gets its own folder and owes the "
          "same 4 files:")
    print()
    for lang in rows:
        print(f"{lang['folder']} — {lang['name']} · "
              f"translator: {lang['translator']}")
        for f in lang["files"]:
            print(f"  [ ] {f['file']:<16} {f['what']} — "
                  f"{f['source_fact']}")
        print()
    print("Hand each translator their sheet (the `sheet` "
          "command), then run `check` on what comes back.")
    return 0


def cmd_check(a):
    path = Path(a.project)
    project = load_project(path)
    root = Path(a.root) if a.root else path.parent
    results = [check_language(project, root, t)
               for t in project["targets"]]
    complete = sum(1 for r in results
                   if r["status"] == "complete")
    all_complete = complete == len(results)
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__,
            "command": "check", "project_file": path.name,
            "project": project["title"],
            "source_cues": len(project["source_cues"]),
            "root": str(root),
            "languages": results,
            "complete": complete, "total": len(results),
            "all_complete": all_complete,
            "note": "Structural check only — file presence, "
                    "parseability, lengths and timings. It "
                    "cannot judge whether a translation is "
                    "accurate or well written.",
        }, indent=2))
        return 0 if all_complete else 1
    _header("check", path, project)
    for r in results:
        verdict = ("COMPLETE" if r["status"] == "complete"
                   else f"INCOMPLETE "
                        f"({len(r['problems'])} problem(s))")
        print(f"{r['language']} — {r['name']} · translator: "
              f"{r['translator']} — {verdict}")
        for item in r["items"]:
            detail = item["detail"]
            if not item["ok"]:
                detail = f"PROBLEM: {detail}"
            print(f"  {item['file']:<16} {detail}")
        print()
    print(f"{complete} of {len(results)} language(s) "
          f"complete.")
    print("This check covers structure only — file presence, "
          "parseability, lengths and timings. It cannot judge "
          "whether a translation is accurate or well written; "
          "a COMPLETE package still needs a reader of the "
          "language before it ships.")
    return 0 if all_complete else 1


def cmd_sheet(a):
    path = Path(a.project)
    project = load_project(path)
    targets = project["targets"]
    if a.language:
        targets = [t for t in targets
                   if t["language"] == a.language]
        if not targets:
            known = ", ".join(t["language"]
                              for t in project["targets"])
            raise ToolError(f"language {a.language!r} is not a "
                            f"target of this project "
                            f"(targets: {known})")
    rows = sheet_rows(project)
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__,
            "command": "sheet", "project_file": path.name,
            "project": project["title"],
            "sheets": [{"language": t["language"],
                        "name": t["name"],
                        "translator": _translator_of(t),
                        "rows": rows} for t in targets],
        }, indent=2))
        return 0
    blocks = []
    for t in targets:
        if a.format == "csv":
            blocks.append(f"# Translation sheet — {t['name']} "
                          f"({t['language']}) · translator: "
                          f"{_translator_of(t)}\n"
                          + render_sheet_csv(project, t, rows))
        else:
            blocks.append(render_sheet_md(project, t, rows))
    print("\n".join(blocks), end="")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _JsonAwareParser.json_mode = "--json" in argv
    ap = _JsonAwareParser(
        prog=TOOL,
        description="Package one video (or app) for many "
                    "languages: the per-language folder plan, "
                    "the translator hand-off sheet, and a "
                    "structural check of what comes back. It "
                    "translates nothing itself. (stdlib only, "
                    "local only).")
    sub = ap.add_subparsers(dest="command", required=True,
                            parser_class=_JsonAwareParser)

    p_man = sub.add_parser(
        "manifest", help="print the per-language delivery "
                         "plan: folders, translators, and the "
                         "4 files each language owes")
    p_man.add_argument("project", help="project JSON file")
    _json_arg(p_man)
    p_man.set_defaults(func=cmd_manifest)

    p_chk = sub.add_parser(
        "check", help="validate a filled package per language "
                      "(files present, title within YouTube's "
                      "100 characters, subtitles parse, cue "
                      "timings within 2.0s of the source); "
                      "exit 1 when any language is incomplete")
    p_chk.add_argument("project", help="project JSON file")
    p_chk.add_argument("--root",
                       help="folder holding the per-language "
                            "folders (default: the project "
                            "file's folder)")
    _json_arg(p_chk)
    p_chk.set_defaults(func=cmd_check)

    p_sheet = sub.add_parser(
        "sheet", help="export the translator hand-off sheet: "
                      "every string and subtitle cue with a "
                      "blank target column")
    p_sheet.add_argument("project", help="project JSON file")
    p_sheet.add_argument("--format", choices=("md", "csv"),
                         default="md",
                         help="md = Markdown table (default), "
                              "csv = spreadsheet-ready")
    p_sheet.add_argument("--language",
                         help="only this target language "
                              "(default: every target)")
    _json_arg(p_sheet)
    p_sheet.set_defaults(func=cmd_sheet)

    a = ap.parse_args(argv)

    def fail(msg):
        if getattr(a, "json", False):
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    try:
        return a.func(a)
    except ToolError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
