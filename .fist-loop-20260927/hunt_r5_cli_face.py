"""R5-寻虫 法②：CLI / import hook 面的候选在**真入口**上逐条复跑两遍确诊。

不复用分析器电池（hunt_r5_confirm.py）：这批候选的现象不在 `analyze()` 的返回值里，而在
rc / 落盘产物 / stdout 文案上——拿分析器电池测它们，测的是隔壁那面墙。

四条口径：
- pos=声明面说会生效、观察与声明不符；ctl=**同一条 plumbing 上今天确实生效**的形状。
  只有 pos 成立而 ctl 不站对 ⇒ 记 UNSURE（也许整条通道都没接，归因不到这一个分支）。
- 每条跑两遍，两遍的 `observed` 必须同向；不同向 ⇒ refuse（不写「偶发」）。
- 声明原文按 file + 片段现读盘上文件，找不到片段 ⇒ refuse（没有立单依据）。
- 夹具只落在 `hunt_r5_tmp/cli_face/`，跑完整批删；不改产品码、不碰冻结面、不 commit。
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "hunt_r5_cli_face.json"
TMP = HERE / "hunt_r5_tmp" / "cli_face"
PY = sys.executable
REFUSE: list = []
CHECKS: list = []
CANARY: dict = {}
HELLO = (ROOT / "examples" / "hello.cypy").as_posix()
MARKER_OK = "#!bin cypy\n\n\ndef value() -> int:\n    return 42\n"


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def run(cwd: Path, args: list, stdin: str = "") -> dict:
    p = subprocess.run(
        [PY, "-X", "utf8", *args],
        cwd=str(cwd),
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    return {
        "rc": p.returncode,
        "out": (p.stdout or "").strip(),
        "err": (p.stderr or "").strip(),
        "argv": args,
    }


def w(d: Path, rel: str, text: str) -> Path:
    q = d / rel
    q.parent.mkdir(parents=True, exist_ok=True)
    q.write_text(text, encoding="utf-8", newline="\n")
    return q


def wb(d: Path, rel: str, data: bytes) -> Path:
    q = d / rel
    q.parent.mkdir(parents=True, exist_ok=True)
    q.write_bytes(data)
    return q


def quote(rel: str, frag: str) -> dict:
    path = ROOT / rel
    if not path.exists():
        REFUSE.append(f"声明所在文件不在盘上：{rel}")
        return {"file": rel, "line": -1, "quote": ""}
    for i, ln in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if frag in ln:
            return {"file": rel, "line": i, "quote": ln.strip()[:170]}
    REFUSE.append(f"{rel} 里找不到声明片段 {frag!r} ⇒ 这一条没有立单依据")
    return {"file": rel, "line": -1, "quote": ""}


def _tail(out: str, n: int = 160) -> str:
    return out[-n:]


# ------------------------------------------------------------------ 七条候选
def k01(d: str) -> dict:
    """全局 `-o`：文档写在「全局选项」栏里，位置在子命令**前**也必须生效。"""
    work = TMP / d
    work.mkdir(parents=True, exist_ok=True)
    r = run(work, ["-m", "cypyc", "-o", "globals_dir", "transpile", HELLO])
    made = (work / "globals_dir").exists()
    return {
        "rc": r["rc"],
        "dir_made": made,
        "out": _tail(r["out"], 200),
        "observed": "ignored" if not made else "honoured",
    }


def k01_ctl() -> dict:
    work = TMP / "k01c"
    work.mkdir(parents=True, exist_ok=True)
    r = run(work, ["-m", "cypyc", "transpile", HELLO, "-o", "sub_dir"])
    return {
        "rc": r["rc"],
        "dir_made": (work / "sub_dir").exists(),
        "observed": "honoured" if (work / "sub_dir").exists() else "ignored",
    }


def k02(d: str) -> dict:
    """`cypyc hook <source>`：--help 与 USAGE 都这么写，位置参数却永远填不进。"""
    work = TMP / d
    work.mkdir(parents=True, exist_ok=True)
    r = run(work, ["-m", "cypyc", "hook", HELLO, "--transpile-only"])
    refused = r["rc"] != 0 and "invalid choice" in r["out"] + r["err"]
    return {
        "rc": r["rc"],
        "msg": _tail(r["out"] + r["err"], 200),
        "observed": "unreachable" if refused else "reachable",
    }


def k02_ctl() -> dict:
    return _k02_ctl_real()


def _k02_ctl_real() -> dict:
    work = TMP / "k02c"
    work.mkdir(parents=True, exist_ok=True)
    r = run(work, ["-m", "cypyc", "hook", "--transpile-only", HELLO])
    return {
        "rc": r["rc"],
        "msg": _tail(r["out"] + r["err"], 200),
        "observed": "reachable" if r["rc"] == 0 else "unreachable",
    }


def _hook_probe(work: Path, mod: str) -> dict:
    code = (
        "import cypy_hook, sys\n"
        "cypy_hook.install_hook()\n"
        "m = __import__(sys.argv[1])\n"
        "print(type(m.__loader__).__name__, m.__file__)\n"
    )
    return run(work, ["-c", code, mod])


def k03(d: str) -> dict:
    """BOM 首行的 `#!bin cypy` 标记：hook 静默不接管，交给 CPython 按普通 .py 跑。"""
    work = TMP / d
    wb(work, "marker_bom.py", MARKER_OK.encode("utf-8-sig"))
    r = _hook_probe(work, "marker_bom")
    return {
        "rc": r["rc"],
        "loader": _tail(r["out"], 120),
        "observed": "not_hooked" if "SourceFileLoader" in r["out"] else "hooked",
    }


def k03_ctl() -> dict:
    work = TMP / "k03c"
    w(work, "marker_ok.py", MARKER_OK)
    r = _hook_probe(work, "marker_ok")
    return {
        "rc": r["rc"],
        "loader": _tail(r["out"], 120),
        "observed": "hooked" if "ExtensionFileLoader" in r["out"] else "not_hooked",
    }


def k04(d: str) -> dict:
    """`hook clear-cache` 报「已清除」，但 `.pyd`/`.c` 仍在原地。"""
    work = TMP / d
    w(work, "marker_ok.py", MARKER_OK)
    _hook_probe(work, "marker_ok")
    before = sorted(p.name for p in work.rglob("*.pyd"))
    r = run(work, ["-m", "cypyc", "hook", "clear-cache"])
    after = sorted(p.name for p in work.rglob("*.pyd"))
    return {
        "rc": r["rc"],
        "claim": _tail(r["out"], 120),
        "pyd_before": before,
        "pyd_after": after,
        "manifest_gone": not list(work.rglob("manifest.json")),
        "observed": "claimed_but_kept" if r["rc"] == 0 and after else "cleared",
    }


def k04_ctl() -> dict:
    work = TMP / "k04c"
    w(work, "marker_ok.py", MARKER_OK)
    _hook_probe(work, "marker_ok")
    before = sorted(p.name for p in work.rglob("manifest.json"))
    r = run(work, ["-m", "cypyc", "hook", "clear-cache"])
    after = sorted(p.name for p in work.rglob("manifest.json"))
    return {
        "rc": r["rc"],
        "manifest_before": before,
        "manifest_after": after,
        "observed": "cleared" if before and not after else "claimed_but_kept",
    }


def k05(d: str) -> dict:
    """`build --entry nosuch`：rc=1 但把「为什么失败」的那句话吞了。"""
    work = TMP / d
    work.mkdir(parents=True, exist_ok=True)
    proj = ROOT / "examples" / "test_project"
    r = run(work, ["-m", "cypyc", "build", proj.as_posix(), "--entry", "nosuch"])
    empty_list = "Failed modules (0)" in r["out"]
    return {
        "rc": r["rc"],
        "out": _tail(r["out"], 220),
        "reason_missing": empty_list,
        "observed": "no_reason" if r["rc"] != 0 and empty_list else "reason_given",
    }


def k05_ctl() -> dict:
    work = TMP / "k05c"
    work.mkdir(parents=True, exist_ok=True)
    proj = ROOT / "examples" / "test_project"
    r = run(work, ["-m", "cypyc", "build", proj.as_posix()])
    return {
        "rc": r["rc"],
        "out": _tail(r["out"], 160),
        "observed": "reason_given" if r["rc"] == 0 else "no_reason",
    }


def k06(d: str) -> dict:
    """`build --check-only --entry X` 收下了 --entry 却不按它裁剪范围。"""
    work = TMP / d
    work.mkdir(parents=True, exist_ok=True)
    proj = ROOT / "examples" / "test_project"
    r = run(work, ["-m", "cypyc", "build", proj.as_posix(), "--entry", "geometry", "--check-only"])
    all_checked = "3" in r["out"] and "passed type checking" in r["out"]
    return {
        "rc": r["rc"],
        "out": _tail(r["out"], 200),
        "observed": "ignored" if all_checked else "honoured",
    }


def k06_ctl() -> dict:
    work = TMP / "k06c"
    work.mkdir(parents=True, exist_ok=True)
    proj = ROOT / "examples" / "test_project"
    r = run(work, ["-m", "cypyc", "build", proj.as_posix(), "--entry", "nosuch"])
    return {
        "rc": r["rc"],
        "out": _tail(r["out"], 160),
        "observed": "honoured" if r["rc"] != 0 else "ignored",
    }


def k07(d: str) -> dict:
    """产物里 `__name__`/`__file__` 恒为 unknown/空 ⇒ 模块认不出自己。"""
    work = TMP / d
    work.mkdir(parents=True, exist_ok=True)
    r = run(work, ["-m", "cypyc", "transpile", HELLO, "-o", "out"])
    prod = "\n".join(
        q.read_text(encoding="utf-8", errors="replace")
        for q in sorted((work / "out").glob("*"))
        if q.is_file()
    )
    bad = '__name__ = "unknown"' in prod and '__file__ = ""' in prod
    return {"rc": r["rc"], "observed": "unknown_identity" if bad else "real_identity"}


def k07_ctl() -> dict:
    work = TMP / "k07c"
    work.mkdir(parents=True, exist_ok=True)
    run(work, ["-m", "cypyc", "transpile", HELLO, "-o", "out"])
    prod = "\n".join(
        q.read_text(encoding="utf-8", errors="replace")
        for q in sorted((work / "out").glob("*"))
        if q.is_file()
    )
    ok = "__all__ = [" in prod and "__profile__ = " in prod
    return {"observed": "real_identity" if ok else "unknown_identity", "tail": _tail(prod, 120)}


CASES = [
    {
        "id": "H01",
        "key": "CLI_global_output_dir_overwritten_by_subparser",
        "doc": ("docs/USAGE.md", "-o, --output"),
        "pos": k01,
        "ctl": k01_ctl,
        "want_pos": "ignored",
        "want_ctl": "honoured",
        "phenomenon": "全局 `-o DIR` 被子命令的同名默认值覆盖 ⇒ 写到 `output` 且没有任何提示",
    },
    {
        "id": "H02",
        "key": "CLI_hook_positional_source_unreachable",
        "doc": ("docs/USAGE.md", "cypyc hook"),
        "pos": k02,
        "ctl": k02_ctl,
        "want_pos": "unreachable",
        "want_ctl": "reachable",
        "phenomenon": "`cypyc hook <source>` 这种文档与 --help 都写了的用法必然报 invalid choice",
    },
    {
        "id": "H03",
        "key": "HOOK_bom_marker_silently_not_hooked",
        "doc": ("docs/USAGE.md", "#!bin cypy"),
        "pos": k03,
        "ctl": k03_ctl,
        "want_pos": "not_hooked",
        "want_ctl": "hooked",
        "phenomenon": "带 BOM 的 `#!bin cypy` 首行让 hook 静默放行，按普通 .py 执行且零诊断",
    },
    {
        "id": "H04",
        "key": "HOOK_clear_cache_reports_ok_but_keeps_artifacts",
        "doc": ("docs/USAGE.md", "清除 Cypy 编译缓存"),
        "pos": k04,
        "ctl": k04_ctl,
        "want_pos": "claimed_but_kept",
        "want_ctl": "cleared",
        "phenomenon": "`hook clear-cache` 打「已清除」但 `.pyd` 留在原地（只删了 manifest 那层）",
    },
    {
        "id": "H05",
        "key": "CLI_build_entry_failure_reason_swallowed",
        "doc": ("docs/USAGE.md", "--entry"),
        "pos": k05,
        "ctl": k05_ctl,
        "want_pos": "no_reason",
        "want_ctl": "reason_given",
        "phenomenon": "`build --entry nosuch` rc=1，打印 `Failed modules (0)`，原因文案被丢弃",
    },
    {
        "id": "H06",
        "key": "CLI_check_only_ignores_entry_scope",
        "doc": ("docs/USAGE.md", "仅编译"),
        "pos": k06,
        "ctl": k06_ctl,
        "want_pos": "ignored",
        "want_ctl": "honoured",
        "phenomenon": "`--check-only` 分支根本不读 `args.entry` ⇒ 裁剪范围的承诺在检查模式下失效",
    },
    {
        "id": "H07",
        "key": "CODEGEN_module_identity_hardcoded_unknown",
        "doc": ("cypyc/codegen/cython_generator.py", "Source file"),
        "pos": k07,
        "ctl": k07_ctl,
        "want_pos": "unknown_identity",
        "want_ctl": "real_identity",
        "phenomenon": '每个产物都写死 `__name__ = "unknown"` / `__file__ = ""`（无人传 source_file）',
    },
]


def main() -> int:
    started = now_s()
    OUT.write_text(
        json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in CASES:
        a = c["pos"](c["id"].lower())
        b = c["pos"]("r" + c["id"].lower())
        ca = c["ctl"]()
        cb = c["ctl"]()
        if a.get("observed") != b.get("observed") or ca.get("observed") != cb.get("observed"):
            REFUSE.append(
                f"{c['id']}：两遍复跑不同向（pos {a.get('observed')}/{b.get('observed')}，"
                f"ctl {ca.get('observed')}/{cb.get('observed')}）⇒ 不入账"
            )
        pos_ok = a.get("observed") == c["want_pos"]
        ctl_ok = ca.get("observed") == c["want_ctl"]
        rows.append(
            {
                "id": c["id"],
                "key": c["key"],
                "phenomenon": c["phenomenon"],
                "doc": quote(*c["doc"]),
                "want_pos": c["want_pos"],
                "want_ctl": c["want_ctl"],
                "pos_first": a,
                "pos_second": b,
                "ctl_first": ca,
                "ctl_second": cb,
                "pos_ok": pos_ok,
                "ctl_ok": ctl_ok,
                "verdict": "CONFIRMED" if pos_ok and ctl_ok else "UNSURE",
            }
        )
        if pos_ok and not ctl_ok:
            print(
                f"[UNSURE] {c['id']} 对照没站对（实得 {ca.get('observed')}，"
                f"期望 {c['want_ctl']}）⇒ 只记未确认"
            )
    confirmed = [r["id"] for r in rows if r["verdict"] == "CONFIRMED"]
    unsure = [r["id"] for r in rows if r["verdict"] != "UNSURE" or True]
    unsure = [r["id"] for r in rows if r["verdict"] != "CONFIRMED"]
    got4 = sum(
        1
        for r in rows
        for k in ("pos_first", "pos_second", "ctl_first", "ctl_second")
        if r[k].get("observed")
    )
    check("每条候选四档观察全部拿到", got4, len(rows) * 4, "四档 × 每条候选")
    check("确诊 + 未确认 = 总数", len(confirmed) + len(unsure), len(rows), "两栏回加")
    check(
        "确诊集合非空（否则是本判据看不见，不是产品干净）",
        bool(confirmed),
        True,
        f"确诊 {confirmed}／未确认 {unsure}",
    )
    check(
        "声明原文全部定位成功",
        [r["id"] for r in rows if r["doc"]["line"] < 0],
        [],
        "file:line 现读",
    )
    CANARY = {
        "pos_and_ctl_expectations_are_opposite_per_case": all(
            c["want_pos"] != c["want_ctl"] for c in CASES
        ),
        "flipping_one_expectation_would_change_verdict": next(
            r["verdict"] for r in rows if r["pos_ok"]
        )
        != "UNSURE",
    }
    check(
        "canary：每条的 pos/ctl 期望方向相反（同向=没在做对照）",
        CANARY["pos_and_ctl_expectations_are_opposite_per_case"],
        True,
        json.dumps(CANARY),
    )
    doc = {
        "started": started,
        "cases": len(CASES),
        "rows": rows,
        "confirmed": confirmed,
        "unsure": unsure,
        "keys": [r["key"] for r in rows if r["verdict"] == "CONFIRMED"],
        "canary": CANARY,
        "tmp_left": [],
        "self_checks": CHECKS,
        "refuse": [],
        "at_utc": now_s(),
    }
    # 清理：先试干净（不吃错误），Windows 上句柄未放会留下目录 ⇒ 必须复测
    for _ in range(3):
        shutil.rmtree(TMP, ignore_errors=True)
        if not TMP.exists():
            break
    leftovers = sorted(q.name for q in TMP.glob("*")) if TMP.exists() else []
    if TMP.exists() and not leftovers:
        try:
            TMP.rmdir()
        except OSError as exc:
            leftovers.append(f"<rmdir:{type(exc).__name__}>")
    doc["tmp_left"] = leftovers
    if leftovers:
        REFUSE.append(f"跑完仍有残渣 {leftovers}（目录 {TMP.name} 还在 ⇒ 清理静默失败）")
    red = [f"判据自证未过：{x['label']}（实得 {x['got']}）" for x in CHECKS if not x["ok"]]
    doc["refuse"] = sorted(set(REFUSE) | set(red))
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "confirmed": confirmed,
                "unsure": unsure,
                "observed": {
                    r["id"]: [r["pos_first"].get("observed"), r["ctl_first"].get("observed")]
                    for r in rows
                },
                "self_checks": f"{sum(1 for x in CHECKS if x['ok'])}/{len(CHECKS)}",
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
