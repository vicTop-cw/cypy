"""文档面两单（BUG-66/BUG-67）的成对判据：文档说的与实现里现读的必须一致。

口径与寻虫环同一套（`docs/USAGE.md` 与 `pyproject.toml`/`--help`/dataclass 字段集三方对照）：
- 正例：本轮改过的每一条，文档文本与实现事实**现在一致**；
- 对照：不在冻结面里、但**本轮没权力改**的那一条（`SYNTAX/appendix-C` 的 `--compile` 行）
  必须仍然不一致并被记为 `still_open` —— 如果它也"一致"了，说明判据看不见差异或我偷偷动了冻结面；
- 反向对照：文档里不许出现实现里根本没有的旗标（`--incremental`）。
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "fix_r4_docs.json"
USAGE = ROOT / "docs" / "USAGE.md"
PYPROJECT = ROOT / "pyproject.toml"
APPENDIX = ROOT / "SYNTAX" / "appendix-C-features.md"
REFUSE: list = []
ROWS: list = []


def row(claim_id, doc, fact, agree, note=""):
    ROWS.append({"id": claim_id, "doc": doc, "measured": fact,
                 "verdict": "agreed" if agree else "still_open", "note": note})


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    usage = USAGE.read_text(encoding="utf-8")
    py = PYPROJECT.read_text(encoding="utf-8")
    appendix = APPENDIX.read_text(encoding="utf-8")

    py_floor = (re.search(r'requires-python\s*=\s*"([^"]+)"', py) or [None, "?"])[1]
    doc_floor = re.findall(r"Python \| ≥ ([\d.]+)", usage)
    row("D09 python 下限", f"docs/USAGE.md: Python ≥ {'/'.join(doc_floor)}",
        f"pyproject: requires-python={py_floor}", bool(doc_floor) and doc_floor[0] in py_floor)

    # 只看 `[project.scripts]` 段：把整个 TOML 的 key="value" 都当入口点会数进 name/version 等噪声
    scripts_txt = (py.split("[project.scripts]")[1].split("[")[0]
                   if "[project.scripts]" in py else "")
    scripts = re.findall(r'^(\w[\w-]*)\s*=\s*"([^"]+)"', scripts_txt, re.M)
    tail = usage.split("[project.scripts]")
    doc_lines = tail[-1].splitlines() if len(tail) > 1 else []
    doc_pairs = []
    for ln in doc_lines:
        if re.match(r"\s*(\[|```)", ln):
            break
        m = re.match(r'\s*(\w[\w-]*) = "([^"]+)"', ln)
        if m:
            doc_pairs.append((m.group(1), m.group(2)))
    doc_scripts = dict(doc_pairs)
    row("D08 入口点", json.dumps(doc_scripts, ensure_ascii=False),
        json.dumps(dict(scripts), ensure_ascii=False),
        doc_scripts == dict(scripts) and bool(doc_scripts))

    help_r = subprocess.run([sys.executable, "-X", "utf8", "-m", "cypyc.cli", "hook", "--help"],
                            cwd=str(ROOT), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=180)
    helptxt = (help_r.stdout or "") + (help_r.stderr or "")
    doc_opts = set(re.findall(r"cypyc hook (\[?--[a-z-]+\]?)", usage))
    doc_flags = {o.lstrip("[").rstrip("]") for o in doc_opts}
    missing = sorted(f for f in doc_flags if f.startswith("--") and f not in helptxt)
    row("D10 hook 选项清单", "文档列出的 hook 选项：" + ", ".join(sorted(doc_flags)),
        f"--help 里出现={sorted(f for f in doc_flags if f in helptxt)}；文档有而 help 没有={missing}",
        bool(doc_flags) and not missing)
    row("对照 不存在的旗标不得出现在文档", "--incremental / --compile 是否仍被 USAGE 引用",
        {"incremental_in_usage": "--incremental" in usage,
         "compile_in_usage": "--compile" in usage},
        "--incremental" not in usage,
        note="`hook --compile` 是真实选项（--help 现读），所以 --compile 可以出现；"
             "`build --incremental` 不是 ⇒ 反向对照钉的是 incremental")

    import inspect
    from cypyc.project.project_compiler import ProjectCompileResult

    real_fields = [f for f in inspect.signature(ProjectCompileResult).parameters]
    # 只钉「构建示例」那一段：文档里还有 TranspileResult 的示例（pyx_path/pyd_path 是它的字段），
    # 拿 ProjectCompileResult 去比所有 `result.X` 会把别的类型也算成缺陷
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", usage, re.S)
    build_block = next((b for b in blocks if "compiler.build(" in b), "")
    if not build_block:
        REFUSE.append("判据看不见样本：USAGE.md 里找不到含 compiler.build( 的代码块")
    doc_uses = re.findall(r"result\.(\w+)", build_block)
    bad = sorted({u for u in doc_uses if u not in real_fields})
    row("D11 构建产物字段", f"文档引用 result.{doc_uses}",
        f"ProjectCompileResult 实际字段={real_fields}",
        (not bad) and bool(doc_uses) and "pyd_paths" in doc_uses,
        note="文档示例里的每个属性都要在 dataclass 上真存在")

    hook_src = (ROOT / "cypy_hook" / "hook.py").read_text(encoding="utf-8")
    eval_returns_module = "return module" in hook_src.split("def eval")[-1][:900]
    doc_promise = "# 42" in usage
    row("D12 eval 返回值", "文档现在对 eval 示例的说明："
        + ("仍承诺 42" if doc_promise else "改写成「返回 import 进来的模块对象」"),
        {"写侧产出 __result__": bool(re.findall(r"__result__\s*=", hook_src)),
         "读侧只认 __result__": "hasattr(module, \"__result__\")" in hook_src,
         "今天落到 return module": eval_returns_module},
        (not doc_promise) and eval_returns_module,
        note="「写侧从不产出 __result__」这一半是产品缺口，本轮只改文档口径，"
             "生成侧补不在本单授权内 ⇒ 记为 half-open 转结")

    still_open = [r for r in ROWS if r["verdict"] == "still_open"]
    agreed = [r for r in ROWS if r["verdict"] == "agreed"]
    frozen_row = "cypyc --compile" in appendix
    check_appendix = {"appendix_still_claims_compile": frozen_row}
    if not frozen_row:
        REFUSE.append("对照失效：SYNTAX/appendix-C 的 `cypyc --compile` 行不见了 ⇒ "
                      "要么动了冻结面，要么对照本身看不见样本")
    if len(agreed) < 4:
        REFUSE.append(f"本轮该一致的行只有 {len(agreed)} 条（<4）⇒ 文档没真改到位")
    doc = {"started": started, "rows": ROWS, "agreed": [r["id"] for r in agreed],
           "still_open": [r["id"] for r in still_open],
           "frozen_control": check_appendix,
           "frozen_bytes_sha": hashlib_sha(APPENDIX),
           "half_open": ["D12：写侧 `__result__` 从不产出（生成侧缺口，交裁决）"],
           "note": "冻结面只读探针：appendix-C 的 stale 行必须仍然 stale，"
                   "它变一致了就说明本环动了冻结面",
           "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "agreed": doc["agreed"],
                      "still_open": doc["still_open"]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


def hashlib_sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


if __name__ == "__main__":
    sys.exit(main())
