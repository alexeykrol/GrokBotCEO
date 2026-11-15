#!/usr/bin/env python3
"""Position balance of the correct option over every shown quiz situation (P2b §5) and its lint.

Algorithm p2b-balance-1 (pure, deterministic, always terminates):
  1. Units: every shown situation, in course order (step order; inside a step the primary situation,
     then the extra situations in list order). The unit id is the scenario_id (the primary situation
     and S….b are separate units).
  2. Targets: n // 3 per position, the remainder one each in the order a, b, c.
  3. Unit by unit: among the positions whose remaining target is > 0, a position that would make a run
     of 3 equal positions in a row is excluded if another position with remaining > 0 exists (else it
     is taken with a warning); of the rest the one with the largest remaining target wins; a tie goes
     to the smaller sha256("p2b-balance-1|" + scenario_id + "|" + letter) (hex string order).
  4. Permutation: the correct option moves to the chosen position, the wrong options keep their
     relative order.
The assignment depends only on the unit ids and their order, never on the current positions, so a
second run on a balanced course gives the same result.

Lint (warnings only, never a build failure): share of a position outside [0.25, 0.42], a run of 3,
share of "the correct option is strictly the longest" above 0.5 (a tie for the longest is not "the
longest"). Denominators: all shown situations; the report also gives the primaries alone.

    quiz-balance.py report [--course FILE]          lint of the course + the planned assignment
    quiz-balance.py apply --course-dir DIR          rewrite DIR/sections/*.json with the assignment
                                                    (source files; then run course-merge.py)
Stdlib only.
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

VERSION = "p2b-balance-1"
LETTERS = "abc"
SHARE_LOW, SHARE_HIGH = 0.25, 0.42
LONGEST_MAX = 0.5
RUN = 3
COURSE_FILE = Path(__file__).resolve().parent.parent / "course" / "course.json"


def tie_key(unit_id, letter):
    return hashlib.sha256(f"{VERSION}|{unit_id}|{letter}".encode("utf-8")).hexdigest()


def targets(n):
    q, r = divmod(n, len(LETTERS))
    return {L: q + (1 if i < r else 0) for i, L in enumerate(LETTERS)}


def assign(unit_ids):
    """[(unit_id, letter)], warnings. Deterministic; terminates for every n (the targets sum to n)."""
    remaining = targets(len(unit_ids))
    out, warnings = [], []
    for u in unit_ids:
        cands = [L for L in LETTERS if remaining[L] > 0]
        runs = {L for L in cands if len(out) >= RUN - 1 and all(x[1] == L for x in out[-(RUN - 1):])}
        pool = [L for L in cands if L not in runs] or cands
        if set(pool) & runs:
            warnings.append(f"{u}: only position {pool} left, a run of {RUN} is unavoidable")
        best = min(pool, key=lambda L: (-remaining[L], tie_key(u, L)))
        remaining[best] -= 1
        out.append((u, best))
    return out, warnings


def permute(options, letter):
    """The correct option at the position of letter; the wrong ones keep their relative order."""
    right = [o for o in options if o.get("correct")]
    wrong = [o for o in options if not o.get("correct")]
    if len(right) != 1 or len(options) != len(LETTERS):
        raise ValueError("need exactly 3 options with one correct")
    i = LETTERS.index(letter)
    return wrong[:i] + right + wrong[i:]


def iter_steps(course):
    for sec in course["sections"]:
        for les in sec["lessons"]:
            for st in les["steps"]:
                yield st


def situations(course):
    """[(unit_id, step_id, is_primary, options-list-object)] of every shown quiz situation, in course order."""
    out = []
    for st in iter_steps(course):
        if st.get("type") != "quiz":
            continue
        out.append((st.get("primary_scenario_id") or st["id"], st["id"], True, st["options"]))
        for x in st.get("situations") or []:
            out.append((x["id"], st["id"], False, x["options"]))
    return out


def correct_pos(options):
    return next((LETTERS[i] for i, o in enumerate(options) if o.get("correct")), None)


def longest_kind(options):
    """'longest' if the correct option is strictly the longest, 'tie' if it shares the maximum, else 'no'."""
    lens = [len(o.get("text", "")) for o in options]
    c = next(i for i, o in enumerate(options) if o.get("correct"))
    m = max(lens)
    if lens[c] < m:
        return "no"
    return "longest" if lens.count(m) == 1 else "tie"


def lint(course):
    """Warnings (strings) and the numbers over all shown situations and over the primaries alone."""
    sits = situations(course)

    def stats(items):
        n = len(items)
        pos = [correct_pos(opts) for _, _, _, opts in items]
        counts = {L: pos.count(L) for L in LETTERS}
        kinds = [longest_kind(opts) for _, _, _, opts in items]
        runs = [items[i][0] for i in range(RUN - 1, n) if len(set(pos[i - RUN + 1:i + 1])) == 1]
        return {"n": n, "counts": counts, "shares": {L: (round(counts[L] / n, 4) if n else None) for L in LETTERS},
                "longest": kinds.count("longest"), "tie": kinds.count("tie"),
                "longest_share": round(kinds.count("longest") / n, 4) if n else None, "runs_end_at": runs}

    all_, prim = stats(sits), stats([x for x in sits if x[2]])
    warnings = []
    if all_["n"]:
        for L in LETTERS:
            sh = all_["shares"][L]
            if not SHARE_LOW <= sh <= SHARE_HIGH:
                warnings.append(f"position {L}: share {sh} outside [{SHARE_LOW}; {SHARE_HIGH}] of {all_['n']} situations")
        for u in all_["runs_end_at"]:
            warnings.append(f"run of {RUN} equal positions ends at {u}")
        if all_["longest_share"] > LONGEST_MAX:
            warnings.append(f"correct option strictly the longest in {all_['longest']} of {all_['n']} "
                            f"({all_['longest_share']} > {LONGEST_MAX}); ties {all_['tie']}")
    return warnings, {"all": all_, "primaries": prim}


def plan(course):
    units = [u for u, _, _, _ in situations(course)]
    return assign(units)


def apply_to_sections(course_dir: Path):
    """Rewrite course_dir/sections/*.json with the assignment over the merged course order."""
    sec_dir = Path(course_dir) / "sections"
    files = sorted(sec_dir.glob("S*.json"), key=lambda f: int(f.stem[1:]))
    docs = {f: json.loads(f.read_text(encoding="utf-8")) for f in files}
    merged = {"sections": [docs[f] for f in files]}
    assignment, warnings = plan(merged)
    where = {u: opts for u, _, _, opts in situations(merged)}
    for u, letter in assignment:
        opts = where[u]
        opts[:] = permute(list(opts), letter)
    for f, d in docs.items():
        fd, tmp = tempfile.mkstemp(dir=f.parent, suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, f)
    return assignment, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("--course", type=Path, default=COURSE_FILE)
    a = sub.add_parser("apply")
    a.add_argument("--course-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "report":
        course = json.loads(args.course.read_text(encoding="utf-8"))["course"]
        warnings, numbers = lint(course)
        assignment, aw = plan(course)
        planned = {L: sum(1 for _, x in assignment if x == L) for L in LETTERS}
        print(json.dumps({"algorithm": VERSION, "lint_warnings": warnings, "numbers": numbers,
                          "planned_counts": planned, "planned_warnings": aw,
                          "assignment": [{"unit": u, "position": x} for u, x in assignment]},
                         ensure_ascii=False, indent=1))
        return 0
    assignment, warnings = apply_to_sections(args.course_dir)
    print(json.dumps({"algorithm": VERSION, "applied": len(assignment), "warnings": warnings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
