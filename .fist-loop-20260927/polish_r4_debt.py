"""R4-打磨 法④：判据件骨架收敛到 `loop_kit.py`，等价性拿**归档件里的真实输入**核对。

收敛最容易说谎的地方是「我重构了，行为没变」这句。所以这里不重跑任何旧环判据件
（重跑旧件 = 渲染输入件漂移，R4-验证 刚为此记过账），而是：

* 把旧件**已经记下**的摘要行原文取出来，喂给新解析器，逐字段与旧件记的数对一遍；
* 快照复制器与一份参考实现（`shutil.copytree`）在同一目录上比文件集合与逐文件 sha；
* canary：一条畸形摘要行必须解析为零而不是被猜成某个数；
* 债务按「还了多少 / 还剩多少」分栏点名，不许把没动的面写成已收敛。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import loop_kit as KIT  # noqa: E402

OUT = HERE / "polish_r4_debt.json"
ARTS = ["verify_r4_baselines.json", "fix_r4_baselines.json", "advance_r3_baselines.json"]
CHECKS: list = []
REFUSE: list = []


def rec(label, got, want, why) -> None:
    KIT.record(CHECKS, REFUSE, label, got, want, why)


def reference_copy(src: Path, dst: Path, suffixes: tuple) -> set:
    """参考实现：同一套排除规则，但按 copytree 的直觉写法独立实现一遍。"""
    got = set()
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if not f.is_file() or (suffixes and f.suffix not in suffixes):
            continue
        if any(part in {"__pycache__", ".git", ".pytest_cache"} for part in rel.parts[:-1]):
            continue
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst / rel)
        got.add((rel.as_posix(), hashlib.sha256(f.read_bytes()).hexdigest()[:12]))
    return got


def systems_of(d: dict) -> dict:
    """两种历史形状都要吃：R4 件的 `systems` 嵌套，与 R3/修复环件的顶层平铺。"""
    if isinstance(d.get("systems"), dict):
        return d["systems"]
    return {"pytest": d.get("pytest") or {}, "suite": d.get("suite") or {},
            "collect": d.get("collect") or {}, "e2e": d.get("e2e") or {}}


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    equiv, missing, empty = [], [], []
    for name in ARTS:
        p = HERE / name
        if not p.exists():
            missing.append(name)
            continue
        sysd = systems_of(json.loads(p.read_text(encoding="utf-8")))
        rows_before = len(equiv)
        py = sysd.get("pytest") or {}
        line = py.get("summary_line") or ""
        if line:
            got = KIT.parse_pytest_summary(line)
            keys = ("passed", "failed", "errors", "skipped")
            equiv.append({"artifact": name, "kind": "pytest", "line": line,
                          "kit": {k: got.get(k) for k in keys},
                          "recorded": {k: py.get(k, 0) for k in keys}})
        sl = (sysd.get("suite") or {}).get("line") or ""
        if sl:
            equiv.append({"artifact": name, "kind": "suite", "line": sl,
                          "kit": KIT.parse_kv_line(sl),
                          "recorded": (sysd.get("suite") or {}).get("fields") or {}})
        if len(equiv) == rows_before:
            empty.append(name)
    if missing:
        REFUSE.append(f"等价核对缺件（没有真实输入可喂）：{missing}")
    if empty:
        REFUSE.append(f"这些件里没取到任何摘要行（形状不认识，别当成「无需比对」）：{empty}")
    shape_div = []
    for e in equiv:
        for k, v in e["recorded"].items():
            if isinstance(v, str) and v.isdigit():
                shape_div.append(f'{e["artifact"]}:{e["kind"]}.{k} 旧件记成字符串 "{v}"')
                e["recorded"][k] = int(v)
    bad = [e for e in equiv if e["kit"] != e["recorded"]]
    rec("新解析器对旧件记录的每一行都逐字段相等（行为不变的正面证据）",
        [b["artifact"] + ":" + b["kind"] for b in bad], [], json.dumps(bad[:2])[:400])
    rec("旧件之间的**形状差异**必须被点名（R3 把套件计数存成字符串，不许静默归一）",
        bool([s for s in shape_div if s.startswith("advance_r3_")]), True,
        json.dumps(shape_div[:6]))
    rec("等价核对至少 3 条比对且覆盖两份以上归档件",
        [len(equiv) >= 3, len({e["artifact"] for e in equiv}) >= 2], [True, True],
        f"{len(equiv)} 条 / {len({e['artifact'] for e in equiv})} 份件")

    junk = KIT.parse_pytest_summary("nothing interesting here\n........ [100%]")
    rec("canary：畸形/无摘要的文本必须解析为零而不是猜数",
        [junk["passed"], junk["failed"], junk["errors"]], [0, 0, 0], junk["summary_line"])
    good = KIT.parse_pytest_summary("1976 passed in 423.40s")
    rec("canary 不误抓：正常摘要行必须解析出该数", good["passed"], 1976, good["summary_line"])

    src = ROOT / "scripts"
    tmp = Path(tempfile.mkdtemp(prefix="debt_kit_"))
    try:
        a_dir, b_dir = tmp / "a", tmp / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        n_kit = KIT.copy_tree(src, a_dir, (".py", ".sh"))
        ref = reference_copy(src, b_dir, (".py", ".sh"))
        kit_set = {(f.relative_to(a_dir).as_posix(),
                    hashlib.sha256(f.read_bytes()).hexdigest()[:12])
                   for f in a_dir.rglob("*") if f.is_file()}
        rec("快照复制器与参考实现复制到的文件集合逐字相同",
            [len(kit_set), kit_set == ref], [n_kit, True], f"kit={len(kit_set)} ref={len(ref)}")
        rec("复制器真的复制到了东西（空集合会让上一条恒真）", n_kit > 0, True, f"{n_kit} 个文件")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    drivers = sorted(HERE.glob("verify_r4_*.py")) + sorted(HERE.glob("fix_r4_*.py")) \
        + sorted(HERE.glob("polish_r4_*.py")) + sorted(HERE.glob("advance_r3_*.py"))
    inline = {}
    for pat in ("def check(", "passed|failed|errors?", "Total:", "rglob"):
        inline[pat] = sorted(f.name for f in drivers
                             if pat in f.read_text(encoding="utf-8", errors="replace"))
    users = sorted(f.name for f in HERE.glob("polish_r4_*.py")
                   if "import loop_kit" in f.read_text(encoding="utf-8"))
    rec("本环新件确实在用共用骨架（不许只建模块不接线）",
        "polish_r4_debt.py" in users, True, json.dumps(users))
    git = subprocess.run(["git", "status", "--porcelain", ".fist-loop-20260927/loop_kit.py"],
                         cwd=str(ROOT), capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    kit_present = bool((git.stdout or "").strip())
    rec("共用件确在盘上并进了改动半径", kit_present, True, (git.stdout or "").strip())

    kit_apis = sorted(k for k in dir(KIT)
                      if not k.startswith("_") and k not in ("re", "shutil", "Path"))
    used_arts = [m for m in ARTS if m not in missing]
    doc = {"started": started, "kit": "loop_kit.py", "kit_apis": kit_apis,
           "equivalence": equiv, "shape_divergence": shape_div,
           "shape_divergence_len": len(shape_div),
           "equivalence_artifacts": used_arts,
           "copy_tree_face": {"files": n_kit, "matches_reference": kit_set == ref},
           "canary": {"junk_zero": [junk["passed"], junk["failed"], junk["errors"]],
                      "good_1976": good["passed"]},
           "debt_remaining_inline": {k: v for k, v in inline.items()},
           "debt_remaining_counts": {k: len(v) for k, v in inline.items()},
           "kit_users_this_ring": users,
           "scope_note": "本轮只把**新写的件**接进共用骨架；旧环 48/41 个件按四类骨架逐件点名留债，"
                         "不重跑（重跑＝改动上一环的渲染输入证据）。换骨架属于下一环的半径。",
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "equiv_rows": len(equiv),
                      "copy_files": n_kit, "kit_users": users,
                      "debt_counts": doc["debt_remaining_counts"]},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
