#!/usr/bin/env python3
"""Tests for localization-packager. Stdlib unittest only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

Every expected number below was worked out by hand from the
sample project, never copied from the tool's own output.

Sample project (examples/), by hand:
source/en.srt has 6 cues starting at 0.0, 4.0, 7.5, 11.5,
15.5 and 19.5 seconds. Source title "Kelowna Trail Loop in
Winter | Full Ride" is 40 characters; the source description
is 186 characters.

Hindi (hi) is the complete package: title 41 characters,
description present, subtitles 6 cues at the source timings
(largest drift 0.0s), thumbnail present -> COMPLETE.

Punjabi (pa) is deliberately incomplete, exactly 3 problems:
  - title.txt is 101 characters (one over the 100 limit)
  - subtitles.srt cue 4 starts at 14.0s vs the source's 11.5s
    -> drift 2.5s (over the 2.0s limit)
  - thumbnail.txt is missing
-> INCOMPLETE (3 problem(s)), check exits 1.

Boundaries pinned below: drift of exactly 2000 ms passes,
2100 ms flags; a title of exactly 100 characters passes, 101
flags; a cue-count gap of exactly 25% of the source count
passes (8 source cues, 6 delivered), a bigger gap flags
(5 delivered).
"""
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SRC = PACK_ROOT / "src" / "localization_packager.py"
SAMPLE = PACK_ROOT / "examples" / "project.json"
sys.path.insert(0, str(PACK_ROOT / "src"))

import localization_packager as lp  # noqa: E402


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SRC), *args],
        capture_output=True, text=True, cwd=PACK_ROOT)


def ts(ms):
    return (f"{ms // 3600000:02d}:{(ms // 60000) % 60:02d}:"
            f"{(ms // 1000) % 60:02d},{ms % 1000:03d}")


def srt_text(cues):
    """cues: list of (start_ms, end_ms, text) -> SRT text."""
    blocks = [f"{i}\n{ts(s)} --> {ts(e)}\n{t}"
              for i, (s, e, t) in enumerate(cues, start=1)]
    return "\n\n".join(blocks) + "\n"


BASE_CUES = [(0, 3000, "One."), (4000, 7000, "Two."),
             (8000, 11000, "Three."), (12000, 15000, "Four.")]


def build_project(tmp, source_cues=BASE_CUES, targets=None,
                  packages=None):
    """Write a project + package tree under tmp; return the
    project file path. packages maps language -> {file: text};
    a file mapped to None is left out entirely."""
    root = Path(tmp)
    (root / "source").mkdir(parents=True, exist_ok=True)
    (root / "source" / "en.srt").write_text(
        srt_text(source_cues), encoding="utf-8")
    if targets is None:
        targets = [{"language": "hi", "name": "Hindi",
                    "translator": "Priya Sharma"}]
    data = {"project": "Demo Project", "source_language": "en",
            "source_title": "Demo Title",
            "source_description": "A demo description.",
            "source_thumbnail_text": "DEMO!",
            "source_subtitles": "source/en.srt",
            "targets": targets}
    project_path = root / "project.json"
    project_path.write_text(json.dumps(data), encoding="utf-8")
    for lang, files in (packages or {}).items():
        folder = root / lang
        folder.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            if text is not None:
                (folder / name).write_text(text,
                                           encoding="utf-8")
    return str(project_path)


def complete_package(cues=BASE_CUES, title="A fine title"):
    return {"title.txt": title + "\n",
            "description.txt": "A translated description.\n",
            "subtitles.srt": srt_text(cues),
            "thumbnail.txt": "THUMB!\n"}


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name


# ----------------------------------------------------------------------
# SRT parsing (unit level)
# ----------------------------------------------------------------------

class TestSrtParsing(unittest.TestCase):
    def test_parse_sample_source_counts_and_times(self):
        text = (PACK_ROOT / "examples" / "source"
                / "en.srt").read_text(encoding="utf-8")
        cues = lp.parse_srt(text, "source")
        self.assertEqual(len(cues), 6)
        self.assertEqual(cues[3]["start_ms"], 11500)
        self.assertEqual(cues[3]["end_ms"], 15000)
        self.assertEqual(cues[0]["text"],
                         "Welcome back to the channel.")

    def test_parse_without_index_lines(self):
        cues = lp.parse_srt(
            "00:00:01,000 --> 00:00:02,500\nHello.\n", "x")
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0]["start_ms"], 1000)
        self.assertEqual(cues[0]["end_ms"], 2500)

    def test_parse_millisecond_precision(self):
        cues = lp.parse_srt(srt_text([(2100, 3000, "Late.")]),
                            "x")
        self.assertEqual(cues[0]["start_ms"], 2100)

    def test_empty_text_raises(self):
        with self.assertRaises(lp.ToolError):
            lp.parse_srt("   \n", "x")

    def test_bad_timing_line_raises(self):
        with self.assertRaises(lp.ToolError):
            lp.parse_srt("1\nnot a timing\nText.\n", "x")

    def test_end_before_start_raises(self):
        with self.assertRaises(lp.ToolError):
            lp.parse_srt(srt_text([(5000, 4000, "Backwards.")]),
                         "x")

    def test_cue_without_text_raises(self):
        with self.assertRaises(lp.ToolError):
            lp.parse_srt("1\n00:00:01,000 --> 00:00:02,000\n",
                         "x")

    def test_fmt_srt_ms(self):
        self.assertEqual(lp.fmt_srt_ms(11500), "00:00:11,500")
        self.assertEqual(lp.fmt_srt_ms(0), "00:00:00,000")


# ----------------------------------------------------------------------
# manifest
# ----------------------------------------------------------------------

class TestManifest(unittest.TestCase):
    def test_manifest_sample_exit_0(self):
        r = run_cli("manifest", str(SAMPLE))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_manifest_lists_both_languages_and_files(self):
        out = run_cli("manifest", str(SAMPLE)).stdout
        for needle in ("hi/ — Hindi", "pa/ — Punjabi",
                       "Priya Sharma", "Harpreet Gill",
                       "title.txt", "description.txt",
                       "subtitles.srt", "thumbnail.txt"):
            self.assertIn(needle, out)

    def test_manifest_source_facts(self):
        out = run_cli("manifest", str(SAMPLE)).stdout
        self.assertIn("40 characters (limit 100)", out)
        self.assertIn("source description is 186 characters",
                      out)
        self.assertIn("source has 6 cues", out)
        self.assertIn('"WINTER RIDE!"', out)

    def test_manifest_json_shape(self):
        r = run_cli("manifest", str(SAMPLE), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["command"], "manifest")
        self.assertEqual(data["source_cues"], 6)
        self.assertEqual(len(data["languages"]), 2)
        for lang in data["languages"]:
            self.assertEqual(len(lang["files"]), 4)
        self.assertEqual(data["languages"][0]["translator"],
                         "Priya Sharma")


# ----------------------------------------------------------------------
# check on the bundled sample
# ----------------------------------------------------------------------

class TestCheckSample(unittest.TestCase):
    def test_check_sample_exit_1(self):
        r = run_cli("check", str(SAMPLE))
        self.assertEqual(r.returncode, 1, r.stderr)

    def test_check_sample_verdicts(self):
        out = run_cli("check", str(SAMPLE)).stdout
        self.assertIn("hi — Hindi · translator: Priya Sharma "
                      "— COMPLETE", out)
        self.assertIn("pa — Punjabi · translator: Harpreet "
                      "Gill — INCOMPLETE (3 problem(s))", out)
        self.assertIn("1 of 2 language(s) complete.", out)

    def test_check_sample_hi_details(self):
        out = run_cli("check", str(SAMPLE)).stdout
        self.assertIn("41 characters (limit 100)", out)
        self.assertIn("6 cues, largest timing drift 0.0s "
                      "(limit 2.0s)", out)

    def test_check_sample_pa_problems_exact(self):
        out = run_cli("check", str(SAMPLE)).stdout
        self.assertIn("PROBLEM: 101 characters — over the "
                      "100-character YouTube title limit", out)
        self.assertIn("PROBLEM: cue 4 starts 2.5s away from "
                      "the source cue (limit 2.0s)", out)
        self.assertIn("PROBLEM: missing", out)

    def test_check_sample_honesty_line(self):
        out = run_cli("check", str(SAMPLE)).stdout
        self.assertIn("cannot judge whether a translation is "
                      "accurate or well written", out)

    def test_check_sample_json(self):
        r = run_cli("check", str(SAMPLE), "--json")
        self.assertEqual(r.returncode, 1, r.stderr)
        data = json.loads(r.stdout)
        self.assertFalse(data["all_complete"])
        self.assertEqual(data["complete"], 1)
        self.assertEqual(data["total"], 2)
        by_lang = {lang["language"]: lang
                   for lang in data["languages"]}
        self.assertEqual(by_lang["hi"]["status"], "complete")
        self.assertEqual(by_lang["hi"]["problems"], [])
        self.assertEqual(by_lang["pa"]["status"], "incomplete")
        self.assertEqual(len(by_lang["pa"]["problems"]), 3)
        self.assertIn("structural check only",
                      data["note"].lower())


# ----------------------------------------------------------------------
# check boundaries (temp packages)
# ----------------------------------------------------------------------

class TestCheckBoundaries(TempDirCase):
    def run_check(self, project):
        return run_cli("check", project)

    def test_all_complete_exit_0(self):
        project = build_project(
            self.tmp, packages={"hi": complete_package()})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("COMPLETE", r.stdout)
        self.assertIn("1 of 1 language(s) complete.", r.stdout)

    def test_drift_exactly_2000ms_passes(self):
        cues = [(s + 2000, e + 2000, t) for s, e, t in BASE_CUES]
        project = build_project(
            self.tmp,
            packages={"hi": complete_package(cues=cues)})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("largest timing drift 2.0s", r.stdout)

    def test_drift_2100ms_flags(self):
        cues = list(BASE_CUES)
        cues[1] = (4000 + 2100, 7000, "Two.")
        project = build_project(
            self.tmp,
            packages={"hi": complete_package(cues=cues)})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("cue 2 starts 2.1s away from the source "
                      "cue", r.stdout)

    def test_drift_backwards_flags(self):
        cues = list(BASE_CUES)
        cues[2] = (8000 - 2100, 11000, "Three.")
        project = build_project(
            self.tmp,
            packages={"hi": complete_package(cues=cues)})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("cue 3 starts 2.1s", r.stdout)

    def test_title_exactly_100_passes(self):
        project = build_project(
            self.tmp, packages={
                "hi": complete_package(title="x" * 100)})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("100 characters (limit 100)", r.stdout)

    def test_title_101_flags(self):
        project = build_project(
            self.tmp, packages={
                "hi": complete_package(title="x" * 101)})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("101 characters — over the "
                      "100-character", r.stdout)

    def test_cue_count_gap_at_25_percent_passes(self):
        source = [(i * 4000, i * 4000 + 3000, f"Cue {i}")
                  for i in range(8)]
        target = source[:6]  # 6 of 8 -> gap 2 = exactly 25%
        project = build_project(
            self.tmp, source_cues=source,
            packages={"hi": complete_package(cues=target)})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("cue count differs from the source by 2 "
                      "(within the 25% tolerance)", r.stdout)

    def test_cue_count_gap_over_25_percent_flags(self):
        source = [(i * 4000, i * 4000 + 3000, f"Cue {i}")
                  for i in range(8)]
        target = source[:5]  # 5 of 8 -> gap 3 > 25%
        project = build_project(
            self.tmp, source_cues=source,
            packages={"hi": complete_package(cues=target)})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("5 cues vs 8 in the source", r.stdout)

    def test_missing_description_flags(self):
        pkg = complete_package()
        pkg["description.txt"] = None
        project = build_project(self.tmp, packages={"hi": pkg})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("description.txt", r.stdout)
        self.assertIn("PROBLEM: missing", r.stdout)

    def test_empty_thumbnail_flags(self):
        pkg = complete_package()
        pkg["thumbnail.txt"] = "  \n"
        project = build_project(self.tmp, packages={"hi": pkg})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("PROBLEM: the file is empty", r.stdout)

    def test_corrupt_target_subtitles_is_a_finding(self):
        pkg = complete_package()
        pkg["subtitles.srt"] = "this is not an srt file\n"
        project = build_project(self.tmp, packages={"hi": pkg})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("does not parse as SRT", r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_missing_language_folder_all_missing(self):
        project = build_project(self.tmp, packages={})
        r = self.run_check(project)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("INCOMPLETE (4 problem(s))", r.stdout)

    def test_root_override(self):
        # Package lives somewhere else; --root points at it.
        elsewhere = Path(self.tmp) / "elsewhere"
        (elsewhere / "hi").mkdir(parents=True)
        for name, text in complete_package().items():
            (elsewhere / "hi" / name).write_text(
                text, encoding="utf-8")
        project = build_project(self.tmp, packages={})
        r = run_cli("check", project, "--root", str(elsewhere))
        self.assertEqual(r.returncode, 0, r.stdout)


# ----------------------------------------------------------------------
# sheet
# ----------------------------------------------------------------------

class TestSheet(unittest.TestCase):
    def test_sheet_md_both_languages(self):
        out = run_cli("sheet", str(SAMPLE)).stdout
        self.assertEqual(out.count("# Translation sheet"), 2)
        self.assertIn("# Translation sheet — Hindi (hi)", out)
        self.assertIn("# Translation sheet — Punjabi (pa)",
                      out)

    def test_sheet_md_rows(self):
        out = run_cli("sheet", str(SAMPLE),
                      "--language", "hi").stdout
        self.assertIn("| 1 | title |", out)
        self.assertIn("| 4 | cue 1 | 00:00:00,000 --> "
                      "00:00:03,500 | Welcome back to the "
                      "channel. |  |", out)
        self.assertIn("| 9 | cue 6 |", out)

    def test_sheet_md_escapes_pipes(self):
        out = run_cli("sheet", str(SAMPLE),
                      "--language", "hi").stdout
        self.assertIn("Kelowna Trail Loop in Winter \\| Full "
                      "Ride", out)

    def test_sheet_language_filter(self):
        out = run_cli("sheet", str(SAMPLE),
                      "--language", "pa").stdout
        self.assertEqual(out.count("# Translation sheet"), 1)
        self.assertIn("Punjabi (pa)", out)

    def test_sheet_unknown_language_exit_2(self):
        r = run_cli("sheet", str(SAMPLE), "--language", "fr")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_sheet_csv_parses_and_counts(self):
        r = run_cli("sheet", str(SAMPLE), "--format", "csv",
                    "--language", "pa")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [ln for ln in r.stdout.splitlines()
                 if not ln.startswith("# ")]
        rows = list(csv.reader(io.StringIO("\n".join(lines))))
        self.assertEqual(rows[0],
                         ["n", "item", "timing", "source_en",
                          "target_pa"])
        self.assertEqual(len(rows), 10)  # header + 9 strings
        self.assertEqual(rows[1][1], "title")
        self.assertEqual(rows[4][1], "cue 1")
        self.assertEqual(rows[4][3],
                         "Welcome back to the channel.")
        self.assertTrue(all(row[4] == "" for row in rows[1:]))

    def test_sheet_json_rows(self):
        r = run_cli("sheet", str(SAMPLE), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(len(data["sheets"]), 2)
        rows = data["sheets"][0]["rows"]
        self.assertEqual(len(rows), 9)  # 3 strings + 6 cues
        self.assertEqual(rows[0]["item"], "title")
        self.assertEqual(rows[3]["item"], "cue 1")
        self.assertEqual(rows[3]["timing"],
                         "00:00:00,000 --> 00:00:03,500")
        self.assertTrue(all(row["target"] == ""
                            for row in rows))


# ----------------------------------------------------------------------
# errors: clean exit 2, {"error": ...} under --json, no tracebacks
# ----------------------------------------------------------------------

class TestErrors(TempDirCase):
    def assert_clean_error(self, r):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_missing_project_file(self):
        self.assert_clean_error(
            run_cli("check", str(Path(self.tmp) / "nope.json")))

    def test_malformed_project_json(self):
        bad = Path(self.tmp) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        self.assert_clean_error(run_cli("manifest", str(bad)))

    def test_project_not_an_object(self):
        bad = Path(self.tmp) / "list.json"
        bad.write_text("[1, 2]", encoding="utf-8")
        self.assert_clean_error(run_cli("manifest", str(bad)))

    def test_missing_targets(self):
        bad = Path(self.tmp) / "notargets.json"
        bad.write_text(json.dumps({
            "project": "X", "source_language": "en",
            "source_title": "T", "source_description": "D",
            "source_thumbnail_text": "TH",
            "source_subtitles": "source/en.srt"}),
            encoding="utf-8")
        self.assert_clean_error(run_cli("manifest", str(bad)))

    def test_duplicate_language_rejected(self):
        project = build_project(
            self.tmp, targets=[
                {"language": "hi", "name": "Hindi"},
                {"language": "hi", "name": "Hindi again"}])
        r = run_cli("manifest", project)
        self.assert_clean_error(r)
        self.assertIn("appears twice", r.stdout)

    def test_missing_source_subtitles(self):
        root = Path(self.tmp)
        (root / "project.json").write_text(json.dumps({
            "project": "X", "source_language": "en",
            "source_title": "T", "source_description": "D",
            "source_thumbnail_text": "TH",
            "source_subtitles": "source/gone.srt",
            "targets": [{"language": "hi", "name": "Hindi"}]}),
            encoding="utf-8")
        self.assert_clean_error(
            run_cli("check", str(root / "project.json")))

    def test_corrupt_source_subtitles_is_an_error(self):
        root = Path(self.tmp)
        (root / "source").mkdir()
        (root / "source" / "en.srt").write_text(
            "garbage\n", encoding="utf-8")
        (root / "project.json").write_text(json.dumps({
            "project": "X", "source_language": "en",
            "source_title": "T", "source_description": "D",
            "source_thumbnail_text": "TH",
            "source_subtitles": "source/en.srt",
            "targets": [{"language": "hi", "name": "Hindi"}]}),
            encoding="utf-8")
        self.assert_clean_error(
            run_cli("manifest", str(root / "project.json")))

    def test_json_error_shape(self):
        r = run_cli("check",
                    str(Path(self.tmp) / "nope.json"), "--json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("error", json.loads(r.stdout))

    def test_argparse_error_json_shape(self):
        r = run_cli("check", str(SAMPLE), "--bogus", "--json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("error", json.loads(r.stdout))

    def test_argparse_error_text_mode_no_json(self):
        r = run_cli("check", str(SAMPLE), "--bogus")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
