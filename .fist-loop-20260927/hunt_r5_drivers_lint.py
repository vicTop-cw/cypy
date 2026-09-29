"""R5-寻虫：本轮亲笔的判据脚本自身要过仓库 lint 口径（line-length=100，硬错零容忍）。

与上一环的两处收紧（不是放宽）：
- **硬错栏补上 F841**：`str.replace` 型补丁把变量改掉之后，"赋了值再没人用"就是那次改动的直接
  证据（本轮 `now_iso()` 自递归、`refuse, out = [], {}` 都是这一类）；
- **软账不再是「只记账不判红」**：上一环实测 `soft_total=0`，本轮把它当基线，条数回升即拒。
  基线是从 `advance_r4_drivers_lint.json` 现读的，不是我记得的数。

自带见证：合成一条必超 100 列的行（必须被抓）+ 一条干净行（不得被误抓）；合成目录用完必须清掉，
没清掉即拒（否则 lint 自己在污染被测面）。
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "hunt_r5_drivers_lint.json"
PREV = HERE / "advance_r4_drivers_lint.json"
PY = sys.executable
HARD = ["E9", "W605", "F821", "F7", "F63", "F841"]
DRIVERS = [
    "hunt_r5_analyzer.py",
    "hunt_r5_baselines.py",
    "hunt_r5_book.py",
    "hunt_r5_calllog_tally.py",
    "hunt_r5_cli_face.py",
    "hunt_r5_codegen.py",
    "hunt_r5_close_spec.py",
    "hunt_r5_declared.py",
    "hunt_r5_drivers_lint.py",
    "hunt_r5_faces.py",
    "hunt_r5_kit_from_r4.py",
    "hunt_r5_needles.py",
    "hunt_r5_progress.py",
    "hunt_r5_render_order.py",
    "hunt_r5_report_spec.py",
    "hunt_r5_self_audit.py",
]
REFUSE: list = []
CHECKS: list = []


def now_s() -> str:
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


def flake(paths: list, extra: list | None = None) -> list:
    cmd = [
        PY,
        "-m",
        "flake8",
        "--max-line-length=100",
        "--extend-ignore=E203,W503,W505",
        *(extra or []),
        *[str(p) for p in paths],
    ]
    p = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    return [ln for ln in (p.stdout or "").splitlines() if ln.strip()]


def tally(lines: list) -> dict:
    """flake8 行的路径在 Windows 上带盘符冒号 ⇒ 只能按 ` E501 ` 这种模式取码，不能按 split 下标。"""
    codes: dict = {}
    for ln in lines:
        m = re.search(r":\s+([EWFC]\d{2,4})\s", ln)
        code = m.group(1) if m else "?"
        codes[code] = codes.get(code, 0) + 1
    if "?" in codes and len(lines) != codes["?"]:
        codes["_parse_broken"] = codes.pop("?")
    return dict(sorted(codes.items()))


def main() -> int:
    started = now_s()
    OUT.write_text(
        json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    missing = [d for d in DRIVERS if not (HERE / d).exists()]
    if missing:
        REFUSE.append(f"清单里的脚本不在盘上（口径漏档就是无人认领的改动）：{missing}")
    on_disk = [HERE / d for d in DRIVERS if d not in missing]
    lines = flake(on_disk)
    hard = [ln for ln in lines if any(f" {c} " in ln for c in HARD)]
    soft = [ln for ln in lines if ln not in hard]
    prev = json.loads(PREV.read_text(encoding="utf-8")) if PREV.exists() else {}
    baseline = prev.get("soft_total")
    check(
        "上一环软账基线能从实测件现读（不是我记得的数）",
        isinstance(baseline, int),
        True,
        f"{PREV.name} → {baseline}",
        ok=isinstance(baseline, int),
    )
    if baseline is None:
        REFUSE.append(f"读不到上一环软账基线（{PREV.name} 缺失或没有 soft_total）⇒ 不许弃权")
    elif len(soft) > int(baseline):
        REFUSE.append(f"软账 {len(soft)} 条 > 上一环基线 {baseline} 条 ⇒ 只降不升")
    check(
        "硬错栏点名（含 F841）",
        sorted(set(re.findall(r"([EWFC]\d{2,4})\s", " ".join(hard)))),
        [],
        "逐码点名",
    )
    check(
        "扫描覆盖面 = 清单里在盘的脚本数",
        len(on_disk),
        len(DRIVERS) - len(missing),
        f"{len(on_disk)} 个",
    )

    tmp = Path(tempfile.mkdtemp(prefix="r5canary_", dir=str(HERE / "hunt_r5_tmp")))
    bad, good = tmp / "canary_bad.py", tmp / "canary_good.py"
    bad.write_text(
        "def f():\n    return " + " + ".join(["1"] * 40) + "  # 一条必然超 100 列的行\n",
        encoding="utf-8",
    )
    good.write_text("def f() -> int:\n    return 1\n", encoding="utf-8")
    bad_lines, good_lines = flake([bad]), flake([good])
    caught = [ln for ln in bad_lines if " E501 " in ln]
    if not caught:
        REFUSE.append(f"见证失败：合成超长行没被抓到（{bad_lines[:2]}）⇒ lint 格是恒绿的")
    if [ln for ln in good_lines if "E501" in ln]:
        REFUSE.append(f"见证失败：干净文件被判 E501（{good_lines[:2]}）⇒ 口径在误抓")
    check(
        "canary 两侧同件：违例必被抓、干净不误抓",
        [bool(caught), not [ln for ln in good_lines if "E501" in ln]],
        [True, True],
        f"bad={bad_lines[:1]} good={good_lines[:1]}",
    )
    shutil.rmtree(tmp, ignore_errors=True)
    left = sorted(p.name for p in (HERE / "hunt_r5_tmp").glob("*") if "r5canary" in p.name)
    if left:
        REFUSE.append(f"合成违例目录没清干净：{left}")

    doc = {
        "started": started,
        "window_start_note": "本轮亲笔（mtime 在本环号段内）",
        "drivers_scanned": len(on_disk),
        "driver_list": DRIVERS,
        "hard_violations": len(hard),
        "hard_lines": hard[:6],
        "hard_codes": HARD,
        "soft_total": len(soft),
        "soft_codes": tally(soft),
        "previous_round_soft_baseline": baseline,
        "baseline_source": PREV.name,
        "canary": {
            "bad_caught": len(caught),
            "clean_false_positive": 0 if not [ln for ln in good_lines if "E501" in ln] else 1,
        },
        "canary_left": left,
        "line_length_declared": 100,
        "ignore_declared": ["E203", "W503", "W505"],
        "note": "口径与上一环一致：仓库 pyproject 声明 line-length=100 与同款 extend-ignore",
        "self_checks": CHECKS,
        "refuse": [],
        "at_utc": now_s(),
    }
    red = [c["label"] for c in CHECKS if not c["ok"]]
    doc["refuse"] = sorted(set(REFUSE) | {f"判据自证未过：{x}" for x in red})
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                k: doc[k]
                for k in (
                    "refuse",
                    "drivers_scanned",
                    "hard_violations",
                    "soft_total",
                    "soft_codes",
                    "previous_round_soft_baseline",
                    "canary",
                    "canary_left",
                )
            }
            | {"self_checks": f"{len(CHECKS) - len(red)}/{len(CHECKS)}"},
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
                {"refuse": [f"崩在 {type(exc).__name__}: {exc}"], "at_utc": now_s()},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
