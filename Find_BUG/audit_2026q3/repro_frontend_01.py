#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.2.1 / defect 01.

Target: cypyc/parser/preprocessor.py:39-50  (Preprocessor._read_include_file)

Claim: #include filenames are neither validated nor normalised.  A filename
containing ``..`` (or an absolute path) escapes the configured include search
root and any file reachable by the process is opened and inlined verbatim.
Expected behaviour: an explicit error, nothing read.

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)

from cypyc.parser.preprocessor import Preprocessor  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "d01")
SEARCH_ROOT = os.path.join(FIX, "inc", "incroot")          # configured include path
MARKER_OUTSIDE = os.path.join(FIX, "OUTSIDE_MARKER.txt")    # 2 levels above SEARCH_ROOT
MARKER_ABS = os.path.join(FIX, "ABSOLUTE_MARKER.txt")       # anywhere on disk, no relation
MARKER_CWD = os.path.join(FIX, "cwdrel", "CWD_MARKER.txt")  # reached via CWD-relative read
LEGIT = os.path.join(SEARCH_ROOT, "legit.inc")

MARKER_OUTSIDE_TEXT = "TOP-SECRET-OUTSIDE-ROOT-LINE-4D7A1\n"
MARKER_ABS_TEXT = "TOP-SECRET-ABSOLUTE-PATH-9C3F2\n"
MARKER_CWD_TEXT = "TOP-SECRET-CWD-RELATIVE-B8E50\n"
LEGIT_TEXT = "let legit_var: int = 1\n"


def setup():
    for d in (SEARCH_ROOT, os.path.join(FIX, "cwdrel")):
        os.makedirs(d, exist_ok=True)
    for path, text in ((MARKER_OUTSIDE, MARKER_OUTSIDE_TEXT),
                       (MARKER_ABS, MARKER_ABS_TEXT),
                       (MARKER_CWD, MARKER_CWD_TEXT),
                       (LEGIT, LEGIT_TEXT)):
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)


def run_case(label, source, include_paths, cwd=None):
    """Feed `source` through the real preprocessor; report error / inlined text."""
    pp = Preprocessor()
    pp.set_include_paths(include_paths)
    old = os.getcwd()
    if cwd:
        os.chdir(cwd)
    try:
        try:
            out = pp.process(source)
            error = None
        except Exception as exc:                                   # noqa: BLE001
            out, error = "", "%s: %s" % (type(exc).__name__, exc)
    finally:
        os.chdir(old)
    leaked = [name for name, txt in (("OUTSIDE", MARKER_OUTSIDE_TEXT.strip()),
                                     ("ABSOLUTE", MARKER_ABS_TEXT.strip()),
                                     ("CWD-RELATIVE", MARKER_CWD_TEXT.strip()))
              if txt in out]
    print("  %-26s include=%-34r raised=%-28s leaked=%s" % (
        label, source.strip(), error or "NO ERROR", leaked or "-"))
    return out, error, leaked


def main():
    setup()
    fwd = "../" * 2 + "OUTSIDE_MARKER.txt"
    back = ".." + os.sep + ".." + os.sep + "OUTSIDE_MARKER.txt"
    print("=" * 78)
    print("T0r61.2.1 / defect 01 - cypyc/parser/preprocessor.py:39-50 include escape")
    print("=" * 78)
    print("include search root : %s" % SEARCH_ROOT)
    print("marker (outside root): %s" % MARKER_OUTSIDE)
    print("marker content       : %r" % MARKER_OUTSIDE_TEXT.strip())
    print()
    print("cases (all through Preprocessor.process, the API used by cypy_hook/hook.py:91):")

    hits = 0

    # 0) control: a legitimate include inside the search root must keep working
    out, err, _ = run_case("control: in-root include", '#include <legit.inc>\n', [SEARCH_ROOT])
    control_ok = (LEGIT_TEXT.strip() in out) and err is None
    print("     -> in-root include inlined=%s (normal behaviour baseline)" % control_ok)

    # 1) forward-slash ../ escape through the include search path
    out, err, leaked = run_case("escape: ../../ relative", '#include <%s>\n' % fwd, [SEARCH_ROOT])
    if leaked and err is None:
        hits += 1
        print("     -> INLINED OUTSIDE-ROOT FILE CONTENT: %r" %
              [ln for ln in out.splitlines() if ln.strip()])

    # 2) same, with Windows separators
    out, err, leaked = run_case("escape: ..\\..\\ (win)", '#include <%s>\n' % back, [SEARCH_ROOT])
    if leaked and err is None:
        hits += 1

    # 3) quoted form ("..." instead of <...>)
    out, err, leaked = run_case('escape: quoted "../../x"', '#include "%s"\n' % fwd, [SEARCH_ROOT])
    if leaked and err is None:
        hits += 1

    # 4) absolute path, no include path configured -> fallback open(filename)
    out, err, leaked = run_case("escape: absolute path",
                                '#include <%s>\n' % MARKER_ABS.replace("\\", "/"), [])
    if MARKER_ABS_TEXT.strip() in out and err is None:
        hits += 1

    # 5) CWD-relative fallback read (line 46-48: open(filename) as typed)
    out, err, leaked = run_case("escape: CWD-relative",
                                '#include <%s>\n' % os.path.relpath(MARKER_CWD, FIX).replace("\\", "/"),
                                [SEARCH_ROOT], cwd=FIX)
    if MARKER_CWD_TEXT.strip() in out and err is None:
        hits += 1

    # 6) missing file is silently ignored (no diagnostic at all)
    out, err, _ = run_case("missing include silently dropped",
                           '#include <does_not_exist.inc>\nlet x: int = 1\n', [SEARCH_ROOT])
    silent_drop = (err is None and "does_not_exist" not in out)
    print("     -> missing file produced no error and no marker: %s" % silent_drop)

    # 7) real-world shape: Windows system file reachable through the fallback read
    #    (read-only probe - only the byte count is printed, never the content)
    sys_ini = "C:/Windows/win.ini"
    out, err, _ = run_case("probe: <%s> no search root" % sys_ini,
                           '#include <%s>\n' % sys_ini, [])
    if err is None and len(out) > 0:
        hits += 1
        print("     -> ARBITRARY SYSTEM FILE READ: %d bytes inlined "
              "(content withheld)" % len(out))
    else:
        print("     -> system probe inconclusive on this host: %s" % (err or "empty read"))
    out, err, _ = run_case("probe: system path w/ root",
                           '#include <%s>\n' % sys_ini, [SEARCH_ROOT])
    print("     -> with a search root configured the same input escapes the "
          "except-clause and propagates: %s" % (err or "no error"))

    print()
    print("normalisation check: _read_include_file never calls os.path.normpath/"
          "abspath/realpath and has no containment test against self.include_paths "
          "(see cypyc/parser/preprocessor.py:39-50).")
    if hits:
        print("VERDICT: REPRODUCED - %d out-of-root include reads inlined, "
              "no exception raised." % hits)
        return 1
    print("VERDICT: NOT-REPRODUCED - include filenames are now validated.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                              # noqa: BLE001
        traceback.print_exc()
        sys.exit(3)
