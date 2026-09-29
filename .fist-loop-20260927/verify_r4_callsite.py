"""R4-验证 法③：BUG-61..64 的**调用面**复算。

修复环的锁走的是进程内 `CypyHook.analyze_only`；本件只走用户真正敲的那张脸——
`python -X utf8 -m cypyc.cli transpile <src> -o <scratch> --check-only` 子进程，
rc、stdout、stderr 逐字入账。夹具是本轮现写的（换了标识符、换了嵌套、换了函数名），
不复用锁文件里的 12 条样本，否则「锁绿」就等于「锁绿」。

四件事一起测：
① 正确程序必须零诊断（旧缺陷把正确调用判错）；
② 错误程序必须报，且报的种类对（旧缺陷把错误调用放行）；
③ 同族对照必须维持既有正确行为（元数在别名上照报、动态值照宽松）；
④ 每条报错文案必须给用户看得懂的名字与行列定位，且不得外泄内部表示。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TMP = HERE / "verify_r4_tmp" / "callsite"
OUT = HERE / "verify_r4_callsite.json"
BEFORE_TC = HERE / "fix_r4_before" / "type_checker.py"
sys.path.insert(0, str(HERE))
import verify_r4_lib as V  # noqa: E402
CHECKS: list = []
REFUSE: list = []

TYPE_F = 'type F = Callable[[int], int]\n'


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


PROBES = [
    # --- BUG-61 / RC1：函数符号被登记成返回类型 ---
    {"id": "V61a", "bug": "BUG-61", "role": "proper",
     "src": (
         TYPE_F + "def wrap(cb: F, n: int) -> F:\n    return cb\n\n"
         "def thrice(a: int) -> int:\n    return a\n\n"
         "def run() -> F:\n    return wrap(thrice, 1)\n"),
     "want": "clean",
     "why": ("返回类型是 Callable 的函数按自身元数被正确调用，不该被判错"
             "（旧症状 C01：`mk(one, 1)` 被报 expected 1, got 2）")},
    {"id": "V61b", "bug": "BUG-61", "role": "violation",
     "src": "def pair(a: int, b: int) -> int:\n    return a\n\ndef run(g: int) -> int:\n"
            "    return pair(g)\n",
     "want": "error", "contains": ["arity", "expected 2, got 1"],
     "why": "少传一个实参必须报元数（旧症状 C02/C05 零诊断）"},
    {"id": "V61c", "bug": "BUG-61", "role": "proper",
     "src": (
         TYPE_F + "def twice(a: int) -> int:\n    return a\n\n"
         "def mk() -> F:\n    return twice\n"),
     "want": "clean", "why": "函数作值返回不该被当成返回类型不符（旧症状 C03）"},
    {"id": "V61d", "bug": "BUG-61", "role": "control",
     "src": TYPE_F + "def use(f: F) -> int:\n    return f(1, 2)\n",
     "want": "error", "contains": ["arity"],
     "why": "对照：别名 Callable 变量上的元数判定不得因 RC1 修法失效"},
    {"id": "V61e", "bug": "BUG-61", "role": "violation",
     "src": "def pair(a: int, b: int) -> int:\n    return a\n\ndef run(g: int) -> int:\n"
            "    return pair(g, 1, 2)\n",
     "want": "error", "contains": ["arity", "expected 2, got 3"],
     "why": "多传一个实参必须报元数（旧症状 C04 零诊断）"},

    # --- BUG-62 / RC2：实参类型从不比对 ---
    {"id": "V62a", "bug": "BUG-62", "role": "violation",
     "src": 'def apply(n: int) -> int:\n    return n\n\ndef run() -> int:\n    return apply("s")\n',
     "want": "error", "contains": ["mismatch"],
     "why": "str 传给 int 形参必须报（旧症状 C08 零诊断）"},
    {"id": "V62b", "bug": "BUG-62", "role": "violation",
     "src": 'def apply(s: str) -> str:\n    return s\n\ndef run() -> str:\n    return apply(42)\n',
     "want": "error", "contains": ["mismatch"], "why": "int 传给 str 形参必须报"},
    {"id": "V62c", "bug": "BUG-62", "role": "proper",
     "src": "def apply(n: int) -> int:\n    return n\n\ndef run() -> int:\n    return apply(7)\n",
     "want": "clean", "why": "类型相符的调用不得误报"},
    {"id": "V62d", "bug": "BUG-62", "role": "control",
     "src": "def apply(n: int) -> int:\n    return n\n\nlet dyn: object = 1\n\ndef run() -> int:\n"
            "    return apply(dyn)\n",
     "want": "clean", "why": "对照：动态值走宽松分支是设计，不得误报"},
    {"id": "V62e", "bug": "BUG-62", "role": "violation",
     "src": (
         TYPE_F + "def applyf(f: F) -> int:\n    return 0\n\n"
         "def thrice(a: int, b: int) -> int:\n    return a\n\n"
         "def run() -> int:\n    return applyf(thrice)\n"),
     "want": "error", "contains": ["mismatch"],
     "why": "两参函数传给一参 Callback 形参必须报（旧症状 C06）"},

    # --- BUG-63 / RC3：struct 成员类型解析不出 ---
    {"id": "V63a", "bug": "BUG-63", "role": "violation",
     "src": "struct K:\n    n: int\n\n    def f(self) -> str:\n        return self.n\n",
     "want": "error", "contains": ["Return type mismatch"],
     "why": "self.n 是 int 却声明返回 str（旧症状 C09 静默）"},
    {"id": "V63b", "bug": "BUG-63", "role": "violation",
     "src": "struct Inner:\n    n: int\n\nstruct Outer:\n    i: Inner\n\n"
            "    def f(self) -> str:\n        return self.i.n\n",
     "want": "error", "contains": ["Return type mismatch"], "why": "嵌套成员链同样要解析"},
    {"id": "V63c", "bug": "BUG-63", "role": "violation",
     "src": (
         TYPE_F + "struct S:\n    cb: F\n\n"
         "    def f(self) -> int:\n        return self.cb(1, 2)\n"),
     "want": "error", "contains": ["arity"], "why": "成员是 Callable 时元数要判（旧症状 C11）"},
    {"id": "V63d", "bug": "BUG-63", "role": "control",
     "src": "struct K:\n    n: int\n\n    def f(self) -> int:\n        return self.n\n",
     "want": "clean", "why": "对照：类型相符的成员返回不得误报"},

    # --- BUG-64 / RC4：文案外泄内部表示 ---
    {"id": "V64a", "bug": "BUG-64", "role": "violation",
     "src": TYPE_F + "def run() -> int:\n    let x: F = 1\n    return x\n",
     "want": "error", "contains": ["Callable[[int], int]"], "forbidden": ["tuple["],
     "why": "文案必须给源语法名而不是内部表示（旧症状 C12）"},
    {"id": "V64b", "bug": "BUG-64", "role": "violation",
     "src": 'def run() -> int:\n    let x: int = "s"\n    return x\n',
     "want": "error", "contains": ["Type mismatch"], "forbidden": ["tuple[", "object at 0x"],
     "why": "基本类型的文案形状不得被共用件带偏"},
    {"id": "V64c", "bug": "BUG-64", "role": "violation",
     "src": TYPE_F + "def run() -> int:\n    let x: F = 1\n    return 0\n",
     "want": "error", "contains": ["Callable[[int], int]"], "forbidden": ["tuple["],
     "why": "同一份源里第二条诊断也不许外泄"},
    {"id": "V64d", "bug": "BUG-64", "role": "control",
     "src": "struct P:\n    x: int\n\ndef use(p: P) -> int:\n    return p.x\n\ndef run() -> int:\n"
            "    return use(1)\n",
     "want": "error", "contains": ["P"], "forbidden": ["tuple[", "object at 0x"],
     "why": "对照：用户类型名必须原样出现在文案里（共用显示件不得把 struct 也糊掉）"},
]

INTERNAL_REPRS = ("tuple[<cypyc", "Type object at 0x", "tuple[int]", "object at 0x")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def cli_check(src_path: Path, cwd: Path = None, out_dir: Path = None) -> dict:
    cwd = cwd or ROOT
    out_dir = out_dir or TMP
    cmd = [sys.executable, "-X", "utf8", "-m", "cypyc.cli", "transpile", str(src_path),
           "-o", str(out_dir), "--check-only"]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if cwd != ROOT:
        env["PYTHONPATH"] = str(cwd)  # 快照树跑快照码，不吃工作区也不吃已安装孪生
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=300)
    raw = (p.stdout or "") + (p.stderr or "")
    text = ANSI_RE.sub("", raw)  # CLI 带 ANSI 着色，不剥就数不出诊断行
    diags = [ln.strip()[2:] for ln in text.splitlines() if ln.strip().startswith("- ")]
    return {"command_verbatim": " ".join(cmd), "rc": p.returncode, "diags": diags,
            "stdout_tail": (p.stdout or "")[-200:], "stderr_tail": (p.stderr or "")[-200:],
            "ok_banner": "[OK] Static analysis passed" in text,
            "fail_banner": text.startswith("[FAIL]") or "[FAIL]" in text}


def classify(row: dict) -> str:
    return "error" if row["diags"] or row["rc"] != 0 else "clean"


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    TMP.mkdir(parents=True, exist_ok=True)

    # 身份探针：CLI 子进程吃的必须是工作区的 cypyc，不是已安装孪生、也不是快照树
    ident = subprocess.run([sys.executable, "-X", "utf8", "-c",
                            "import cypyc,os;print(os.path.abspath(cypyc.__file__))"],
                           cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    loaded = ident.stdout.strip()
    check("调用面身份：CLI 必须吃工作区 cypyc",
          Path(loaded).resolve().is_relative_to(ROOT.resolve()), True, f"loaded={loaded}")
    check("调用面身份：不得落在快照树里", "verify_r4_snap" in loaded, False, f"loaded={loaded}")

    cli_rows = []
    for probe in PROBES:
        src = TMP / f"{probe['id']}.cypy"
        src.write_text(probe["src"], encoding="utf-8", newline="\n")
        r = cli_check(src)
        got = classify(r)
        joined = " | ".join(r["diags"])
        problems = []
        if got != probe["want"]:
            problems.append(f"期望 {probe['want']} 实得 {got}：{joined or '(零诊断)'}")
        # rc 与诊断必须同向：rc==0 却带诊断，或 rc!=0 却零诊断，都算调用面自相矛盾
        if (r["rc"] == 0) != (len(r["diags"]) == 0):
            problems.append(f"rc={r['rc']} 与诊断数 {len(r['diags'])} 不同向")
        for needle in probe.get("contains", []):
            if needle not in joined:
                problems.append(f"文案缺 {needle!r}")
        for needle in probe.get("forbidden", []):
            if needle in joined:
                problems.append(f"文案外泄 {needle!r}")
        if probe["want"] == "error" and not re.search(r"at \d+:\d+", joined):
            problems.append("错误诊断缺行列定位")
        cli_rows.append({**probe, "file": str(src.relative_to(ROOT)).replace("\\", "/"),
                         "got": got, "problems": problems, "pass": not problems, **r})

    control = [r for r in cli_rows if r["role"] == "control"]

    # 敏感度复测：同一批夹具喂给「修前产品码」的另一棵快照树，旧症状必须现形。
    # 没有这一档，「17 行全过」只证明夹具与今天的实现自洽，不证明它们抓得住昨天的缺陷。
    pre_snap = V.copy_into_snap(dest=V.SNAP2)
    (pre_snap / "cypyc" / "analyzer" / "type_checker.py").write_text(
        BEFORE_TC.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    pre_tmp = pre_snap / "verify_r4_tmp" / "callsite"
    pre_tmp.mkdir(parents=True, exist_ok=True)
    pre_ident = V.identity_probe(pre_snap)
    flips = []
    for probe in PROBES:
        src = pre_tmp / f"{probe['id']}.cypy"
        src.write_text(probe["src"], encoding="utf-8", newline="\n")
        before = cli_check(src, cwd=pre_snap, out_dir=pre_tmp / "out")
        now = next(r for r in cli_rows if r["id"] == probe["id"])
        if classify(before) != now["got"] or before["diags"] != now["diags"]:
            flips.append({"id": probe["id"], "role": probe["role"], "bug": probe["bug"],
                          "prefix_got": classify(before), "prefix_diags": before["diags"],
                          "now_got": now["got"], "now_diags": now["diags"]})
    sensitivity = {"snapshot": str(V.SNAP2), "identity": pre_ident,
                   "flips": flips, "flips_total": len(flips),
                   "proper_flips": [f["id"] for f in flips if f["role"] == "proper"]}
    check("敏感度树身份：吃的是修前快照", pre_ident["under_snapshot"], True,
          f"loaded={pre_ident['loaded'].get('mod')}")
    if len(flips) < 6:
        REFUSE.append(f"修前码上只有 {len(flips)} 行行为改变（<6）⇒ 这批调用面夹具对"
                      f"本轮修复不敏感，「全过」是装饰")
    for pid in ("V61a", "V61c"):
        if pid not in sensitivity["proper_flips"]:
            REFUSE.append(f"{pid}（正确程序）在修前码上没变红 ⇒ 旧误报症状没被这批夹具抓到")

    violations = [r for r in cli_rows if r["role"] == "violation"]
    propers = [r for r in cli_rows if r["role"] == "proper"]
    leaks = {r["id"]: [p for p in INTERNAL_REPRS if p in " | ".join(r["diags"])]
             for r in cli_rows if r["diags"]}
    leaks = {k: v for k, v in leaks.items() if v}
    failed_rows = [r["id"] for r in cli_rows if not r["pass"]]

    check("每条被拒/不符都必须点名（不许静默放行）", failed_rows, [], "见 rows[].problems")
    check("内部表示外泄必须为 0", leaks, {}, "逐条扫 tuple[<cypyc / object at 0x / tuple[int]")
    check("每个 bug 编号都要有实测行",
          sorted({r["bug"] for r in cli_rows}), ["BUG-61", "BUG-62", "BUG-63", "BUG-64"], "覆盖四单")
    check("对照行数≥4（每单一条同族对照）", len(control) >= 4, True, f"control={len(control)}")
    check("违规行数≥6（旧缺陷放行的那些形状）", len(violations) >= 6, True,
          f"violation={len(violations)}")
    check("正确程序行≥4", len(propers) >= 3, True, f"proper={len(propers)}")
    check("每行都要留逐字命令", sum(1 for r in cli_rows if r["command_verbatim"]), len(cli_rows),
          "command_verbatim 计数")
    if len(cli_rows) < 15:
        REFUSE.append(f"调用面只有 {len(cli_rows)} 行（<15）⇒ 覆盖面不够复算四单")

    doc = {"started": started, "face": "python -X utf8 -m cypyc.cli transpile … --check-only",
           "identity": {"loaded_cypyc": loaded, "cwd": str(ROOT)},
           "cli_rows": cli_rows, "rows_total": len(cli_rows),
           "control": control, "controls_pass": sum(1 for r in control if r["pass"]),
           "sensitivity": sensitivity,
           "by_bug": {b: [r["id"] for r in cli_rows if r["bug"] == b]
                      for b in sorted({r["bug"] for r in cli_rows})},
           "internal_repr_leaks": leaks, "failed_rows": failed_rows,
           "note": "本件只走子进程 CLI，不 import 判据件、不 import 锁文件里的夹具；"
                   "rc 与诊断数同向是硬门（rc=0 却带诊断=调用面自相矛盾）",
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"rows_total": len(cli_rows), "failed_rows": failed_rows,
                      "leaks": leaks,
                      "sensitivity_flips": sensitivity["flips_total"],
                      "proper_flips": sensitivity["proper_flips"],
                      "pre_ident": pre_ident["under_snapshot"],
                      "refuse": doc["refuse"]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
