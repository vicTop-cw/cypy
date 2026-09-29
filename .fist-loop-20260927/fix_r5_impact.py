"""R5-修复 的语义影响面（法⑤）：同一批语料在 HEAD 引擎与当前引擎各跑一遍，差异只许来自产品码改动。

口径：
- 语料文本从盘上现读一次，**同一串**喂给两棵树 ⇒ 差异不可能来自输入不同；
- 可比面 = `transpile()` 的成功位 + 错误清单（两棵树都有这个 API）；
  `analyze_only()` 在 HEAD 上根本不存在（实测 AttributeError），所以那一栏只记账、不参与判定，
  并把「分析器诊断面在 HEAD 不可比」写成显式 not_measured，而不是假装测过；
- 三张表分别点名：修前无诊断→修后有诊断（new_diagnostics）、修前可编译→修后被拒（new_rejections）、
  修前被拒→修后可编译（new_acceptances，改好的那部分也要如实写，不许只报忧或只报喜）；
  两档都有错但错的内容变了记在 shape_changed。
- 命中不是「没问题」也不是「自动放行」：new_diagnostics/new_rejections 都进 adjudication，交 ledger 挂账。

对照四条（否则比较器可能恒说不等或恒说相等）：
- 对照0：两档都必须有 transpile 这个可比 API；
- 对照0b：analyze_only 的存在性逐档记录，不一致就必须把诊断面标成 not_measured（不许拿它下结论）；
- 对照1：一条两棵树都该同形的最小源 ⇒ 观察必须一致；
- 对照2：一条两棵树都该拒绝的坏源 ⇒ 任何一档给出 success=True 就是判据坏了。
"""

from __future__ import annotations

import datetime
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "fix_r5_impact.json"
SNAP = HERE / "fix_r5_snap" / "head_impact"
PY = sys.executable
CORPUS_DIRS = ("examples", "test_suite", "docs", "omega", "Find_BUG")
CORPUS_EXT = (".cypy",)
RUNNER = """
import sys, json
root = sys.argv[1]
sys.path.insert(0, root)
from cypy_hook.hook import CypyHook
import cypyc.analyzer.type_checker as tc
hook = CypyHook()
API = {"analyze_only": hasattr(hook, "analyze_only"), "transpile": hasattr(hook, "transpile")}
rows = []
for name, src in json.loads(sys.stdin.read()):
    row = {"file": name, "ok": None, "code_len": 0, "err": [], "ana": None}
    try:
        res = hook.transpile(src)
        row["ok"] = bool(getattr(res, "success", False))
        row["code_len"] = len(getattr(res, "cython_code", None) or "")
        row["err"] = [str(x) for x in (getattr(res, "errors", None) or [])]
    except Exception as exc:
        row["ok"] = False
        row["err"] = ["TRANSPILE-EXC " + type(exc).__name__ + ": " + str(exc)[:180]]
    if API["analyze_only"]:
        try:
            _, e = hook.analyze_only(src)
            row["ana"] = [str(x) for x in (e or [])]
        except Exception as exc:
            row["ana"] = ["ANALYZE-EXC " + type(exc).__name__ + ": " + str(exc)[:180]]
    rows.append(row)
print(json.dumps({"ident": tc.__file__, "api": API, "rows": rows}, ensure_ascii=False))
"""
CHECKS: list = []
REFUSE: list = []
# 这句话是「主张」不是「测量」：只有对照0b 保证它与两档 API 实测一致，改 API 面就必须改这句
CHANNEL_TEXT = (
    "not_measured：HEAD 的 CypyHook 没有 analyze_only（实测 AttributeError），两档 API 面不等"
    "⇒ 分析器诊断面不写结论；本件的 new_diagnostics 走的是 transpile 错误面"
)


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


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


def build_head_tree() -> int:
    if SNAP.exists():
        import shutil

        shutil.rmtree(SNAP)
    SNAP.mkdir(parents=True)
    paths = ["cypyc", "cypy_hook", "cypy_bridge", "pyproject.toml"]
    p = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", *paths],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=600,
    )
    if p.returncode != 0:
        REFUSE.append(f"git archive HEAD 失败：{p.stderr.decode('utf-8', 'replace')[:180]}")
        return 0
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as tf:
        tf.extractall(SNAP)
    return sum(1 for _ in SNAP.rglob("*.py"))


def corpus() -> list:
    out = []
    for d in CORPUS_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for f in sorted(base.rglob("*")):
            if f.is_file() and f.suffix in CORPUS_EXT:
                out.append(
                    (
                        f.relative_to(ROOT).as_posix(),
                        f.read_text(encoding="utf-8-sig", errors="replace"),
                    )
                )
    return out


def run_tree(tree: Path, items: list) -> dict:
    p = subprocess.run(
        [PY, "-X", "utf8", "-c", RUNNER, str(tree)],
        cwd=str(tree),
        input=json.dumps(items, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    if p.returncode != 0:
        REFUSE.append(f"{tree.name} 引擎跑挂 rc={p.returncode}：{(p.stdout + p.stderr)[-300:]}")
        return {"api": {}, "rows": []}
    got = json.loads(p.stdout.strip().splitlines()[-1])
    want = (tree / "cypyc" / "analyzer" / "type_checker.py").as_posix().lower()
    if Path(got["ident"]).as_posix().lower() != want:
        REFUSE.append(f"{tree.name} 档跑的不是自己的 type_checker：期望 {want} 实得 {got['ident']}")
    return got


def main() -> int:
    started = now_iso()
    items = corpus()
    if not items:
        REFUSE.append("语料一封都没数到 ⇒ 影响面没有输入，比较器无从判")
    n_py = build_head_tree()
    if not n_py:
        REFUSE.append("HEAD 引擎树没建起来 ⇒ 没有对照面，影响面无从比")
        return finish(started, [], [], [], [], 0, {}, {}, 0, "not_measured")
    root_got = run_tree(ROOT, items)
    head_got = run_tree(SNAP, items)
    root_rows, head_rows = root_got["rows"], head_got["rows"]
    if len(root_rows) != len(items) or len(head_rows) != len(items):
        REFUSE.append(
            f"回的行数不齐：语料 {len(items)} / 当前 {len(root_rows)} / HEAD {len(head_rows)}"
        )

    api = {"head": head_got.get("api", {}), "current": root_got.get("api", {})}
    comparable = bool(api["head"].get("transpile")) and bool(api["current"].get("transpile"))
    ana_same = api["head"].get("analyze_only") == api["current"].get("analyze_only")

    by_head = {r["file"]: r for r in head_rows}
    by_root = {r["file"]: r for r in root_rows}
    new_diag, new_rej, new_acc, shape_changed = [], [], [], []
    for name, cur in sorted(by_root.items()):
        old = by_head.get(name)
        if old is None:
            continue
        if not old["err"] and cur["err"]:
            new_diag.append({"file": name, "verbatim": cur["err"][:3]})
        if old["ok"] and not cur["ok"]:
            new_rej.append({"file": name, "verbatim": cur["err"][:3]})
        if not old["ok"] and cur["ok"]:
            new_acc.append({"file": name, "head_verbatim": old["err"][:2], "len": cur["code_len"]})
        if old["err"] and cur["err"] and old["err"] != cur["err"]:
            shape_changed.append(
                {"file": name, "head": old["err"][0][:140], "cur": cur["err"][0][:140]}
            )

    same_src = [("canary_same.cypy", "def f() -> int:\n    return 1\n")]
    bad_src = [("canary_bad.cypy", "def f(:\n")]
    c_head, c_root = run_tree(SNAP, same_src)["rows"], run_tree(ROOT, same_src)["rows"]
    b_head, b_root = run_tree(SNAP, bad_src)["rows"], run_tree(ROOT, bad_src)["rows"]
    agree = (
        bool(c_head)
        and bool(c_root)
        and c_head[0]["ok"] == c_root[0]["ok"]
        and c_head[0]["err"] == c_root[0]["err"]
    )
    both_reject = bool(b_head) and bool(b_root) and not b_head[0]["ok"] and not b_root[0]["ok"]
    named = sum(1 for r in new_diag + new_rej if r.get("verbatim"))
    canary = {
        "transpile_comparable": comparable,
        "analyze_only_same_surface": ana_same,
        "same_source_agrees": agree,
        "bad_source_rejected_both": both_reject,
        "same_source_head": c_head[:1],
        "same_source_current": c_root[:1],
    }

    check(
        "对照0：两档都必须有 transpile 这个可比 API（没有就没有影响面主张）",
        comparable,
        True,
        f"api={api}",
    )
    why = (
        f"HEAD analyze_only={api['head'].get('analyze_only')} / "
        f"当前={api['current'].get('analyze_only')} ⇒ 交付件里写的是 {CHANNEL_TEXT.split('：')[0]}"
    )
    check(
        "对照0b：交付件里的诊断面口径必须跟着实测 API 差异走（不可比却写 measured=在编结论）",
        CHANNEL_TEXT.startswith("not_measured"),
        not ana_same,
        why,
    )
    diag_note = CHANNEL_TEXT.split("：")[0]
    check(
        "对照1：两棵树对同一条干净源必须给同一种观察（不同=比较器在编差异）",
        agree,
        True,
        f"HEAD={c_head[:1]} 当前={c_root[:1]}",
    )
    check(
        "对照2：两棵树对同一条坏源都必须拒绝（有一档说成功=判据坏了）",
        both_reject,
        True,
        f"HEAD={b_head[:1]} 当前={b_root[:1]}",
    )
    check(
        "语料覆盖率：HEAD 与当前必须都观察到全部语料（缺一档就没有对照面）",
        [len(head_rows), len(root_rows)],
        [len(items), len(items)],
        f"HEAD {len(head_rows)} / 当前 {len(root_rows)} / 语料 {len(items)}",
    )
    check(
        "每条命中都必须带逐字文案点名（只报数不报文案=含糊）",
        named,
        len(new_diag) + len(new_rej),
        f"点名 {named} / 命中 {len(new_diag) + len(new_rej)}",
    )
    adjud = sorted({r["file"] for r in new_diag} | {r["file"] for r in new_rej})

    return finish(
        started,
        new_diag,
        new_rej,
        new_acc,
        shape_changed,
        adjud,
        len(items),
        api,
        canary,
        n_py,
        diag_note,
    )


def finish(
    started,
    new_diag,
    new_rej,
    new_acc,
    shape_changed,
    adjud,
    corpus_total,
    api,
    canary,
    n_py,
    diag_note="not_measured",
) -> int:
    doc = {
        "started": started,
        "corpus_total": corpus_total,
        "corpus_dirs": [d for d in CORPUS_DIRS if (ROOT / d).exists()],
        "head_tree": {"dir": SNAP.relative_to(ROOT).as_posix(), "py_files": n_py},
        "api_surface": api,
        "diagnostics_channel": CHANNEL_TEXT,
        "self_checks": CHECKS,
        "self_checks_red": [c["label"] for c in CHECKS if not c["ok"]],
        "new_diagnostics": new_diag,
        "new_rejections": new_rej,
        "new_acceptances": new_acc,
        "shape_changed": shape_changed,
        "diagnostics_note_state": diag_note,
        "new_diagnostics_len": len(new_diag),
        "new_rejections_len": len(new_rej),
        "new_acceptances_len": len(new_acc),
        "shape_changed_len": len(shape_changed),
        "corpus_adjudication_files": adjud,
        "adjudication_needed": len(adjud),
        "canary": canary,
        "note": "语料文本同一串喂两棵树；变差命中交 fix_r5_ledger.py 挂账，本件不裁决也不放行；"
        "改好的那部分（new_acceptances）与变差的那部分同屏列出。",
        "refuse": sorted(set(REFUSE)),
        "at_utc": now_iso(),
    }
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "corpus_total": corpus_total,
                "new_diagnostics": len(new_diag),
                "new_rejections": len(new_rej),
                "new_acceptances": len(new_acc),
                "shape_changed": len(shape_changed),
                "adjudication_needed": len(adjud),
                "api_surface": api,
                "canary": {k: v for k, v in canary.items() if not k.startswith("same_source")},
                "red_checks": doc["self_checks_red"],
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
        import traceback

        last = (traceback.format_exc().strip().splitlines() or [""])[-1]
        OUT.write_text(
            json.dumps(
                {"refuse": [f"崩在 {type(exc).__name__}: {exc} @ {last}"], "at_utc": now_iso()},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc} @ {last}"}, ensure_ascii=False))
        sys.exit(2)
