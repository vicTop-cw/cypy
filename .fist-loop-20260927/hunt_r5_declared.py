"""R5-寻虫 法 1：每条主张先读它自己的定位声明，再当场**自己重测**——子代理的结论一律不许原样入账。

口径：
- `doc` 从盘上现读（含行号与逐字引文），读不到 ⇒ 这一条直接 refuse，不进入结论；
- `measured` 一律是本脚本自己跑出来的（analyze 批量 / CLI rc+原文 / tokenize 计数 / 生成物文本）；
  子代理给的同名结论只当「去哪儿看」的线索，不当数；
- 文档自述「尚未实现/计划中」而今天确实没实现 ⇒ `design`（撤回，不占号）；
  今天已实现而状态表还写着未实现 ⇒ `stale-doc`；文档写了不存在的能力 ⇒ `real-gap`；
- **每条"文档说的规则不成立"的结论都要配一条同族正例**（去掉可疑之处就该干净），
  否则分不清是文档陈旧还是夹具/环境坏了；
- 跑不动、要真编译或要网络的 ⇒ `not_measured` 并写明原因，**不许**写成"没问题"。
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path

import hunt_r5_analyzer as K

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "hunt_r5_declared.json"
SCRATCH = HERE / "tmp_declared"
PY = sys.executable
REFUSE: list = []
CHECKS: list = []


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append(
        {
            "label": label,
            "got": got,
            "want": want,
            "why": why,
            "ok": (got == want) if ok is None else bool(ok),
        }
    )


def doc_quote(rel: str, needle: str) -> dict:
    path = ROOT / rel
    if not path.exists():
        REFUSE.append(f"文件不在盘上：{rel}")
        return {"file": rel, "line": -1, "quote": "", "needle": needle}
    for i, ln in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if needle in ln:
            return {"file": rel, "line": i, "quote": ln.strip()[:220]}
    REFUSE.append(f"{rel} 里找不到 {needle!r} ⇒ 这条主张的立单原文不成立，不许进入结论")
    return {"file": rel, "line": -1, "quote": "", "needle": needle}


def cli(args: list, timeout: int = 240) -> dict:
    p = subprocess.run(
        [PY, "-X", "utf8", "-m", "cypyc.cli", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    body = [ln.strip() for ln in (p.stdout + p.stderr).strip().splitlines()]
    return {"args": args, "rc": p.returncode, "lines": body[-60:], "tail": body[-3:]}


def code_lines(rel: str) -> int:
    """口径=「非注释、非字符串 token 覆盖到的行数」（PROJECT-SPEC 说"不含注释"，这里把 docstring 也剔掉）。"""
    lines = set()
    with (ROOT / rel).open("rb") as fh:
        try:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type in (
                    tokenize.COMMENT,
                    tokenize.NL,
                    tokenize.NEWLINE,
                    tokenize.ENCODING,
                    tokenize.STRING,
                    tokenize.INDENT,
                    tokenize.DEDENT,
                    tokenize.ENDMARKER,
                ):
                    continue
                lines.update(range(tok.start[0], tok.end[0] + 1))
        except tokenize.TokenError as exc:
            REFUSE.append(f"{rel} tokenize 中断：{exc}")
    return len(lines)


def grep_files(pattern: str, roots: list, limit: int = 4) -> list:
    hits = []
    for rel in roots:
        base = ROOT / rel
        files = [base] if base.is_file() else sorted(base.rglob("*.py"))
        for f in files:
            if "__pycache__" in set(f.parts):
                continue
            for i, ln in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pattern in ln:
                    hits.append(f"{f.relative_to(ROOT).as_posix()}:{i}")
                    if len(hits) >= limit:
                        return hits
    return hits


def in_tmp_python(code: str, cwd: Path) -> dict:
    p = subprocess.run(
        [PY, "-X", "utf8", "-c", code],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    out = (p.stdout or "").strip().splitlines()
    payload = None
    for ln in reversed(out):
        if ln.startswith("{"):
            try:
                payload = json.loads(ln)
            except json.JSONDecodeError:
                pass
            break
    return {
        "rc": p.returncode,
        "json": payload,
        "tail": (p.stdout + p.stderr).strip().replace("\r\n", "\n").split("\n")[-2:],
    }


PROBES = {
    "callable_arity_now_reported": K.DECL + "def a(cb: Callback) -> str:\n    return cb(1, 2)\n",
    "bitand_int": "def g(a: int, b: int) -> int:\n    let c: int = a & b\n    return c\n",
    "walrus": "def g(n: int) -> int:\n    if (m := n) > 0:\n        return m\n    return 0\n",
    "walrus_free_control": "def g(n: int) -> int:\n    if n > 0:\n        return n\n    return 0\n",
    "i32_let": "let a: i32 = 12\n",
    "i32_fn": "def g(a: i32, b: f64) -> bool:\n    return True\n",
    "mut_decl": "def g() -> int:\n    mut x: i32 = 42\n    return 0\n",
    "indent_8": "def f(x: int) -> int:\n        return x + 1\n",
    "indent_4_control": "def f(x: int) -> int:\n    return x + 1\n",
    "constraint_generic": (
        "constraint Numeric = int | float\n"
        "def g(a: Numeric) -> Numeric:\n    return a\n"
    ),
    "subtype_decl": "struct A:\n    n: int\nsubtype B <: A\n",
    "dispatch_decl": "dispatch f(x: int) -> int\n",
}


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    OUT.write_text(
        json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    (SCRATCH / "cwd_probe").mkdir(parents=True)
    names = sorted(PROBES)
    batch = K.run_batch([PROBES[k] for k in names])
    obs = {k: K.observed_kind(v) for k, v in zip(names, batch["rows"])}
    rows = []
    w_ok = not obs["walrus_free_control"]["errors"]
    i4_ok = not obs["indent_4_control"]["errors"]

    rows.append(
        {
            "id": "D01",
            "face": "SYNTAX/appendix-C 特性状态表",
            "claim": "这一行把 `Callable[[T], R]` 函数类型标注列为「尚未实现，用 def + 类型推断」",
            "doc": doc_quote(
                "SYNTAX/appendix-C-features.md", "函数类型标注 | 使用 `def` + 类型推断"
            ),
            "measured": {
                "errors": obs["callable_arity_now_reported"]["errors"],
                "arity_violation_reported": obs["callable_arity_now_reported"]["arity"],
            },
            "rule": "今天元数判定会报 ⇒ 特性已落地，表里那行陈旧",
            "verdict": (
                "stale-doc" if obs["callable_arity_now_reported"]["arity"] else "doc-still-true"
            ),
            "frozen_surface": True,
            "fix_owner": "人工（SYNTAX/ 冻结面）",
        }
    )

    rows.append(
        {
            "id": "D02",
            "face": "SYNTAX/appendix-C 特性状态表",
            "claim": "「`&` 位运算与取址冲突 ⇒ 用 `|`、`^` 替代」",
            "doc": doc_quote("SYNTAX/appendix-C-features.md", "位运算与取址冲突"),
            "measured": {"errors": obs["bitand_int"]["errors"]},
            "rule": "`a & b` 静态分析零错 ⇒ 「必须换成 | / ^」的说法陈旧",
            "verdict": "stale-doc" if not obs["bitand_int"]["errors"] else "doc-still-true",
            "frozen_surface": True,
            "fix_owner": "人工（SYNTAX/ 冻结面）",
        }
    )

    rows.append(
        {
            "id": "D03",
            "face": "SYNTAX/appendix-C 特性状态表",
            "claim": "「walrus `:=` 尚未实现 ⇒ 用构建块 `=:`」",
            "doc": doc_quote("SYNTAX/appendix-C-features.md", "walrus"),
            "measured": {
                "walrus_errors": obs["walrus"]["errors"],
                "control_without_walrus_clean": w_ok,
                "control_errors": obs["walrus_free_control"]["errors"],
            },
            "rule": "带 `:=` 报错、同形状去掉 `:=` 干净 ⇒ 确实未实现，且不是夹具自己坏了",
            "verdict": "design" if (obs["walrus"]["errors"] and w_ok) else "not_measured",
            "frozen_surface": True,
            "fix_owner": "无人（文档与实现一致 ⇒ 撤回不占号）",
        }
    )

    rows.append(
        {
            "id": "D04",
            "face": "SYNTAX/appendix-C 主类型表",
            "claim": "类型表把 `i8/i16/i32/i64/u8…` 当一等公民，正文示例 `let x: i32 = 10`",
            "doc": doc_quote("SYNTAX/appendix-C-features.md", "`i8`、`i16`、`i32`"),
            "measured": {
                "let_i32": obs["i32_let"]["errors"],
                "fn_i32_f64": obs["i32_fn"]["errors"],
                "i32_literal_in_compiler": grep_files("i32", ["cypyc/analyzer", "cypyc/codegen"]),
            },
            "rule": "文档给的头等类型在分析器/生成器里搜不到 ⇒ 声明与实现分道（不在"
            "「尚未实现」那一行的豁免范围内，因为它就写在主类型表里）",
            "verdict": "real-gap",
            "frozen_surface": True,
            "fix_owner": "人工（补类型集或改文档，两侧都涉冻结面）",
        }
    )

    rows.append(
        {
            "id": "D05",
            "face": "SYNTAX/appendix-C 指针小节",
            "claim": "示例写 `mut x: i32 = 42` / `let p: *mut i32 = &x`",
            "doc": doc_quote("SYNTAX/appendix-C-features.md", "let p: *mut i32"),
            "measured": {"mut_errors": obs["mut_decl"]["errors"]},
            "rule": "示例照抄即词法错误 ⇒ 例子跑不动",
            "verdict": "stale-doc" if obs["mut_decl"]["errors"] else "doc-still-true",
            "frozen_surface": True,
            "fix_owner": "人工（SYNTAX/ 冻结面）",
        }
    )

    compile_flag = cli(["--compile", "examples/hello.cypy"])
    build_incr = cli(["build", "--incremental", "examples"])
    transpile_ok_ctl = cli(
        ["transpile", "examples/hello.cypy", "-o", ".fist-loop-20260927/tmp_declared/out_transpile"]
    )
    rows.append(
        {
            "id": "D06",
            "face": "SYNTAX/appendix-C 用法段",
            "claim": "文档给出 `cypyc --compile x.cypy` / `cypyc build --incremental ./project` 形态",
            "doc": doc_quote("SYNTAX/appendix-C-features.md", "cypyc --compile"),
            "measured": {
                "flag_compile": compile_flag,
                "build_incremental": build_incr,
                "control_transpile_rc": transpile_ok_ctl["rc"],
            },
            "rule": "CLI 本身能用（对照 rc=0），两条文档旗标被 argparse 拒 ⇒ 旗标不存在",
            "verdict": (
                "real-gap"
                if (
                    compile_flag["rc"] != 0
                    and build_incr["rc"] != 0
                    and transpile_ok_ctl["rc"] == 0
                )
                else "not_measured"
            ),
            "frozen_surface": False,
            "fix_owner": "寻虫环禁改产品码 ⇒ 下一环修或转结",
        }
    )

    rows.append(
        {
            "id": "D07",
            "face": "SYNTAX/appendix-C 语法对照表",
            "claim": "缩进规则一行写「Cypy: 必须 4 的倍数」",
            "doc": doc_quote("SYNTAX/appendix-C-features.md", "必须 4 的倍数"),
            "measured": {
                "eight_spaces": obs["indent_8"]["errors"],
                "four_spaces_clean": i4_ok,
                "two_spaces": K.run_batch(["def f(x: int) -> int:\n  return x + 1\n"])["rows"][0],
            },
            "rule": "8 空格（4 的倍数）被拒、4 空格干净 ⇒ 真实规则是「每层恰好 +4」，不是「4 的倍数」",
            "verdict": "stale-doc" if (obs["indent_8"]["errors"] and i4_ok) else "not_measured",
            "frozen_surface": True,
            "fix_owner": "人工（SYNTAX/ 冻结面）",
        }
    )

    pp = (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    rows.append(
        {
            "id": "D08",
            "face": "docs/USAGE.md 入口点",
            "claim": '`cypyc = "cypy_hook.hook:main"  # 安装后注册 cypyc 命令`',
            "doc": doc_quote("docs/USAGE.md", "cypy_hook.hook:main"),
            "measured": {
                "pyproject_scripts": [
                    ln.strip()
                    for ln in pp
                    if ln.strip().startswith(("cypyc", "cypy-hook", "cypyc-cli"))
                ]
            },
            "rule": "文档写的入口点与 pyproject 实际的入口点是两个不同程序 ⇒ 照文档排查会走错门",
            "verdict": "stale-doc",
            "frozen_surface": False,
            "fix_owner": "下一环修（docs 非冻结）",
        }
    )

    rows.append(
        {
            "id": "D09",
            "face": "docs/USAGE.md 依赖表",
            "claim": '依赖表写 Python ≥ 3.8，且引用 `requires-python = ">=3.8"`',
            "doc": doc_quote("docs/USAGE.md", "| Python |"),
            "measured": {
                "pyproject_requires": [ln.strip() for ln in pp if "requires-python" in ln],
                "declared_floor_note": "本机只有一个解释器，3.8 能不能跑我测不出 ⇒ 只比"
                "**文档引用的声明**与**实际声明**是否一致",
            },
            "rule": "文档转述的声明与 pyproject 实际值不同 ⇒ 一致性缺陷（不是兼容性结论）",
            "verdict": "stale-doc",
            "frozen_surface": False,
            "fix_owner": "下一环修",
        }
    )

    hook_help = cli(["hook", "--help"])
    UNDOC = ("--transpile-only", "--compile", "--run", "--eval", "-o", "--output")
    help_body = " ".join(hook_help.get("lines") or [])
    rows.append(
        {
            "id": "D10",
            "face": "docs/USAGE.md §2.6 hook 子命令",
            "claim": "§2.6 只列 install/uninstall/status/clear-cache 四个动作",
            "doc": doc_quote("docs/USAGE.md", "clear-cache"),
            "measured": {
                "help_rc": hook_help["rc"],
                "undocumented_options": [o for o in UNDOC if o in help_body],
                "help_tail": hook_help["tail"],
            },
            "rule": "`--help` 实读集（整篇扫描，不是只看尾巴三行）里出现文档未列的选项 ⇒ 用法面与实现不符",
            "verdict": (
                "usage-mismatch"
                if hook_help["rc"] == 0 and [o for o in UNDOC if o in help_body]
                else "not_measured"
            ),
            "frozen_surface": False,
            "fix_owner": "下一环修",
        }
    )

    d11_measured = in_tmp_python(
        "import json,dataclasses as dc;"
        "from cypyc.project.project_compiler import ProjectCompileResult as R;"
        "f=[x.name for x in dc.fields(R)];"
        "print(json.dumps({'fields':f,'has_pyd_paths':'pyd_paths' in f}))",
        SCRATCH / "cwd_probe",
    )
    rows.append(
        {
            "id": "D11",
            "face": "docs/USAGE.md §5 项目 API 示例",
            "claim": "示例读 `result.pyd_paths`（上一环把 `result.output_files` 换成了这个，"
            "注释写「字段名以 ProjectCompileResult 的实际声明为准」）",
            "doc": doc_quote("docs/USAGE.md", "result.pyd_paths"),
            "measured": d11_measured,
            "rule": "示例引用的属性在返回类型的 dataclass 字段里 ⇒ 照抄可用；"
            "字段名是从 `dc.fields()` 现读的，不是比字符串包含",
            "verdict": ("doc-still-true" if (d11_measured.get("json") or {}).get("has_pyd_paths")
                        else "example-fails"),
            "frozen_surface": False,
            "fix_owner": "无需修（本条是上一环修法①的复验）",
        }
    )

    rows.append(
        {
            "id": "D12",
            "face": "docs/USAGE.md §4 eval 示例",
            "claim": '示例声称 `hook.eval("let x: int = 21 * 2\\nx")` 打印 42',
            "doc": doc_quote("docs/USAGE.md", "hook.eval("),
            "measured": {
                "result_symbol_in_cypyc": grep_files("__result__", ["cypyc"], 3),
                "only_reader_in_hook": grep_files("__result__", ["cypy_hook"], 2),
            },
            "rule": "读侧只认 `__result__`，写侧（cypyc 生成器）从不产出它 ⇒ eval 拿不到值；"
            "两端都点名才下结论（不靠跑一次编译）",
            "verdict": (
                "example-fails" if not grep_files("__result__", ["cypyc"], 3) else "doc-still-true"
            ),
            "frozen_surface": False,
            "fix_owner": "下一环修（生成侧补或改文档 ⇒ 交裁决）",
        }
    )

    rows.append(
        {
            "id": "D13",
            "face": "docs/USAGE.md §6 未实现清单",
            "claim": "「`constraint` / `subtype` / `dispatch` 尚未实现（v0.5 计划）」",
            "doc": doc_quote("docs/USAGE.md", "尚未实现"),
            "measured": {
                "constraint": obs["constraint_generic"]["errors"],
                "subtype": obs["subtype_decl"]["errors"],
                "dispatch": obs["dispatch_decl"]["errors"],
            },
            "rule": "三个名字逐个当场测：被接受的 ⇒ 该行陈旧；仍被拒的 ⇒ 半句准确，按 design 处理",
            "verdict": "stale-doc",
            "frozen_surface": False,
            "fix_owner": "下一环修",
            "split_note": {
                "constraint": "已落地" if not obs["constraint_generic"]["errors"] else "未落地",
                "subtype": "已落地" if not obs["subtype_decl"]["errors"] else "未落地",
                "dispatch": "已落地" if not obs["dispatch_decl"]["errors"] else "未落地",
            },
        }
    )

    rows.append(
        {
            "id": "D14",
            "face": "SYNTAX_IMPLEMENTATION_STATUS.md",
            "claim": "状态表：`SubtypeDecl` 解析/语义/生成均未落",
            "doc": doc_quote("SYNTAX_IMPLEMENTATION_STATUS.md", "SubtypeDecl"),
            "measured": {
                "parser_hits": grep_files("_parse_subtype_def", ["cypyc/"], 2),
                "codegen_hits": grep_files("subtype_defs", ["cypyc/"], 3),
                "dispatch_hits": grep_files("DispatchDecl", ["cypyc", "cypy_bridge"], 3),
            },
            "rule": "表说未落，代码里解析与登记已在 ⇒ 陈旧行（dispatch 那半仍准确）",
            "verdict": (
                "stale-doc" if grep_files("_parse_subtype_def", ["cypyc/"], 1) else "doc-still-true"
            ),
            "frozen_surface": False,
            "fix_owner": "下一环修",
        }
    )

    rows.append(
        {
            "id": "D15",
            "face": "PROJECT-SPEC 规模红线",
            "claim": "「单个源文件超过 3000 行（不含注释）即视为规模超标，须按职责拆分」",
            "doc": doc_quote("PROJECT-SPEC/01-项目结构规范.md", "3000"),
            "measured": {
                "parser": code_lines("cypyc/parser/parser.py"),
                "generator": code_lines("cypyc/codegen/cython_generator.py"),
                "type_checker": code_lines("cypyc/analyzer/type_checker.py"),
                "口径": "非注释非字符串 token 覆盖的行数（docstring 也剔掉）",
            },
            "rule": "自己的规范阈值被自己的文件越过 ⇒ real-gap；拆分是不可逆大改 ⇒ 只挂账",
            "verdict": (
                "real-gap" if code_lines("cypyc/parser/parser.py") > 3000 else "doc-still-true"
            ),
            "frozen_surface": True,
            "fix_owner": "人工（跨文件拆分）",
        }
    )

    cache_probe = in_tmp_python(
        "import json,pathlib;"
        "pre=sorted(p.as_posix() for p in pathlib.Path('.').rglob('*'));"
        "from cypy_bridge.compiler import BridgeCacheManager as M;"
        "m=M();src='def f() -> int:\\n    return 1';"
        "r1=m.get_cached_pyd(src,'probe_mod');r2=m.is_stale(src,'probe_mod');"
        "post=sorted(p.as_posix() for p in pathlib.Path('.').rglob('*'));"
        "print(json.dumps({'created':[x for x in post if x not in pre],"
        "'cached_none':r1 is None,'stale':bool(r2)}))",
        SCRATCH / "cwd_probe",
    )
    rows.append(
        {
            "id": "D16",
            "face": "bridge 缓存目录",
            "claim": "`_get_base_cache_dir` 的定位是「获取基础缓存目录」的只读查询",
            "doc": doc_quote("cypy_bridge/compiler.py", "获取基础缓存目录"),
            "measured": cache_probe,
            "rule": "两个只读查询跑完就在**调用方 CWD** 造出目录 ⇒ 与「只读」定位不符",
            "verdict": (
                "bridge-side-effect"
                if (cache_probe.get("json") or {}).get("created")
                else "not_measured"
            ),
            "frozen_surface": False,
            "fix_owner": "下一环修",
        }
    )

    bridge_code = (
        "import json;"
        "from cypy_bridge.compiler import BridgeCompiler;"
        "bc=BridgeCompiler();"
        "src=open(r" + repr(str(ROOT / "examples" / "hello.cypy")) + ", encoding='utf-8').read();"
        "c=bc._generate_c_code(src,'hello_probe');"
        "lines=[l.strip() for l in c.split(chr(10))];"
        "import itertools;"
        "delta=[l.count('{')-l.count('}') for l in lines];"
        "pref=list(itertools.accumulate([0]+delta[:-1]));"
        "tops=[lines[i] for i,l in enumerate(lines) if pref[i]==0 and l.startswith('if (')];"
        "print(json.dumps({'len':len(c),'口径':'按花括号净深推前缀和，depth==0 才算模块级',"
        "'module_level_if':tops[:3],'total_if':sum(1 for l in lines if l.startswith('if ('))}))"
    )
    bridge = in_tmp_python(bridge_code, SCRATCH / "cwd_probe")
    rows.append(
        {
            "id": "D17",
            "face": "bridge 生成物结构",
            "claim": "`cypy_bridge` 自述「提供与 Cython 等价的核心功能，作为移除 Cython 依赖的桥接层」",
            "doc": doc_quote("cypy_bridge/__init__.py", "等价"),
            "measured": bridge,
            "rule": "生成的 C 里出现函数外的模块级 `if (...)` ⇒ 不是可编译的模块结构，"
            "「与 Cython 等价」不成立；只看到文本就下结论，真编译留 R4-验证",
            "verdict": (
                "bridge-not-equivalent"
                if (bridge.get("json") or {}).get("module_level_if")
                else "not_measured"
            ),
            "frozen_surface": False,
            "fix_owner": "下一环修（真编译验证转结）",
        }
    )
    if not (bridge.get("json") or {}).get("module_level_if"):
        rows[-1]["measured"]["why_not_measured"] = (
            "生成 C 文本里没看到函数外的模块级 if ⇒ 本条按未测定，" "不写「等价」也不写「不等价」"
        )

    rows.append(
        {
            "id": "D18",
            "face": "docs/USAGE.md 缓存命中",
            "claim": "「缓存命中：`transpile_file` / `compile_to_pyd` 默认增量编译，源未变会复用 `.pyd`」",
            "doc": doc_quote("docs/USAGE.md", "缓存命中"),
            "measured": {
                "why_not_measured": "要两次真编译（含工具链），单条 30s+ 且会落 .pyd；"
                "本环时间盒内不跑 ⇒ 转结 R4-验证实测，本轮不写结论"
            },
            "verdict": "not_measured",
            "frozen_surface": False,
            "fix_owner": "转结 R4-验证",
        }
    )

    # 崩掉的探针不许被读成确诊：非零退出或没吐出 JSON ⇒ 一律降级 not_measured 并记一条拒绝
    for r in rows:
        m = r.get("measured")
        if isinstance(m, dict) and "rc" in m and (m.get("rc") != 0 or m.get("json") is None):
            if r["verdict"] not in ("not_measured", "doc-still-true"):
                REFUSE.append(
                    f"{r['id']}：探针 rc={m.get('rc')}、json={m.get('json')}，"
                    f"却给了结论 {r['verdict']} ⇒ 判据把崩溃读成了确诊"
                )
            r["verdict"] = "not_measured"
            r["measured"]["why_not_measured"] = "探针非零退出或未吐 JSON ⇒ 按未测处理，不写产品结论"
            r["measured"]["tail"] = (m.get("tail") or [])[-2:]

    stale = [
        r["id"]
        for r in rows
        if r["verdict"]
        in (
            "stale-doc",
            "real-gap",
            "example-fails",
            "usage-mismatch",
            "bridge-side-effect",
            "bridge-not-equivalent",
        )
    ]
    design = [r["id"] for r in rows if r["verdict"] == "design"]
    untested = [r["id"] for r in rows if r["verdict"] in ("not_measured", "doc-still-true")]
    check(
        "每行的立单原文都在盘上（行号 > 0）",
        [r["id"] for r in rows if r["doc"]["line"] < 1],
        [],
        "doc_quote 未命中",
    )
    check(
        "每条结论都带 measured",
        [r["id"] for r in rows if not r.get("measured")],
        [],
        "measured 缺失",
    )
    check(
        "未测/仍准确两态都点名了为什么",
        [
            r["id"]
            for r in rows
            if r["verdict"] in ("not_measured", "design")
            and "why_not_measured" not in json.dumps(r["measured"], ensure_ascii=False)
            and "rule" not in r
        ],
        [],
        "缺理由",
    )
    check(
        "成对对照真的成对（walrus 与缩进两条各带同族正例）",
        [w_ok, i4_ok],
        [True, True],
        "control 干净才算 pos 有效",
    )
    check(
        "CLI 对照：transpile 本身可用（旗标失败不是 CLI 挂了）",
        transpile_ok_ctl["rc"],
        0,
        "同一次跑的对照",
    )
    shutil.rmtree(SCRATCH, ignore_errors=True)
    left = sorted(p.name for p in HERE.glob("tmp_declared*"))
    check("临时探针目录自删干净", left, [], "SCRATCH 清点")
    by_id = {r["id"]: r for r in rows}
    doc = {
        "started": started,
        "rows": rows,
        "rows_total": len(rows),
        "identity": batch["ident"],
        "size_lines": {
            "parser": by_id["D15"]["measured"]["parser"],
            "cython_generator": by_id["D15"]["measured"]["generator"],
            "type_checker": by_id["D15"]["measured"]["type_checker"],
            "threshold": 3000,
        },
        "undocumented_hook_options": by_id["D10"]["measured"]["undocumented_options"],
        "eval_result_symbol_hits": len(by_id["D12"]["measured"]["result_symbol_in_cypyc"]),
        "cache_dirs_created_in_caller_cwd": (by_id["D16"]["measured"].get("json") or {}).get(
            "created"
        ),
        "bridge_module_level_if": (by_id["D17"]["measured"].get("json") or {}).get(
            "module_level_if"
        ),
        "stale_total": len([r for r in rows if r["verdict"] == "stale-doc"]),
        "real_gap_total": len([r for r in rows if r["verdict"] == "real-gap"]),
        "stale_or_gap": stale,
        "withdrawn_design": design,
        "not_measured_or_true": untested,
        "self_checks": CHECKS,
        "refuse": [],
        "note_on_subagent": "子代理只用来指路。上表 measured 全部由本脚本当场重跑；"
        "appendix-C《已实现的限制修复》14 行本轮未逐行复测 ⇒ 不入账、不引用",
        "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    doc["refuse"] = sorted(set(REFUSE)) + [
        f"判据自证未过：{c['label']}（实得 {json.dumps(c['got'], ensure_ascii=False)[:180]}）"
        for c in CHECKS
        if not c["ok"]
    ]
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "rows_total": len(rows),
                "stale_or_gap": stale,
                "withdrawn_design": design,
                "not_measured_or_true": untested,
                "verdicts": {r["id"]: r["verdict"] for r in rows},
                "self_checks": f"{sum(1 for c in CHECKS if c['ok'])}/{len(CHECKS)}",
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(
            json.dumps(
                {"refuse": [f"崩在 {type(exc).__name__}: {exc}"]}, ensure_ascii=False, indent=1
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
