#!/usr/bin/env python3
"""terms.py - the terms notice at install and update, and the local record of its acceptance.

Legal requirements B-8..B-13 (docs: TERMS-NOTICE.md). Bookkeeping only: the bot shows what `show`
prints and passes the user's exact answer to `accept`; this script decides whether that answer is an
acceptance and writes the record. Stdlib only. No network: the record never leaves the bot computer.

Commands (every one prints one JSON object on stdout):

  show    --release DIR [--locale LL] [--mode install|update]
          the notice to show verbatim: {"text", "locale", "sha256", "terms_version",
          "notice_version", "yes_answers", "no_answer"}. The text is in LL only when a reviewed copy
          exists (TERMS-NOTICE.<LL>.md with "Status: reviewed"); otherwise English. The answer
          labels are fixed per language (English for a language without fixed labels).
  accept  --release DIR --record FILE --answer WORDS [--locale LL] [--mode install|update]
          exit 0 and write FILE only if WORDS is exactly one of the "yes" answers of `show` (case,
          surrounding spaces and one final "." or "!" ignored; in update mode the yes may carry the
          ticked numbers: "Yes, and also 1, 3" / "Да, и ещё 1, 3"). Anything else - vague, blanket,
          a different language's yes, silence - exit 2, nothing written.
  check   --release DIR --record FILE
          {"show": true|false, "reason"}: true when there is no valid record for the terms version
          and notice version of DIR (update: show the notice again and take a new acceptance).
  require --release DIR --record FILE
          exit 0 only if FILE is a valid acceptance of DIR's terms; else exit 2. Install step 7 and
          update step 8 run it before anything is created or changed.

Record (FILE, JSON): terms_version, notice_version, notice_sha256 (of the exact text shown), locale
(of the text shown), ui_locale, accepted_at (UTC), release_version, mode, answer (the user's words).
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

NOTICE = "TERMS-NOTICE.md"
TERMS = "TERMS.md"
BEGIN = "<!-- notice:begin -->"
END = "<!-- notice:end -->"
DEFAULT_LOCALE = "en"

# Fixed answer labels per language: (install yes answers, update yes answer, no answer).
ANSWERS = {
    "en": (("Yes, with routines", "Yes, without routines"), "Yes", "No"),
    "ru": (("Да, с рутинами", "Да, без рутин"), "Да", "Нет"),
}
UPDATE_TICKS = {"en": "and also", "ru": "и ещё"}
RECORD_FIELDS = ("terms_version", "notice_version", "notice_sha256", "locale", "ui_locale",
                 "accepted_at", "release_version", "mode", "answer")


class TermsError(Exception):
    pass


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TermsError(f"cannot read {path.name}: {exc.strerror or exc}")


def notice_body(text: str, name: str) -> str:
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise TermsError(f"{name}: exactly one {BEGIN} and one {END} expected")
    body = text.split(BEGIN, 1)[1].split(END, 1)[0].strip()
    if not body:
        raise TermsError(f"{name}: empty notice")
    return body


def _field(text: str, label: str, name: str) -> str:
    m = re.search(r"^" + re.escape(label) + r":?\s*(\S+)", text, re.M)
    if not m:
        raise TermsError(f"{name}: no '{label}' line")
    return m.group(1).rstrip("·").strip()


def terms_version(release: Path) -> str:
    m = re.search(r"^Version (\d+) ·", _read(release / TERMS), re.M)
    if not m:
        raise TermsError(f"{TERMS}: no 'Version N ·' line")
    return m.group(1)


def norm_locale(locale) -> str:
    loc = (locale or DEFAULT_LOCALE).strip().lower().replace("_", "-").split("-")[0]
    return loc if re.fullmatch(r"[a-z]{2,3}", loc) else DEFAULT_LOCALE


def notice(release: Path, locale=None) -> dict:
    """The notice for the user's language: a reviewed translation, else English."""
    en_text = _read(release / NOTICE)
    version = _field(en_text, "Notice version", NOTICE)
    shown, body = DEFAULT_LOCALE, notice_body(en_text, NOTICE)
    loc = norm_locale(locale)
    if loc != DEFAULT_LOCALE:
        path = release / f"TERMS-NOTICE.{loc}.md"
        if path.is_file():
            tr = _read(path)
            status = re.search(r"^Status:\s*(\w+)", tr, re.M)
            tr_version = re.search(r"Notice version:\s*(\S+)", tr)
            if status and status.group(1) == "reviewed" and tr_version and \
                    tr_version.group(1).rstrip("·).") == version:
                shown, body = loc, notice_body(tr, path.name)
    return {"text": body, "locale": shown, "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "notice_version": version, "terms_version": terms_version(release)}


def answers(locale, mode: str) -> dict:
    loc = norm_locale(locale)
    install_yes, update_yes, no = ANSWERS.get(loc, ANSWERS[DEFAULT_LOCALE])
    return {"yes_answers": list(install_yes) if mode == "install" else [update_yes], "no_answer": no}


def _canon(words: str) -> str:
    s = re.sub(r"\s+", " ", (words or "").strip())
    if s[-1:] in (".", "!"):
        s = s[:-1].rstrip()
    return s.casefold()


def is_acceptance(words: str, locale, mode: str) -> bool:
    """Only the exact labels of the form (the user's language or English). Never inferred."""
    said = _canon(words)
    if not said:
        return False
    for loc in dict.fromkeys((norm_locale(locale), DEFAULT_LOCALE)):
        if loc not in ANSWERS:
            continue
        install_yes, update_yes, _ = ANSWERS[loc]
        if mode == "install":
            if said in {_canon(a) for a in install_yes}:
                return True
        else:
            yes = _canon(update_yes)
            if said == yes:
                return True
            ticks = re.escape(UPDATE_TICKS[loc].casefold())
            if re.fullmatch(re.escape(yes) + r", " + ticks + r" \d+( ?, ?\d+)*", said):
                return True
    return False


def _release_version(release: Path) -> str:
    return _read(release / "VERSION").strip()


def write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".terms-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def accept(release: Path, record_path: Path, words: str, locale=None, mode="install", now=None) -> dict:
    if not is_acceptance(words, locale, mode):
        return {"accepted": False, "reason": "not one of the exact yes answers of the form; ask the same "
                                             "form again and record nothing"}
    shown = notice(release, locale)
    when = now or datetime.datetime.now(datetime.timezone.utc)
    record = {"terms_version": shown["terms_version"], "notice_version": shown["notice_version"],
              "notice_sha256": shown["sha256"], "locale": shown["locale"], "ui_locale": norm_locale(locale),
              "accepted_at": when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "release_version": _release_version(release), "mode": mode, "answer": words}
    write_record(record_path, record)
    return {"accepted": True, "record": str(record_path)}


def validate(release: Path, record_path: Path) -> str:
    """'' if the record is a valid acceptance of this release's terms, else the reason."""
    if not record_path.is_file():
        return "no acceptance recorded"
    try:
        rec = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "the acceptance record cannot be read"
    if not isinstance(rec, dict) or any(k not in rec for k in RECORD_FIELDS):
        return "the acceptance record is incomplete"
    cur = notice(release, rec.get("locale"))
    if str(rec["terms_version"]) != cur["terms_version"]:
        return f"terms version changed ({rec['terms_version']} -> {cur['terms_version']})"
    if str(rec["notice_version"]) != cur["notice_version"]:
        return f"notice version changed ({rec['notice_version']} -> {cur['notice_version']})"
    if rec["locale"] != cur["locale"] or rec["notice_sha256"] != cur["sha256"]:
        return "the recorded notice is not the text this release shows"
    if not is_acceptance(str(rec["answer"]), rec.get("ui_locale"), rec.get("mode", "install")):
        return "the recorded answer is not an acceptance"
    return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BotCEO terms notice and its local acceptance record")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "accept", "check", "require"):
        p = sub.add_parser(name)
        p.add_argument("--release", type=Path, required=True)
        if name in ("show", "accept"):
            p.add_argument("--locale", default=DEFAULT_LOCALE)
            p.add_argument("--mode", choices=("install", "update"), default="install")
        if name != "show":
            p.add_argument("--record", type=Path, required=True)
        if name == "accept":
            p.add_argument("--answer", required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "show":
            out = notice(args.release, args.locale)
            out.update(answers(args.locale, args.mode))
            code = 0
        elif args.cmd == "accept":
            out = accept(args.release, args.record, args.answer, args.locale, args.mode)
            code = 0 if out["accepted"] else 2
        else:
            reason = validate(args.release, args.record)
            if args.cmd == "check":
                out, code = {"show": bool(reason), "reason": reason or "accepted"}, 0
            else:
                out, code = {"ok": not reason, "reason": reason or "accepted"}, (2 if reason else 0)
    except TermsError as exc:
        out, code = {"error": str(exc)}, 1
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
