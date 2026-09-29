"""边界审视叶 T0r112.1.3 的交付：位置模式在「空/极值/非法/资源极限」四类输入下的形态。

判据口径（不猜）：每格都记录 rc、是否出现 traceback（编译器内部崩溃＝缺陷）、以及诊断首行。
「做不到」也是主张，必须实测：本探针先把每种形态真跑一遍 transpile，再对结果分类，
不把「预期会报错」当结论。分类器本身配一对可红对照：
  - 用一个必然合法的源，要求分类为 clean；
  - 用一个必然语法错的源，要求分类为 syntax-error 且**不含** traceback。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "hunt_r6_boundary.json"

CASES = {
    "空实参": 'struct E:\n    a: int\n\ndef f(e: E) -> int:\n    match e:\n        case E():\n            return 1\n        case _:\n            return 0\n',
    "极值实参-32槽": 'struct E:\n' + ''.join(f"    f{i}: int\n" for i in range(32)) + (
        '\ndef f(e: E) -> int:\n    match e:\n        case E(' + ', '.join(f"x{i}" for i in range(32)) + '):\n'
        '            return x0\n        case _:\n            return 0\n'),
    "非法实参-字面量与绑定混写": 'struct E:\n    a: int\n    b: int\n\ndef f(e: E) -> int:\n    match e:\n        case E(1, x):\n            return x\n        case _:\n            return 0\n',
    "未定义类型的提取器": 'def f(e: Unknown) -> int:\n    match e:\n        case Unknown(a, b):\n            return 1\n        case _:\n            return 0\n',
    "资源极限-嵌套八层": (
        'struct L:\n    v: int\n\n' + 'def f(x: L) -> int:\n    match x:\n'
        + '        case L(' * 8 + '0' + ')' * 8 + ':\n            return 1\n        case _:\n            return 0\n'),
    "空匹配体": 'struct E:\n    a: int\n\ndef f(e: E) -> int:\n    match e:\n',
}

CANARY = {
    "clean": 'struct E:\n    a: int\n    b: int\n\ndef f(e: E) -> int:\n    match e:\n        case E(x, y):\n            return x\n        case _:\n            return 0\n',
    "syntax-error": 'def f(:\n',
}


def run_case(source: str, tmp: Path):
    src = tmp / "case.cypy"
    src.write_text(source, encoding="utf-8", newline="\n")
    # 尺子自坏过一次：cypyc 按**调用进程 cwd**解析源文件路径，而 CLI 的 stdout 横幅里回显的是
    # 我传进去的那个串（看着像真跑了）。先前用「工作目录=本目录 + 相对文件名」⇒ 每格都
    # 「读取文件错误」且 rc=1，逐格数字全部无效。现在用绝对源路径 + 绝对输出目录，
    # 并把「读取文件错误」当作分类器自己的失效信号。
    out_dir = tmp / "out"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "cypyc", "transpile", str(src.resolve()),
         "-o", str(out_dir.resolve()), "--emit-cython"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=180)
    blob = (proc.stdout or "") + (proc.stderr or "")
    if "读取文件错误" in blob:
        raise RuntimeError(f"探针自身失效（源没被读到）：{blob.strip()[-200:]}")
    crashed = "Traceback (most recent call last)" in blob
    # CLI 的诊断行带 ANSI 色码（`  \x1b[31m-\x1b[0m 编译错误: ...`），按字面 "- " 锚定必然数出 0 条。
    plain = re.sub(r"\x1b\[[0-9;]*m", "", blob)
    diag = [ln.strip("- ").strip() for ln in plain.splitlines()
            if ln.strip().startswith("- ") and len(ln.strip()) > 3]
    return {"rc": proc.returncode, "internal_crash": crashed,
            "diagnostics": diag[:3], "verbatim_tail": plain.strip()[-220:]}


def main() -> int:
    tmp = HERE / "boundary_tmp"
    tmp.mkdir(exist_ok=True)
    report: dict = {"cases": {}, "canary": {}, "refuse": []}
    for label, source in CASES.items():
        try:
            report["cases"][label] = run_case(source, tmp)
        except subprocess.TimeoutExpired:
            report["cases"][label] = {"rc": None, "internal_crash": False,
                                      "diagnostics": ["TIMEOUT 180s"], "hang": True}
        except RuntimeError as exc:
            report["cases"][label] = {"probe_broken": str(exc)}
            report["refuse"].append(f"{label}: {exc}")
    for label, source in CANARY.items():
        got = run_case(source, tmp)
        if label == "clean" and got["rc"] != 0:
            report["refuse"].append(f"canary clean 却 rc={got['rc']} ⇒ 分类器或产品坏了：{got['diagnostics']}")
        if label == "clean" and got["internal_crash"]:
            report["refuse"].append("canary clean 出现 traceback")
        if label == "syntax-error" and got["rc"] == 0:
            report["refuse"].append("canary syntax-error 竟然 rc=0 ⇒ 判据恒绿")
        if label == "syntax-error" and got["internal_crash"]:
            report["refuse"].append("canary syntax-error 以内部崩溃收场（应为用户诊断）")
        report["canary"][label] = got
    report["crash_count"] = sum(1 for v in report["cases"].values() if v.get("internal_crash"))
    report["hang_count"] = sum(1 for v in report["cases"].values() if v.get("hang"))
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "verbatim_tail"}
                      for k, v in list(report["cases"].items()) + list(report["canary"].items())},
                     ensure_ascii=False, indent=1))
    print(f"SUMMARY crash={report['crash_count']} hang={report['hang_count']} refuse={len(report['refuse'])}")
    for r in report["refuse"]:
        print("REFUSE:", r)
    return 1 if report["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
