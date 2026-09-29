#!/usr/bin/env python3
"""R2-验证 探针驱动：独立于修复环判据的对抗复测（不复用修复环的夹具）。

输出 `.fist-loop-20260927/verify_r2_probe.json`；`refuse==[]` 才算这几条法在调用面站得住。
两条纪律（都是上一环真实抓到的）：
 - 夹具一律照 SYNTAX 文档写（`str` 不是 `string`、`macro … = ` 不是 `macro …:`），
   否则夹具错误会被读成产品回归；
 - 每条产物判据前面钉一道 `require_emit`（rc=0 且 .pyx 非空）——不然断言会在空文本上恒真。
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIX = HERE / "verify_r2"
OUT = FIX / "out"
RESULT = HERE / "verify_r2_probe.json"

refuse: list = []
probes: dict = {}


def check(tag: str, ok: bool, detail) -> None:
    probes[tag] = {"ok": bool(ok), "detail": detail}
    if not ok:
        refuse.append(f"{tag} 未过：{json.dumps(detail, ensure_ascii=False)[:300]}")


def require_emit(tag: str, res: dict, text: str) -> bool:
    """产物类判据的前置门：编译必须成功且产物非空（空文本会让"不含 X"式断言恒真）。"""
    ok = res["rc"] == 0 and len(text) > 40
    check(tag, ok, {"rc": res["rc"], "pyx_chars": len(text), "tail": res["out"][-200:]})
    return ok


def write_src(name: str, text: str) -> Path:
    FIX.mkdir(parents=True, exist_ok=True)
    p = FIX / name
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def cli(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "cypyc", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    return {"rc": proc.returncode, "out": (proc.stdout or "") + (proc.stderr or "")}


def pyx_of(name: str) -> str:
    p = OUT / (Path(name).stem + ".pyx")
    return p.read_text(encoding="utf-8") if p.exists() else ""


def emit(name: str, text: str) -> tuple:
    src = write_src(name, text)
    res = cli(
        "transpile",
        str(src.relative_to(ROOT)),
        "-o",
        str(OUT.relative_to(ROOT)),
        "--emit-cython",
    )
    return res, pyx_of(name)


def sig_lines(text: str, fname: str) -> list:
    want = f"def {fname}("
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith(want)]


def deco_before(text: str, fname: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    for i, ln in enumerate(lines):
        if ln.startswith(f"def {fname}("):
            return lines[i - 1] if i else ""
    return "<缺>"


# P1 struct 的非绑定方法（文档形状：str 类型 + classmethod 带显式 cls）
P1_SRC = """
struct Gate:
    label: str

    @staticmethod
    def blank(n: int = 3) -> int:
        return n

    @classmethod
    def make(cls, tag: str = "x") -> int:
        return 1

    def shout(self, times: int) -> int:
        return times * 2

def driver() -> int:
    g: Gate = Gate("hi")
    return Gate.blank(4) + g.shout(2)
"""
r1, t1 = emit("p1_struct_cls.cypy", P1_SRC)
g1 = require_emit("P1.emits", r1, t1)
check(
    "P1.static_no_self",
    g1 and sig_lines(t1, "blank") == ["def blank(n=3):"],
    sig_lines(t1, "blank"),
)
sig_make = sig_lines(t1, "make")
check(
    "P1.class_no_self",
    g1 and len(sig_make) == 1 and not sig_make[0].startswith("def make(self"),
    sig_make,
)
check(
    "P1.bound_keeps_self",
    g1 and sig_lines(t1, "shout") == ["def shout(self, times):"],
    sig_lines(t1, "shout"),
)
check(
    "P1.binding_only_on_bound",
    g1
    and deco_before(t1, "blank") != "@cython.binding(False)"
    and deco_before(t1, "shout") == "@cython.binding(False)",
    [deco_before(t1, "blank"), deco_before(t1, "shout")],
)

probes["P0.keyword_observation"] = {
    "fact": "模块级 `def go()` 被 lexer 出 GO token，诊断是 'Expected IDENTIFIER, got GO at 16:5'",
    "doc": "SYNTAX/20-concurrency.md:7 —— `spawn`/`go` 是并发关键字，故这是夹具撞词，不是产品缺陷",
    "cost": "首版探针因此把 rc=1 读成回归，多花一次定位",
}

# P2 class（非 struct）里的同名装饰器：修复环只改了 struct 分支，这一面是空白区
P2_SRC = """
class Registry:
    count: int

    @staticmethod
    def version() -> int:
        return 7

    @classmethod
    def named(cls, tag: str) -> int:
        return 1

    def bump(self, by: int) -> int:
        return self.count + by
"""
r2, t2 = emit("p2_class_static.cypy", P2_SRC)
g2 = require_emit("P2.emits", r2, t2)
check(
    "P2.static_no_self",
    g2 and sig_lines(t2, "version") == ["def version():"],
    sig_lines(t2, "version"),
)
sig_named = sig_lines(t2, "named")
check(
    "P2.classmethod_keeps_cls",
    g2 and sig_named == ["def named(cls, tag):"],
    sig_named,
)
check(
    "P2.bound_keeps_self",
    g2 and sig_lines(t2, "bump") == ["def bump(self, by):"],
    sig_lines(t2, "bump"),
)

# P3 __implicit_default__：参数默认值那半边已修，局部绑定这一面单独看
P3_SRC = """
struct Point:
    x: int
    y: int

def implicit_sum(cfg: Point = __implicit_default__) -> int:
    return cfg.x + cfg.y
"""
r3, t3 = emit("p3_param_implicit.cypy", P3_SRC)
g3 = require_emit("P3.emits", r3, t3)
check(
    "P3.param_desugared", g3 and "Point.__implicit_default__()" in t3, sig_lines(t3, "implicit_sum")
)

P3B_SRC = """
struct Point:
    x: int
    y: int

def local_sum() -> int:
    p: Point = __implicit_default__
    return p.x + p.y
"""
r3b, t3b = emit("p3b_local_implicit.cypy", P3B_SRC)
probes["P3b.local_default"] = {
    "rc": r3b["rc"],
    "implicit_lines": [ln.strip() for ln in t3b.splitlines() if "implicit" in ln][:6],
    "tail": r3b["out"][-200:],
}
probes["P3b.observation_only"] = {
    "why": "SYNTAX/06d 只在参数位示例 __implicit_default__，局部绑定位未文档化 ⇒ 只记录不断言",
    "rc": r3b["rc"],
    "diagnostic": [ln.strip() for ln in r3b["out"].splitlines() if "implicit" in ln][:3],
}

# P4 return 作用域两端：模块级/class 体必须诊断，宏体必须合法
r4a, _ = emit("p4a_class_return.cypy", "class Box:\n    w: int\n    return 1\n")
check("P4.class_return_diagnosed", r4a["rc"] != 0, {"rc": r4a["rc"], "tail": r4a["out"][-200:]})
r4b, _ = emit("p4b_macro_return.cypy", "macro emit(ts: Tokens) -> Tokens =\n    return ts\n")
check("P4.macro_return_legal", r4b["rc"] == 0, {"rc": r4b["rc"], "tail": r4b["out"][-200:]})
r4c, _ = emit("p4c_module_return.cypy", "k: int = 1\nreturn 0\n")
check("P4.module_return_diagnosed", r4c["rc"] != 0, {"rc": r4c["rc"], "tail": r4c["out"][-200:]})

# P5 BUG-35 分桶：语法错误不得叫「读取文件错误」，真读不到才叫
r5, _ = emit("p5_syntax_error.cypy", "xs: list<int> = [1, 2\ndef broken(\n")
check(
    "P5.syntax_error_not_read_bucket",
    r5["rc"] != 0 and "读取文件错误" not in r5["out"],
    {"rc": r5["rc"], "tail": r5["out"][-240:]},
)
r5b = cli("run", ".fist-loop-20260927/verify_r2/definitely_absent_xq.cypy")
check(
    "P5.missing_file_is_read_bucket",
    "读取文件错误" in r5b["out"],
    {"rc": r5b["rc"], "tail": r5b["out"][-200:]},
)

# P6 hook 两条入口 + 包级 API（全新进程，不带本轮任何 in-process 状态）
p6a = cli("hook", "install")
p6b = cli("hook", "status")
p6c = subprocess.run(
    [sys.executable, "-X", "utf8", "-c", "import cypy_hook;print(sorted(cypy_hook.__all__))"],
    cwd=ROOT,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
check("P6.install_scoped_to_process", "current process" in p6a["out"], p6a["out"][-200:])
check(
    "P6.status_not_ok_in_fresh_proc",
    "[OK] Cypy import hook is active" not in p6b["out"],
    p6b["out"][-200:],
)
check(
    "P6.package_api",
    p6c.returncode == 0
    and all(n in p6c.stdout for n in ("install_hook", "uninstall_hook", "is_hook_installed")),
    p6c.stdout[:200],
)


# P7 BUG-50 损害面：文本改动量与语义增量分开数
def git_show_head(rel: str) -> str:
    proc = subprocess.run(
        ["git", "show", f"HEAD:{rel}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout if proc.returncode == 0 else ""


def numstat(rel: str) -> list:
    proc = subprocess.run(
        ["git", "diff", "--numstat", "HEAD", "--", rel],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    parts = proc.stdout.strip().split("\t")
    return parts[:2] if len(parts) >= 2 else ["?", "?"]


def node_hist(src: str) -> dict:
    """AST 节点类型直方图：文本重排不会改动它 ⇒ 与 numstat 并列就是"文本债 vs 语义增量"的分栏。"""
    if not src.strip():
        return {}
    tree = ast.parse(src)
    hist: dict = {}
    for node in ast.walk(tree):
        name = type(node).__name__
        hist[name] = hist.get(name, 0) + 1
    return hist


def hist_delta(a: dict, b: dict) -> int:
    return sum(abs(a.get(k, 0) - b.get(k, 0)) for k in set(a) | set(b))


semantic = {}
RADII = {"cypyc/parser/parser.py": "parser_py", "cypyc/parser/macro_expander.py": "macro_expander_py"}
for rel in RADII:
    hd = node_hist(git_show_head(rel))
    wd = node_hist((ROOT / rel).read_text(encoding="utf-8"))
    added, removed = numstat(rel)
    semantic[RADII[rel]] = {
        "text_lines_delta": f"+{added}/-{removed}",
        "ast_nodes_head": sum(hd.values()),
        "ast_nodes_work": sum(wd.values()),
        "ast_hist_delta": hist_delta(hd, wd),
    }
probes["P7.semantic_vs_text"] = semantic
check(
    "P7.head_is_not_a_pre_black_base",
    all(v["ast_hist_delta"] > 60 for v in semantic.values()),
    {
        "reading": "对 HEAD 的 AST 直方图差达上千节点 ⇒ HEAD 里根本没有 09-26/R1 两轮未提交的工作，"
        "所以『文本 delta vs HEAD』不能用来单独给 black 定量，只能当上界",
        "detail": semantic,
    },
)

# P9 把 black 的噪声与真实增量分开：对 HEAD 版先跑一遍同一配置的 black，再与工作树比
import difflib  # noqa: E402

import black  # noqa: E402

noise = {}
RADII = {"cypyc/parser/parser.py": "parser_py", "cypyc/parser/macro_expander.py": "macro_expander_py"}
for rel in RADII:
    head_src = git_show_head(rel)
    work_lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
    norm = black.format_str(head_src, mode=black.Mode(line_length=100)).splitlines()
    raw_head = head_src.splitlines()

    def changed(a: list, b: list) -> int:
        return sum(
            1
            for ln in difflib.unified_diff(a, b, n=0)
            if (ln.startswith("+") or ln.startswith("-")) and not ln.startswith(("+++", "---"))
        )

    noise[RADII[rel]] = {
        "vs_head_raw": changed(raw_head, work_lines),
        "vs_head_after_black": changed(norm, work_lines),
        "attributable_to_formatting": changed(raw_head, norm),
    }
probes["P9.black_noise_split"] = noise
check(
    "P9.formatting_dominates_the_head_delta",
    all(
        v["vs_head_after_black"] > 0 and v["attributable_to_formatting"] > v["vs_head_after_black"]
        for v in noise.values()
    ),
    noise,
)

# P8 git 红线
p8 = subprocess.run(
    ["git", "rev-parse", "--short", "HEAD"],
    cwd=ROOT,
    capture_output=True,
    text=True,
    encoding="utf-8",
)
check("P8.head_unchanged", p8.stdout.strip() == "17d68b4", p8.stdout.strip())

RESULT.write_text(
    json.dumps({"refuse": refuse, "probes": probes}, ensure_ascii=False, indent=1, default=str)
    + "\n",
    encoding="utf-8",
    newline="\n",
)
print(json.dumps({"refuse": refuse[:8], "count": len(refuse)}, ensure_ascii=False))
sys.exit(1 if refuse else 0)
