"""R1-验证 law5 的可复用内核：把 lint 判据钉在**本轮亲笔写的行**上，而不是整份文件。

为什么要换口径（第一版被打回的真相）：
 `cypyc/codegen/cython_generator.py` 单文件在 flake8(100) 下有 **286 条**存量违规
 （W293 174 / F541 30 / E501 71 / F401 4 / F841 3 …），`cypy_bridge/types.py` 56 条。
 按「本轮碰过的文件必须 lint 干净」判 ⇒ 任何改动都不可能通过，判据等价于恒红；
 按「跑 black 全仓」修 ⇒ 一次产生 400+ 行无关重排，越出验证环节的半径且会顶掉
 09-26 未提交轮的工作。两种都不是可执行的门禁。

现在的口径分三层，每层都能数：
 a) **本轮亲笔区间**（按本轮新引入的 `def`/模块级常量名定位行范围）：违规必须 = 0，
    新文件（`tests/test_loop_20260927_fix.py`）整份算亲笔；
 b) 工作树 vs HEAD 的 '+' 新增行上的违规：本轮**与 09-26 未提交轮混在一起、不可分离**，
    只作清单级记录（不是断言，是承认口径边界）；
 c) 全仓 flake8/black/mypy 普查：交 R1-打磨清账。
外加两条对照：区间内伪造长行必被抓（否则判据空转）、区间外的存量违规不得计入
本轮（否则守卫比主张宽）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
FLAKE_CFG = ["--max-line-length=100"]  # pyproject 的声明值；见 BUG-40：flake8 其实不读它

# 本轮（R1-修复）真正写进产品码的块：BUG-30 的三个 helper + 两张类型表、
# BUG-33/38 的两个 lexer 方法、BUG-31 的两处口径文档 + 改名别名。
AUTHORED_DEFS = {
    "cypyc/codegen/cython_generator.py": [
        "_is_integral_value_expr",
        "_float_widen_if_integral",
        "_record_declared_var",
    ],
    "cypyc/parser/lexer.py": ["_skip_whitespace", "_tokenize_string"],
    "cypy_bridge/types.py": ["to_ctypes", "to_c"],
}
AUTHORED_TOPLEVEL = {
    "cypyc/codegen/cython_generator.py": ["_INTEGRAL_CYTHON_TYPES", "_FLOAT_CYTHON_TYPES"],
    "cypy_bridge/types.py": ["float32_"],
    "cypy_bridge/__init__.py": ["float32_"],
}
NEW_FILES = ["tests/test_loop_20260927_fix.py"]
# 有些改动不落在 `def` 里（改名站点、docstring 口径句），用行内 needle 钉住整行区间；
# 只靠 def 定位会漏检——第一版就是这么让 `cypy_bridge/__init__.py` 变成"零区间"的。
AUTHORED_NEEDLES = {
    "cypy_bridge/__init__.py": [r"^\s*['\"]?float32_['\"]?,?\s*$"],
    "cypy_bridge/types.py": [r"C/FFI", r"^\s*float32_\s*="],
}
REPO_DIRS = ["cypyc", "cypy_bridge", "scripts", "tests"]


def flake8(path: str) -> list:
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "flake8", *FLAKE_CFG, "--", path],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = []
    for ln in (r.stdout or "").splitlines():
        m = re.match(r"^.+?:(\d+):(\d+): ([EWFC]\d+) ", ln)
        if m:
            out.append((int(m.group(1)), m.group(3), ln))
    return out


def def_ranges(rel: str, names: list) -> list:
    """定位 `def name(...)` 到下一个同级 `def`/`class`（或dedent）为止的行区间。"""
    lines = (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    ranges = []
    for i, ln in enumerate(lines, start=1):
        for nm in names:
            m = re.match(rf"^(\s*)def {re.escape(nm)}\(", ln)
            if not m:
                continue
            indent = len(m.group(1))
            j = i + 1
            while j <= len(lines):
                cur = lines[j - 1]
                if cur.strip():
                    ci = len(cur) - len(cur.lstrip())
                    if ci <= indent and re.match(r"^\s*(def |class |@)", cur):
                        break
                j += 1
            ranges.append((i, j - 1, f"def {nm}"))
    return ranges


def toplevel_ranges(rel: str, names: list) -> list:
    """模块级赋值/常量：从赋值行到「下一个顶格且非续行」之前。"""
    lines = (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    ranges = []
    for i, ln in enumerate(lines, start=1):
        for nm in names:
            if not re.match(rf"^{re.escape(nm)}\s*[:=]", ln):
                continue
            j = i + 1
            while j <= len(lines) and (
                not lines[j - 1].strip() or (lines[j - 1] and lines[j - 1][0] in " \t")
            ):
                if not lines[j - 1].strip():
                    break
                j += 1
            ranges.append((i, j - 1, f"toplevel {nm}"))
    return ranges


def needle_ranges(rel: str, needles: list, refuse: list) -> list:
    """按行内 needle 钉区间；每条 needle 必须至少命中 1 行，否则这条主张是空的。"""
    lines = (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    ranges, hits = [], {}
    for pat in needles:
        rx = re.compile(pat)
        n = 0
        for i, ln in enumerate(lines, start=1):
            if rx.search(ln):
                ranges.append((i, i, f"needle {pat}"))
                n += 1
        hits[pat] = n
    for pat, n in hits.items():
        if n == 0:
            refuse.append(f"判据5a {rel} 的 needle {pat!r} 一行都没命中 ⇒ 主张为空，该处没在检查")
    return ranges


def ranges_for(rel: str, refuse: list | None = None) -> list:
    return (
        def_ranges(rel, AUTHORED_DEFS.get(rel, []))
        + toplevel_ranges(rel, AUTHORED_TOPLEVEL.get(rel, []))
        + needle_ranges(rel, AUTHORED_NEEDLES.get(rel, []), refuse if refuse is not None else [])
    )


def added_lines(rel: str) -> set:
    d = subprocess.run(
        ["git", "diff", "-U0", "HEAD", "--", rel],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    out = set()
    for h in re.finditer(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", d, re.M):
        s, n = int(h.group(1)), int(h.group(2) or 1)
        out.update(range(s, s + n))
    return out


def in_ranges(vline: int, rs: list) -> bool:
    return any(a <= vline <= b for a, b, _ in rs)


def census(text_violations: list) -> dict:
    c = {}
    for _l, code, _raw in text_violations:
        c[code] = c.get(code, 0) + 1
    return c


def selftest(refuse: list) -> dict:
    """两条对照：区间内伪造违例必被抓；区间外存量违例不得算本轮的。"""
    rel = "cypyc/codegen/cython_generator.py"
    rs = ranges_for(rel, refuse)
    if not rs:
        refuse.append(f"对照失效：{rel} 定位不到本轮亲笔区间（判据会空转）")
        return {"ok": False}
    a, b, tag = rs[0]
    inside = [(a + 1, "E501", "fake-inside")]
    outside = [(b + 5000, "W293", "fake-outside")]
    caught = [v for v in inside if in_ranges(v[0], rs)]
    ignored = [v for v in outside if in_ranges(v[0], rs)]
    ok = len(caught) == 1 and not ignored
    if not ok:
        refuse.append(f"判据5 对照失效：inside={caught} outside_leaked={ignored}（区间={rs}）")
    return {
        "ok": ok,
        "range0": [a, b, tag],
        "inside_caught": len(caught),
        "outside_leaked": len(ignored),
    }


def main() -> int:
    refuse = []
    doc = {"per_file": {}, "new_files": {}, "black": {}, "repo_census": {}, "controls": {}}

    files = sorted(set(AUTHORED_DEFS) | set(NEW_FILES) | {"cypy_bridge/__init__.py"})
    for rel in files:
        vs = flake8(rel)
        if rel in NEW_FILES:
            mine = list(vs)  # 整份都是本轮写的
            rs, tag = [], "new file"
        else:
            rs = ranges_for(rel, refuse)
            mine = [v for v in vs if in_ranges(v[0], rs)]
            tag = rs
        on_added = [v for v in vs if v[0] in added_lines(rel)]
        entry = {
            "violations_total": len(vs),
            "census": census(vs),
            "authored_ranges": rs,
            "in_authored": len(mine),
            "in_authored_detail": [m[2] for m in mine][:12],
            "on_diff_added_lines": len(on_added),
            "note": "on_diff_added_lines 含 09-26 未提交轮，不可分离 ⇒ 只作清单级记录",
        }
        doc["per_file"][rel] = entry
        if rel in NEW_FILES:
            doc["new_files"][rel] = {"violations": len(mine), "detail": [m[2] for m in mine][:12]}
        if mine:
            refuse.append(
                f"判据5a 本轮亲笔范围 {rel} 有 {len(mine)} 条违规：" f"{[m[2] for m in mine][:6]}"
            )
        if not rs and rel not in NEW_FILES:
            refuse.append(f"判据5a {rel} 既定位不到亲笔区间、也不是新文件 ⇒ 该文件未被真正检查")

    # black：--check 的 rc=1 只表示「会被重排」，原文走 stderr，必须合并才能拿到清单
    br = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "black", "--check", *files],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    reformatted = sorted(
        {
            re.sub(r"^would reformat ", "", ln).strip().replace("\\", "/")
            for ln in (br.stderr or "").splitlines()
            if ln.startswith("would reformat")
        }
    )
    doc["black"] = {
        "rc": br.returncode,
        "would_reformat": reformatted,
        "stderr_lines": len((br.stderr or "").splitlines()),
        "note": "全仓/多文件重排属打磨轮裁决面：一次会产生数百行无关 diff",
    }
    for f in NEW_FILES:
        if any(f in r for r in reformatted):
            refuse.append(f"判据5b 本轮新建的 {f} 连 black 都不接受：{reformatted}")

    rc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "flake8", *FLAKE_CFG, *REPO_DIRS],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    all_v = []
    for ln in (rc.stdout or "").splitlines():
        m = re.match(r"^.+?:(\d+):(\d+): ([EWFC]\d+) ", ln)
        if m:
            all_v.append((int(m.group(1)), m.group(3), ln))
    doc["repo_census"] = {
        "rc": rc.returncode,
        "total": len(all_v),
        "census": census(all_v),
        "files": len({ln.split(":")[0] for ln in (rc.stdout or "").splitlines()}),
        "as": "打磨轮清账队列（判据5 不据此拒绝）",
    }

    doc["controls"] = {"lint_scope": selftest(refuse)}
    (HERE / "verify_lint_r1.json").write_text(
        json.dumps({"refuse": refuse, **doc}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "refuse": refuse,
                "in_authored": {k: v["in_authored"] for k, v in doc["per_file"].items()},
                "totals": {k: v["violations_total"] for k, v in doc["per_file"].items()},
                "ranges_found": {k: len(v["authored_ranges"]) for k, v in doc["per_file"].items()},
                "new_files": doc["new_files"],
                "black": doc["black"],
                "repo_census": {k: v for k, v in doc["repo_census"].items() if k != "census"},
                "controls": doc["controls"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
