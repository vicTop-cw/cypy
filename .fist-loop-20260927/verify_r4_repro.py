"""R4-验证 的三条新缺陷复跑件：退出码 0=现形 / 1=不现形 / 2=夹具坏。

每条都只走公开门面（CLI 子进程或 `CypyHook`/`CythonGenerator` 的公开调用），
断言写成**显式谓词**而不是「输出里有某字样」，这样卡片里的「复跑」命令才真能当证据用。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
TMP = HERE / "verify_r4_tmp" / "repro"

SLICE_TYPEFACE = ("def f() -> list<int>:\n    let xs: list<int> = [1, 2, 3, 4]\n"
                  "    return xs[1:3]\n")
DEMO = "examples/demos/upcoming_features/planned_features.cypy"
MATCH_TUPLE = ("def f(p) -> int:\n    match p:\n        case (0, 0):\n            return 0\n"
               "        case _:\n            return -1\n")


def cli(src_path: Path) -> tuple:
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "cypyc.cli", "transpile",
                        str(src_path), "-o", str(TMP / "out"), "--check-only"],
                       cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    text = ANSI_RE.sub("", (r.stdout or "") + (r.stderr or ""))
    diags = [ln.strip()[2:] for ln in text.splitlines() if ln.strip().startswith("- ")]
    return r.returncode, diags


def slice_typed_as_element() -> dict:
    """切片表达式被判成容器**元素**类型；仓内自带 DEMO 因此过不了 --check-only。"""
    TMP.mkdir(parents=True, exist_ok=True)
    p = TMP / "slice_typeface.cypy"
    p.write_text(SLICE_TYPEFACE, encoding="utf-8", newline="\n")
    rc, diags = cli(p)
    demo_rc, demo_diags = cli(ROOT / DEMO)
    present = (rc != 0 and any("got int" in d and "expected list[int]" in d for d in diags)
               and demo_rc != 0 and demo_diags)
    return {"present": bool(present), "probe": {"rc": rc, "diags": diags},
            "demo": {"file": DEMO, "rc": demo_rc, "diags_total": len(demo_diags),
                     "first": demo_diags[:2]},
            "predicate": "探针 rc!=0 且诊断里有「expected list[int], got int」，"
                         "并且仓内 DEMO 也过不了 --check-only"}


def codegen_named_conditions_unreachable() -> dict:
    """文档点名的三个 `_generate_*_condition` 在活路径上 0 调用，行为由别处就地生成。"""
    drv = TMP / "count_driver.py"
    drv.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import cypyc.codegen.cython_generator as cg\n"
        "from cypy_hook.hook import CypyHook\n"
        "names = ('_generate_tuple_condition', '_generate_array_condition',\n"
        "         '_generate_dict_condition', '_extractor_pattern_condition',\n"
        "         '_contains_extractor')\n"
        "hits = {n: 0 for n in names}\n"
        "for n in names:\n"
        "    f = getattr(cg.CythonGenerator, n)\n"
        "    def w(orig, key):\n"
        "        def inner(self, *a, **k):\n"
        "            hits[key] += 1\n"
        "            return orig(self, *a, **k)\n"
        "        return inner\n"
        "    setattr(cg.CythonGenerator, n, w(f, n))\n"
        "ast, errs = CypyHook().analyze_only(Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "code = cg.CythonGenerator('probe').generate(ast)\n"
        "print(json.dumps({'hits': hits, 'behaviour_in_code':\n"
        "                  'isinstance(_match_subject_1, (list, tuple))' in code}))\n",
        encoding="utf-8", newline="\n")
    src = TMP / "match_tuple.cypy"
    src.write_text(MATCH_TUPLE, encoding="utf-8", newline="\n")
    r = subprocess.run([sys.executable, "-X", "utf8", str(drv), str(src)], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=300)
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"present": None, "fixture_broken": (r.stderr or r.stdout)[-400:]}
    return {"present": bool(out["behaviour_in_code"] and not any(out["hits"].values())),
            "call_hits": out["hits"], "behaviour_generated_inline": out["behaviour_in_code"],
            "predicate": "元组模式的判定条件确实出现在生成物里，而这五个名字的调用计数全为 0"}


def pyd_no_cache_reuse() -> dict:
    """`compile_to_pyd` 连跑两次：产物被重写、`pyd_paths` 恒空、缓存查不到 ⇒ 文档的复用不成立。"""
    drv = TMP / "cache_driver.py"
    drv.write_text(
        "import json, os, sys, time\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from cypy_hook.hook import CypyHook, CypyCacheManager\n"
        f"SRC = {str(TMP / 'cache_src.cypy')!r}\n"
        f"OUT = {str(TMP / 'cache_out')!r}\n"
        "os.makedirs(OUT, exist_ok=True)\n"
        "hook, cm = CypyHook(), CypyCacheManager()\n"
        "def snap():\n"
        "    n = sorted(os.listdir(OUT)) if os.path.isdir(OUT) else []\n"
        "    return {x: os.stat(os.path.join(OUT, x)).st_mtime_ns\n"
        "            for x in n if x.endswith('.pyd')}\n"
        "a = snap()\n"
        "t = time.perf_counter()\n"
        "r1 = hook.compile_to_pyd(SRC, output_dir=OUT)\n"
        "d1 = time.perf_counter()-t\n"
        "b = snap()\n"
        "t = time.perf_counter()\n"
        "r2 = hook.compile_to_pyd(SRC, output_dir=OUT)\n"
        "d2 = time.perf_counter()-t\n"
        "c = snap()\n"
        "print(json.dumps({'pyd_first': list(b), 'pyd_second': list(c),\n"
        "                  'rewritten': b != c,\n"
        "                  'attrs1': sorted(k for k in vars(r1) if 'pyd' in k.lower()),\n"
        "                  'path1': getattr(r1, 'pyd_path', None),\n"
        "                  'path2': getattr(r2, 'pyd_path', None),\n"
        "                  'ok1': r1.success, 'ok2': r2.success,\n"
        "                  'steps1': list(r1.steps or [])[:6],\n"
        "                  'steps2': list(r2.steps or [])[:6],\n"
        "                  'cached_after': cm.get_cached_pyd(SRC),\n"
        "                  'stale_after': cm.is_stale(SRC),\n"
        "                  'dur': [round(d1,2), round(d2,2)]}))\n",
        encoding="utf-8", newline="\n")
    (TMP / "cache_src.cypy").write_text('def hi() -> str:\n    return "hi"\n',
                                        encoding="utf-8", newline="\n")
    r = subprocess.run([sys.executable, "-X", "utf8", str(drv)], cwd=str(TMP),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1200)
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"present": None, "fixture_broken": (r.stderr or r.stdout)[-400:]}
    present = bool(out["ok1"] and out["ok2"] and out["rewritten"]
                   and out["cached_after"] is None)
    return {"present": present, "measure": out,
            "predicate": "两轮都 success、第二轮 .pyd 被重写（mtime 变了）、"
                         "成功后 CypyCacheManager.get_cached_pyd 仍为 None"}


KEYS = {"SLICE_typed_as_element": slice_typed_as_element,
        "CODEGEN_named_conditions_unreachable": codegen_named_conditions_unreachable,
        "PYD_incremental_cache_not_reused": pyd_no_cache_reuse}


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    key = sys.argv[1] if len(sys.argv) > 1 else ""
    if key not in KEYS:
        print(json.dumps({"refuse": [f"未知 KEY：{key}（可选 {sorted(KEYS)}）"]},
                         ensure_ascii=False))
        return 2
    out = KEYS[key]()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if out.get("present") is None or "fixture_broken" in out:
        return 2
    return 0 if out["present"] else 1


if __name__ == "__main__":
    sys.exit(main())
