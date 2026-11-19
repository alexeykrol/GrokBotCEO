#!/usr/bin/env python3
"""
Tests for the license files of the package (legal tech requirements, group A, items 1-7a).

Stdlib only, no network. Checks that need the development repository (the legal drafts in
docs/legal/) are skipped in a published copy. Placeholders such as [OFFICIAL URL] are allowed here:
the release-time check (scripts/release-readiness.py in the development repo, run by
`scripts/publish.sh check`) fails while any remains.
"""
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent                      # the package root (release/)
DEV_LEGAL = ROOT_DIR.parent / "docs" / "legal"    # only in the development repository

LEGAL_FILES = ["LICENSE", "NOTICE", "COURSE-LICENSE.md", "TRADEMARKS.md", "LICENSE-MAP.md", "TERMS.md"]
BOT_TEXTS = ["bots/bot-maker/prompt.md", "bots/mentor/prompt.md", "bots/monitor/prompt.md",
             "bots/reminder/prompt.md", "bots/translator/prompt.md", "bots/main-grok/block.md"]
# The credit is taken from NOTICE (its indented "Based on ..." line), so the tests follow the URL
# once it is filled. Our own bot texts carry "<credit without 'Based on '> — BotCEO License 1.0, see NOTICE".
NOTICE_CREDIT = re.search(r"(?m)^\s+(Based on BotCEO by .+)$",
                          (ROOT_DIR / "NOTICE").read_text(encoding="utf-8")).group(1).strip()
CREDIT = NOTICE_CREDIT[len("Based on "):] + " — BotCEO License 1.0, see NOTICE"
LICENSE_ID = "LicenseRef-BotCEO-1.0"

# Item 2 (i). Sections 1-9 of LICENSE ("   1. Definitions." up to "   10. Attribution") equal sections
# 1-9 of the official Apache License 2.0 text with exactly two changes: "Sections 1 through 10" and
# the parenthetical "(an example is provided in the Appendix below)" removed. Pinned from the
# official file (sha256 OFFICIAL_SHA256), found locally on 2026-11-17; the transformation is
# re-checked against an official copy when one is available (APACHE_LICENSE_FILE or a known path).
OFFICIAL_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
SECTIONS_1_9_SHA256 = "1db5a4f616ac78ba9c6386d9a824819bd78ab3bbcd39641b7c1e3e975330579d"
OFFICIAL_CANDIDATES = ["/opt/homebrew/Cellar/tesseract/5.5.0/LICENSE",
                       "/usr/share/common-licenses/Apache-2.0"]
# Item 2, last sentence: the SHA-256 of the whole LICENSE file is pinned at release, after [YEAR] and
# [OFFICIAL URL] are filled. None until then; the release-time check refuses to publish with None.
LICENSE_SHA256 = "85cff45454d36da62e3cf98fc748e0f260401a60788db24e36efb0c14ad7bffa"


def sections_1_9(text):
    return text[text.index("   1. Definitions."):text.index("   10. Attribution")]


def official_sections_1_9(text):
    body = text[text.index("   1. Definitions."):text.index("   END OF TERMS AND CONDITIONS")]
    a = "and distribution as defined by Sections 1 through 9 of this document."
    b = ("      copyright notice that is included in or attached to the work\n"
         "      (an example is provided in the Appendix below).\n")
    if body.count(a) != 1 or body.count(b) != 1:
        raise ValueError("not the official Apache License 2.0 text")
    return body.replace(a, a.replace("1 through 9", "1 through 10")).replace(
        b, "      copyright notice that is included in or attached to the work.\n")


def first_licensed_release_in_terms():
    """The release named in TERMS.md §2 as the first licensed one (placeholder or filled value)."""
    terms = " ".join(read("TERMS.md").split())
    a = re.search(r"Bot Maker bot contained in releases before (.+?), and any other material", terms)
    b = re.search(r"Bot Maker is licensed starting with release (.+?), which contains", terms)
    assert a and b and a.group(1) == b.group(1), "TERMS.md §2 names the first licensed release twice, equally"
    return a.group(1)


def read(rel):
    return (ROOT_DIR / rel).read_text(encoding="utf-8")


def package_files():
    """Every file of the package, as shipped (no caches, no git, no local data of a test run)."""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT_DIR):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        for name in filenames:
            if name == ".DS_Store" or name.endswith(".pyc"):
                continue
            out.append(Path(dirpath, name).relative_to(ROOT_DIR).as_posix())
    return sorted(out)


def map_rows(text):
    """(patterns, governed-by) for every table row of LICENSE-MAP.md."""
    rows = []
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append((re.findall(r"`([^`]+)`", cells[0]), cells[2]))
    return rows


def matches(pattern, path):
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    if "/" not in pattern and "/" in path:
        return False
    return fnmatch.fnmatchcase(path, pattern) and path.count("/") == pattern.count("/")


class TestLegalFilesShipped(unittest.TestCase):
    """Item 1: six files in the package root, copied unchanged; no ADDITIONAL-PERMISSIONS.md."""

    def test_present(self):
        for name in LEGAL_FILES + ["TERMS-NOTICE.md"]:
            self.assertTrue((ROOT_DIR / name).is_file(), name)
        self.assertFalse((ROOT_DIR / "ADDITIONAL-PERMISSIONS.md").exists())

    @unittest.skipUnless((DEV_LEGAL / "release-files").is_dir(), "development repo only")
    def test_unchanged_copies_of_the_drafts(self):
        for name in LEGAL_FILES[:5]:
            with self.subTest(file=name):
                self.assertEqual(read(name), (DEV_LEGAL / "release-files" / name).read_text(encoding="utf-8"))
        terms = (DEV_LEGAL / "product-terms.md").read_text(encoding="utf-8")
        first, rest = terms.split("\n", 1)
        self.assertIn("Читать на русском", first, "the translation button is the first line of the draft")
        self.assertEqual(read("TERMS.md"), rest.lstrip("\n"), "TERMS.md = the draft without the button")
        self.assertNotIn("Читать на русском", read("TERMS.md"))

    def test_listed_in_manifest(self):
        listed = {line.split("  ", 1)[1] for line in read("MANIFEST.sha256").splitlines() if line}
        missing = [n for n in LEGAL_FILES + ["TERMS-NOTICE.md", "TERMS-NOTICE.ru.md"] if f"release/{n}" not in listed]
        self.assertEqual(missing, [], "run scripts/manifest.py gen")


class TestLicenseIntegrity(unittest.TestCase):
    """Item 2."""

    def setUp(self):
        self.text = read("LICENSE")

    def test_sections_1_to_9_are_the_pinned_apache_text(self):
        self.assertEqual(hashlib.sha256(sections_1_9(self.text).encode("utf-8")).hexdigest(), SECTIONS_1_9_SHA256)

    def test_pin_against_an_official_copy_if_available(self):
        paths = [os.environ.get("APACHE_LICENSE_FILE", "")] + OFFICIAL_CANDIDATES
        official = next((Path(p) for p in paths if p and Path(p).is_file()
                         and hashlib.sha256(Path(p).read_bytes()).hexdigest() == OFFICIAL_SHA256), None)
        if official is None:
            self.skipTest("no local copy of the official Apache License 2.0 text")
        expected = official_sections_1_9(official.read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(expected.encode("utf-8")).hexdigest(), SECTIONS_1_9_SHA256)
        self.assertEqual(sections_1_9(self.text), expected)

    def test_name_and_no_apache_identity(self):
        head = self.text[:self.text.index("   1. Definitions.")]
        self.assertIn("BotCEO License", head)
        self.assertIn("Version 1.0", head)
        self.assertIn("This license is not the Apache License.", head)
        self.assertIn("   10. Attribution (additional term).", self.text)
        self.assertNotIn("APPENDIX", self.text)

    @unittest.skipUnless((DEV_LEGAL / "release-files" / "LICENSE").is_file(), "development repo only")
    def test_header_and_section_10_equal_the_draft(self):
        draft = (DEV_LEGAL / "release-files" / "LICENSE").read_text(encoding="utf-8")
        cut = lambda t: (t[:t.index("   1. Definitions.")], t[t.index("   10. Attribution"):])
        self.assertEqual(cut(self.text), cut(draft))

    def test_pinned_file_hash_once_released(self):
        if LICENSE_SHA256 is None:
            self.skipTest("pinned at release, after [YEAR] and [OFFICIAL URL] are filled")
        self.assertEqual(hashlib.sha256((ROOT_DIR / "LICENSE").read_bytes()).hexdigest(), LICENSE_SHA256)


class TestLicenseMap(unittest.TestCase):
    """Item 4: every file of the package falls under exactly one row or a default rule."""

    def setUp(self):
        self.rows = map_rows(read("LICENSE-MAP.md"))
        self.files = package_files()

    def test_rows_parsed(self):
        self.assertGreaterEqual(len(self.rows), 10)
        governed = {g.split(":")[0] for _, g in self.rows}
        self.assertTrue({"Open part", "Course Materials", "may be copied unchanged"} <= governed)

    def test_every_file_at_most_one_row(self):
        multi = []
        for path in self.files:
            hit = [p for pats, _ in self.rows for p in pats if matches(p, path)]
            if len(hit) > 1:
                multi.append(f"{path}: {hit}")
        self.assertEqual(multi, [])

    def test_every_row_names_real_files(self):
        stale = [p for pats, _ in self.rows for p in pats if not any(matches(p, f) for f in self.files)]
        self.assertEqual(stale, [], "a row of LICENSE-MAP.md names nothing in the package")

    def test_course_files_are_course_materials_unless_listed_as_engine(self):
        engine = [p for pats, g in self.rows if g.startswith("Open part") for p in pats if p.startswith("course/")]
        self.assertEqual(sorted(engine), sorted(["course/progress.py", "course/kb-box/**", "course/MENTOR-RUNTIME.md",
                                                 "course/SCHEMA.md", "course/EVENT-SCHEMA.md"]))
        for path in self.files:
            if path.startswith(("course/lessons/", "course/sections/", "course/kb/", "course/kb-markup/", "teaching/")):
                hit = [g for pats, g in self.rows for p in pats if matches(p, path)]
                self.assertTrue(hit and hit[0].startswith("Course Materials"), path)

    def test_legal_texts_row_covers_the_notice(self):
        legal = [p for pats, g in self.rows if g.startswith("may be copied") for p in pats]
        for name in LEGAL_FILES + ["TERMS-NOTICE.md", "TERMS-NOTICE.ru.md"]:
            self.assertTrue(any(matches(p, name) for p in legal), name)


class TestReadmeLicense(unittest.TestCase):
    """Item 5 (and the wording rule of group A)."""

    def test_sections(self):
        for name in ("README.md", "README.ru.md"):
            text = read(name)
            with self.subTest(readme=name):
                lic = text[text.index("\n## Л" if name.endswith(".ru.md") else "\n## License"):]
                self.assertNotIn("Not chosen yet", text)
                self.assertNotIn("Пока не выбрана", text)
                self.assertIn("BotCEO License 1.0", lic)
                self.assertIn(NOTICE_CREDIT, lic)
                for link in LEGAL_FILES + ["TERMS-NOTICE.md"]:
                    self.assertIn(f"]({link})", lic, link)
                # Same wording as terms §2, with whatever value the release names (placeholder or filled).
                first = first_licensed_release_in_terms()
                m = re.search(r"The licenses and terms of the latest release are also offered for the earlier releases, "
                              r"including those published as GrokBotCEO\. Exception: the Bot Maker bot in releases before "
                              r"(.+?), and any other material not listed in the latest LICENSE-MAP\.md, are not "
                              r"licensed\. Bot Maker is licensed starting with release (.+?)\.(?:\s|$)",
                              " ".join(lic.split()))
                self.assertIsNotNone(m, "the sentence of terms §2 is missing")
                self.assertEqual((m.group(1), m.group(2)), (first, first), "the release named must match TERMS.md §2")
        self.assertIn("We do not accept outside pull requests at this time.", read("README.md"))

    def test_never_open_source_or_apache_identity(self):
        bad = re.compile(r"open[- ]source|apache-2\.0|apache with attribution|apache license 2\.0 \(", re.I)
        names = ["README.md", "README.ru.md", "ONBOARDING.md", "ONBOARDING.ru.md", "NOTICE", "TERMS.md",
                 "TERMS-NOTICE.md", "TERMS-NOTICE.ru.md", "LICENSE-MAP.md", "TRADEMARKS.md", "COURSE-LICENSE.md"]
        names += [p for p in package_files() if p.startswith("bots/")]
        hits = [n for n in names if bad.search(read(n))]
        self.assertEqual(hits, [])


class TestManifestsLicenseField(unittest.TestCase):
    """Item 6: any license field in a JSON manifest is the BotCEO identifier."""

    def test_license_fields(self):
        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "license":
                        yield v
                    yield from walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from walk(v)
        for path in package_files():
            if path.endswith(".json") and not path.startswith(("course/kb/", "course/sections/")) \
                    and path != "course/course.json":
                for value in walk(json.loads(read(path))):
                    self.assertTrue(str(value).startswith(LICENSE_ID), f"{path}: {value}")
                    self.assertTrue((ROOT_DIR / Path(path).parent / "LICENSE").is_file()
                                    or Path(path).parent == Path("."), path)


class TestCreditTravelsWithTheBots(unittest.TestCase):
    """Item 7: every published bot text ends with the credit line, also after the build."""

    def test_source_texts(self):
        for rel in BOT_TEXTS:
            with self.subTest(bot=rel):
                self.assertEqual(read(rel).rstrip("\n").splitlines()[-1], CREDIT)

    def test_built_texts(self):
        cfg = {"WORKSPACE_PATH": "/w", "BOT_MAKER_BOT": "Bot Maker", "MENTOR_BOT": "Mentor",
               "REMINDER_BOT": "Reminder", "TRANSLATOR_BOT": "Translator", "MONITOR_BOT": "Monitor"}
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "config.json"
            conf.write_text(json.dumps(cfg))
            out = Path(tmp) / "out"
            r = subprocess.run([sys.executable, "-B", str(SCRIPT_DIR / "bot-payload-compiler.py"), "build",
                                "--config", str(conf), "--bots", "bot-maker,mentor,reminder,translator,monitor",
                                "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            for bot in ("bot-maker", "mentor", "reminder", "translator", "monitor"):
                desc = json.loads((out / f"{bot}.payload.json").read_text(encoding="utf-8"))["description"]
                self.assertTrue(desc.endswith(CREDIT), bot)


class TestRename(unittest.TestCase):
    """Item 7a: GrokBotCEO -> BotCEO in titles and texts; the old name stays only where code, paths,
    the repository URL, the git identity of installed repos or the history of earlier releases need it."""

    def test_titles(self):
        self.assertTrue(read("README.md").startswith("# BotCEO\n"))
        self.assertTrue(read("README.ru.md").startswith("# BotCEO\n"))
        self.assertTrue(read("ONBOARDING.md").startswith("# Getting Started with BotCEO\n"))
        self.assertTrue(read("ONBOARDING.ru.md").startswith("# Как начать работу с BotCEO\n"))

    def test_install_and_update_commands(self):
        for name in ("README.md", "README.ru.md", "ONBOARDING.md", "ONBOARDING.ru.md"):
            self.assertIn("Install BotCEO for me.", read(name))
            self.assertNotIn("Install GrokBotCEO", read(name))
        self.assertIn("Update BotCEO for me.", read("README.md"))

    def test_old_name_only_where_allowed(self):
        allowed = re.compile(r"github\.com/[\w-]+/GrokBotCEO|GrokBotCEO bots|published as\s+GrokBotCEO|"
                             r"выпущенных (?:как|под названием)\s+GrokBotCEO|«обнови GrokBotCEO»|\"update GrokBotCEO\"|"
                             r"<home>/GrokBotCEO")
        docs = ["README.md", "README.ru.md", "ONBOARDING.md", "ONBOARDING.ru.md", "LOADING-INSTRUCTIONS.md",
                "UPDATE.md", "LOCAL-COPY.md", "TERMS-NOTICE.md", "teaching/customization.md",
                "company-structure/README.md", "company-structure/functions/bot-changes.md",
                "bots/mentor/prompt.md", "bots/reminder/prompt.md", "bots/monitor/prompt.md",
                "bots/translator/prompt.md", "bots/bot-maker/README.md", "bots/main-grok/README.md"]
        hits = []
        for name in docs:
            for no, line in enumerate(read(name).splitlines(), 1):
                if "GrokBotCEO" in allowed.sub("", line):
                    hits.append(f"{name}:{no}")
        self.assertEqual(hits, [])

    def test_grok_bot_stays_the_platform_name(self):
        self.assertIn("Grok Bot", read("README.md"))
        self.assertIn("BotCEO works with Grok Bot", read("TRADEMARKS.md"))


READINESS = ROOT_DIR.parent / "scripts" / "release-readiness.py"   # development repo only
FILL = {"[OFFICIAL URL]": "https://botceo.example/", "[YEAR]": "2026", "[EFFECTIVE DATE]": "2026-12-01",
        "[RELEASE VERSION]": "0.3.0", "[TERMS URL]": "https://botceo.example/terms",
        "[PRIVACY URL]": "https://botceo.example/privacy", "[FIRST LICENSED RELEASE]": "0.3.0",
        "[POSTAL ADDRESS]": "PO Box 100, Example City, CA 90000, USA",
        "[LIST OF COURSE NAMES AND LOGOS — to be completed.]": "Course names: the BotCEO course."}


def fill_legal_fields(root: Path):
    """What the owner does before a release: every legal placeholder gets a value; the blocks that do
    not apply to this release are removed; the manifest and the LICENSE pin follow."""
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix == ".py" or "__pycache__" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = text
        for token, value in FILL.items():
            new = new.replace(token, value)
        if p.name == "NOTICE":
            new = re.sub(r"\n\n\[THIRD-PARTY CREDITS[^\]]*\]\n", "\n", new)
        if p.name == "TERMS.md":
            new = re.sub(r"\n\[TELEMETRY — .*?\"\]\n", "\n", new, flags=re.S)
        if new != text:
            p.write_text(new, encoding="utf-8")
    rehash_manifest(root)
    test = root / "scripts" / "test-legal.py"
    pin = hashlib.sha256((root / "LICENSE").read_bytes()).hexdigest()
    test.write_text(test.read_text(encoding="utf-8").replace("\nLICENSE_SHA256 = None\n",
                                                             f'\nLICENSE_SHA256 = "{pin}"\n', 1), encoding="utf-8")


def rehash_manifest(root: Path):
    lines = []
    for line in (root / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        digest, path = line.split("  ", 1)
        f = root / path.split("/", 1)[1] if path.startswith("release/") else None
        if f is not None and f.is_file():
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path}")
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


@unittest.skipIf(os.environ.get("LEGAL_FIXTURE") == "1", "inside the filled fixture itself")
@unittest.skipUnless(READINESS.is_file(), "development repo only (scripts/release-readiness.py)")
class TestFilledRelease(unittest.TestCase):
    """P1 (Codex review): filling the legal fields must not break the tests; the release-time check
    passes on a filled copy and fails again as soon as one placeholder is back."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.rel = cls.tmp / "release"
        shutil.copytree(ROOT_DIR, cls.rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        fill_legal_fields(cls.rel)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def readiness(self):
        return subprocess.run([sys.executable, "-B", "-I", str(READINESS), "--release", str(self.rel)],
                              capture_output=True, text=True)

    def test_1_legal_and_terms_tests_pass_on_the_filled_copy(self):
        env = dict(os.environ, LEGAL_FIXTURE="1")
        for name in ("test-legal.py", "test-terms.py"):
            with self.subTest(test=name):
                r = subprocess.run([sys.executable, "-B", str(self.rel / "scripts" / name)], capture_output=True,
                                   text=True, env=env, timeout=600)
                self.assertEqual(r.returncode, 0, r.stderr[-3000:])

    def test_2_readiness_passes_on_the_filled_copy(self):
        r = self.readiness()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("release-readiness: PASS", r.stdout)

    def test_3_one_placeholder_back_fails(self):
        for rel, token in (("NOTICE", "[YEAR]"), ("bots/mentor/prompt.md", "[OFFICIAL URL]")):
            with self.subTest(file=rel):
                p = self.rel / rel
                before = p.read_text(encoding="utf-8")
                p.write_text(before + token + "\n", encoding="utf-8")
                rehash_manifest(self.rel)
                try:
                    r = self.readiness()
                    self.assertEqual(r.returncode, 1, r.stdout)
                    self.assertIn(f"{rel}", r.stdout)
                    self.assertIn(f"placeholder {token}", r.stdout)
                finally:
                    p.write_text(before, encoding="utf-8")
                    rehash_manifest(self.rel)
        self.assertEqual(self.readiness().returncode, 0)


if __name__ == "__main__":
    unittest.main()
