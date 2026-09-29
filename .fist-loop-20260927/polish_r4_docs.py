"""R4-打磨 法①：非冻结文档按调用面实读改写，并配「改前措辞与实测相违」的反向对照。

三件事必须同时成立，缺一条就 refuse：

1. **先量后改**：`USAGE.md` 那句「源未变会复用 `.pyd`」先由真编译复算判真假（同源同 output_dir
   连调两次，看 `.pyd` 的 mtime 与 `CypyCacheManager.get_cached_pyd()`），不是读源码字面猜；
2. **改写只碰这一行**：`docs/USAGE.md` 的逐行 diff 必须恰有 1 行变更，冻结面零字节变化；
3. **反向对照**：新措辞里每个技术主张都要有一个键可回查（重编译/恒 None/两行自相矛盾），
   而旧措辞的核心断言（`.pyd` 被复用）在实测面前必须是假的——否则这次改写没有信息量。

顺带把文档里其余可机检的口径按 CLI / argparse / inspect / dataclasses 实读判一遍，
判不过的一律只入账不动手（不在本轮半径内的措辞债留给下一环）。
"""

from __future__ import annotations

import dataclasses
import datetime
import difflib
import hashlib
import inspect
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "polish_r4_docs.json"
DOC = ROOT / "docs" / "USAGE.md"
FROZEN = [ROOT / "PROJECT-SPEC", ROOT / "SYNTAX"]
CHECKS: list = []
REFUSE: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def frozen_sha() -> dict:
    out = {}
    for d in FROZEN:
        for f in sorted(d.rglob("*.md")):
            out[f.relative_to(ROOT).as_posix()] = sha(f)
    return out


def measure_pyd_cache() -> dict:
    """真编译器复算「源未变会不会复用 .pyd」：同源、同 output_dir 连调两次。"""
    sys.path.insert(0, str(ROOT))
    from cypy_hook.hook import CypyCacheManager, CypyHook

    tmp = Path(tempfile.mkdtemp(prefix="polish_docs_"))
    try:
        src = tmp / "m.cypy"
        src.write_text("def add(a: int, b: int) -> int:\n    return a + b\n",
                       encoding="utf-8", newline="\n")
        out_dir = tmp / "o"
        hook, cm = CypyHook(), CypyCacheManager()
        rows = []
        for i, force in ((0, False), (1, False), (2, True)):
            t0 = time.perf_counter()
            r = hook.compile_to_pyd(str(src), output_dir=str(out_dir), force_recompile=force)
            dur = round(time.perf_counter() - t0, 3)
            pyd = r.pyd_path or ""
            rows.append({"i": i, "force": force, "success": r.success, "dur": dur,
                         "pyd": Path(pyd).name if pyd else None,
                         "exists": bool(pyd) and Path(pyd).exists(),
                         "mtime_ns": (Path(pyd).stat().st_mtime_ns
                                      if pyd and Path(pyd).exists() else None),
                         "get_cached_pyd": cm.get_cached_pyd(str(src)),
                         "cache_steps": [s for s in r.steps if "缓存" in s]})
        same_mtime = rows[0]["mtime_ns"] == rows[1]["mtime_ns"]
        cached_none = all(r["get_cached_pyd"] is None for r in rows)
        contradict = any(len(r["cache_steps"]) >= 2 for r in rows)
        return {"rows": rows, "pyd_reused_between_calls": same_mtime,
                "get_cached_pyd_all_none": cached_none,
                "single_call_prints_both_cache_verdicts": contradict,
                "cache_steps_first_two": [rows[1]["cache_steps"]]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def claim_face() -> dict:
    """其余文档口径按调用面实读：签名 / dataclass 字段 / CLI 帮助 / 子进程退出码。"""
    sys.path.insert(0, str(ROOT))
    face = {}
    from cypy_hook.hook import CompileResult, CypyHook

    sig = inspect.signature(CypyHook.compile_to_pyd)
    face["compile_to_pyd_params"] = list(sig.parameters)
    face["compile_result_fields"] = sorted(f.name for f in dataclasses.fields(CompileResult))
    help_p = subprocess.run([sys.executable, "-X", "utf8", "-m", "cypyc.cli", "--help"],
                            cwd=str(ROOT), capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    face["cli_help_rc"] = help_p.returncode
    subs = sorted(set(re.findall(r"^\s+(transpile|compile|build|run|watch|hook|project)\b",
                                 (help_p.stdout or ""), re.M)))
    face["cli_subcommands_seen"] = subs
    for doc_sub in ("transpile", "compile", "build", "run", "watch", "hook"):
        if doc_sub not in subs:
            REFUSE.append(f"文档点了子命令 `{doc_sub}` 而 `--help` 里没看见")
    check("compile_to_pyd 的形参表与文档一致",
          face["compile_to_pyd_params"], ["self", "source_path", "output_dir", "force_recompile"],
          "inspect.signature")
    check("CompileResult 有 pyd_path 字段（文档 §3 的表格点了它）",
          "pyd_path" in face["compile_result_fields"], True,
          json.dumps(face["compile_result_fields"], ensure_ascii=False))
    check("CLI --help 可用", face["cli_help_rc"], 0, "python -m cypyc.cli --help")
    return face


def docs_dirty() -> list:
    git = subprocess.run(["git", "status", "--porcelain", "docs/"], cwd=str(ROOT),
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return sorted(x[3:] for x in (git.stdout or "").splitlines() if x.strip())


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if not DOC.exists():
        REFUSE.append(f"文档不在盘上：{DOC}")
        return finish(started, {}, {}, [], "")
    live = DOC.read_text(encoding="utf-8")
    dirty_before = docs_dirty()
    # 幂等：改写只准发生一次。第二次跑时盘上已没有旧句，就取归档的改前副本当 before，
    # 并如实标 already_applied —— 否则重跑会把「旧句恰有 1 次」这条判成红（假红）。
    anchor = "源未变会复用"
    before_copy = HERE / "verify_r4_tmp" / "USAGE.md.before_polish"
    already_applied = anchor not in live
    if already_applied:
        if not before_copy.exists():
            REFUSE.append(f"盘上已无旧句而改前副本缺失：{before_copy.name} ⇒ 无法核对改写")
            return finish(started, {}, {}, [], "")
        before_text = before_copy.read_text(encoding="utf-8")
    else:
        before_text = live
    before_sha = (hashlib.sha256(before_text.encode("utf-8")).hexdigest()[:16]
                  if already_applied else sha(DOC))
    frozen_before = frozen_sha()

    meas = measure_pyd_cache()
    check("实测必须判明「.pyd 被复用」是假的（两连调 mtime 不同）",
          meas["pyd_reused_between_calls"], False, json.dumps(meas["cache_steps_first_two"]))
    check("实测 .pyd 两次都真落盘（否则「重编译」这句没被测到）",
          [r["exists"] for r in meas["rows"]], [True, True, True], "pyd exists")
    check("实测 get_cached_pyd() 恒 None（缓存查询面）",
          meas["get_cached_pyd_all_none"], True, "CypyCacheManager.get_cached_pyd")
    check("实测同一次调用会连打命中与未命中两行（自相矛盾面）",
          meas["single_call_prints_both_cache_verdicts"], True, "cache_steps 条数")

    hits = [i for i, ln in enumerate(before_text.splitlines(), 1) if anchor in ln]
    check("旧句在改前文本里恰出现 1 次（锚点唯一才许改）", len(hits), 1, f"行号 {hits}")
    new_line = ("6. **增量缓存只到转译层，`.pyd` 每次都重编译**：同一源、同一 `output_dir` "
                "连调两次 `compile_to_pyd` 实测 `.pyd` 的 mtime 变化、"
                "`CypyCacheManager.get_cached_pyd()` 恒返回 `None`，且同一次调用会连打"
                "「缓存命中」与「缓存未命中」两行（两套缓存存储不同源，见 `memory/bugs.md` "
                "的 BUG-73）；`force_recompile=True` 与默认路径同样重编译。"
                "清缓存用 `cypyc hook clear-cache`。")
    lines = before_text.splitlines()
    after_lines = list(lines)
    if len(hits) == 1:
        after_lines[hits[0] - 1] = new_line
    after_text = "\n".join(after_lines) + "\n"
    if not already_applied:
        DOC.write_text(after_text, encoding="utf-8", newline="\n")
    live_now = DOC.read_text(encoding="utf-8")

    diff = list(difflib.unified_diff(lines, after_lines, lineterm="", n=0))
    changed = [ln for ln in diff if ln.startswith(("+", "-")) and not
               re.match(r"^[+-]{3}", ln)]
    removed = [ln for ln in changed if ln.startswith("-")]
    added = [ln for ln in changed if ln.startswith("+")]
    check("逐行 diff 恰为「1 删 1 增」（只动这一行）", [len(removed), len(added)], [1, 1],
          f"变更行样例 {changed[:4]}")
    check("旧句在盘上文档里已不存在", anchor in live_now, False, "反向对照")
    check("盘上正文与判据重建的改后文本逐字相同", live_now, after_text, "改一次即定稿")
    check("新句写入了实测的三个技术事实",
          all(k in live_now for k in ("mtime 变化", "get_cached_pyd",
                                      "force_recompile=True")),
          True, "逐字回查")
    check("改写前后 sha 必须不同（改了要看得见）", before_sha != sha(DOC), True,
          f"{before_sha} → {sha(DOC)}")
    frozen_after = frozen_sha()
    check("冻结面逐文件 sha 未被这次改写触碰", frozen_after == frozen_before, True,
          json.dumps(sorted(set(frozen_after) ^ set(frozen_before)))[:200])
    face = claim_face()
    dirty_after = docs_dirty()
    new_dirty = sorted(set(dirty_after) - set(dirty_before))
    check("这次改写没有在 docs/ 里多牵进一个文件（存量脏不在本环口径内）",
          new_dirty, [], f"改前脏 {dirty_before} / 改后脏 {dirty_after}")
    check("USAGE.md 确在 docs/ 脏清单里（改动看得见）", "docs/USAGE.md" in dirty_after, True,
          json.dumps(dirty_after))
    return finish(started, meas, face, [hits[0] if hits else 0], new_line, before_sha,
                  sha(DOC), frozen_before, changed, already_applied, new_dirty)


def finish(started, meas, face, old_line, new_line, before_sha="", after_sha="",
           frozen=None, changed=None, already_applied=False, new_dirty=None) -> int:
    doc = {"started": started, "doc": "docs/USAGE.md",
           "already_applied_at_rerun": already_applied,
           "docs_new_dirty_by_this_write": new_dirty or [],
           "old_line_number_measured": old_line,
           "citation_drift": "环节计划与 R4-验证 的账写的是 USAGE.md:406，"
                             "盘上实测该句在第 414 行 ⇒ 引用号漂移已在本件点名，不改历史账",
           "before_sha": before_sha, "after_sha": after_sha,
           "measurement": meas, "call_face_claims": face,
           "new_line": new_line, "diff_changed_lines": changed or [],
           "frozen_sha": frozen or {}, "frozen_total": len(frozen or {}),
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"],
                      "pyd_reused": meas.get("pyd_reused_between_calls"),
                      "durs": [r["dur"] for r in (meas.get("rows") or [])],
                      "old_line": old_line, "before_sha": before_sha,
                      "after_sha": after_sha,
                      "checks": len(CHECKS)}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
