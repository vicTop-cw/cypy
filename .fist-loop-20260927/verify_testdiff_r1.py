"""R1-验证 law6：取证「既有测试没被弱化」——不用 mtime 归因，改用可复算的**只减不得**比对。

为什么换判据：第一版按 mtime 反解「本轮改过的测试文件」，再要求 diff 只剩那次改名。实测打回：
`tests/test_bridge_library.py` 的 mtime 是本轮改名的 11:46，但它对 HEAD 的 diff 是
`+427 / -3` —— 那 424 行是上一轮（09-26 打磨轮，未提交）加的测试。mtime 只能证明
「这个文件被碰过」，不能证明「这些行是谁加的」。⇒ 归因型判据在这里必然说谎。

现在的三条都不需要归因：
 a) 改名站点可数：HEAD 里就存在的 `tests/*.py` 中出现 `float32_` 的行 = 3（既有测试的三处按名引用），
    且旧名 `float_` 在**裸代码**（剥掉注释与字符串字面量）里残留 = 0；
    配套成对对照：合成真引用必被抓、`assert not hasattr(bt, "float_")` 的锁文案必不被抓；
 b) 逐文件「只减不得」：对每个已跟踪的 `tests/*.py`，当前 `def test_` 数与 `assert` 数
    都必须 ≥ HEAD 版本的同名计数（删测试/删断言会当场被抓）；
 c) skip/xfail/expectedFailure 标记总数一并记录（本轮不裁，供打磨轮定性）。
外加一条反例对照：内存里造一份「删掉一个 test 函数」的变体，判据必须把它判红。
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
TESTS = ROOT / "tests"
OLD_NAME = re.compile(r"(?<![\w])float_(?![\w])")


def bare_code(text: str) -> str:
    """剥掉注释与字符串字面量后的裸代码。

    判据 6a 要抓的是「旧名还在被当真名字用」，而 `assert not hasattr(bt, "float_")` 与
    docstring 里的 `float_` 恰恰是**断言它不存在**的锁文案——按整篇文本正则扫会把锁自己
    当成残留，第一轮就是这么自打的。
    """
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
        return " ".join(out)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return re.sub(r"#[^\n]*|\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''", "", text)


def git_show(rel: str) -> str:
    return subprocess.run(
        ["git", "show", f"HEAD:{rel}"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def counts(text: str) -> dict:
    return {
        "test_defs": len(re.findall(r"^\s*def test_", text, re.M)),
        "asserts": len(
            re.findall(r"\bassert(?:Equal|True|False|In|NotIn|Raises|AlmostEqual)?\b", text)
        ),
        "markers": sum(
            text.count(m)
            for m in ("@pytest.mark.skip", "@pytest.mark.xfail", "expectedFailure", "pytest.skip(")
        ),
    }


def is_shrunk(now: dict, head: dict) -> bool:
    return now["test_defs"] < head["test_defs"] or now["asserts"] < head["asserts"]


def main() -> int:
    refuse = []
    tracked = [
        l
        for l in subprocess.run(
            ["git", "diff", "--name-only", "--", "tests/"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.split()
        if l.startswith("tests/")
    ]

    tracked_at_head = set(
        subprocess.run(
            ["git", "ls-files", "--", "tests/"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.split()
    )
    renamed_sites = 0
    renamed_sites_new_files = 0
    stale_old_name = []
    shrink = {}
    marker_total = 0
    per_file = {}
    for path in sorted(TESTS.glob("test_*.py")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        # 只数「HEAD 里就存在的文件」中的改名站点：本轮新增的锁文件自己也用 float32_，
        # 混进来的话 3 会变成 7，判据就把「新增测试」误读成「改名站点变多」。
        if rel in tracked_at_head:
            renamed_sites += text.count("float32_")
        else:
            renamed_sites_new_files += text.count("float32_")
        if OLD_NAME.search(bare_code(text)):
            stale_old_name.append(rel)
        c_now = counts(text)
        marker_total += c_now["markers"]
        if rel in tracked:
            c_head = counts(git_show(rel))
            per_file[rel] = {"head": c_head, "now": c_now, "shrunk": is_shrunk(c_now, c_head)}
            if is_shrunk(c_now, c_head):
                shrink[rel] = {"head": c_head, "now": c_now}
        else:
            per_file[rel] = {"head": None, "now": c_now}

    if renamed_sites != 3:
        refuse.append(
            f"判据6a `tests/` 里 `float32_` 出现 {renamed_sites} 次，预期 3 次"
            f"（test_bridge_library.py 的 import/assertEqual/门面导入各一）"
        )
    if stale_old_name:
        refuse.append(
            f"判据6a 旧名 `float_` 仍在这些测试文件里作为独立标识符出现：{stale_old_name}"
        )
    if shrink:
        refuse.append(f"判据6b 有文件的测试数或断言数**少于** HEAD（删测试/删断言）：{shrink}")
    if not per_file:
        refuse.append("判据6b 没有任何已跟踪测试文件可比对，判据空转")

    # 反例对照：把某个文件删掉一个 test 函数，判据必须判红
    sample = next((r for r, v in per_file.items() if v["head"]), None)
    control = None
    if sample:
        text = (ROOT / sample).read_text(encoding="utf-8", errors="replace")
        cut = re.sub(r"^\s*def test_\w+[^\n]*\n(    .*\n|\n|\s*\n)*", "", text, count=1, flags=re.M)
        control = {
            "file": sample,
            "removed_chars": len(text) - len(cut),
            "caught": is_shrunk(counts(cut), counts(text)),
        }
        if not control["caught"]:
            refuse.append(f"判据6b 反例对照失效：删掉一个 test 函数后判据没判红（{control}）")

    # 6a 的成对对照：合成违例必须被抓，锁文案必须不被抓——否则「剥字面量」是把判据调松
    live_use = "from cypy_bridge.types import float_\nassertEqual(bt.float_, 4)\n"
    lock_text = 'assert not hasattr(bt, "float_"), "旧名 float_ 仍在"\n'
    old_name_control = {
        "live_use_caught": bool(OLD_NAME.search(bare_code(live_use))),
        "lock_text_caught": bool(OLD_NAME.search(bare_code(lock_text))),
        "unstripped_would_false_alarm": bool(OLD_NAME.search(lock_text)),
    }
    if not old_name_control["live_use_caught"]:
        refuse.append(f"判据6a 合成违例（真引用旧名）没被抓到 ⇒ 判据空转：{old_name_control}")
    if old_name_control["lock_text_caught"]:
        refuse.append(f"判据6a 把「断言旧名不存在」的锁文案误抓成残留：{old_name_control}")
    if not old_name_control["unstripped_would_false_alarm"]:
        refuse.append("判据6a 对照失效：锁文案里根本没有旧名字面量，这条对照没在测东西")

    doc = {
        "refuse": refuse,
        "renamed_sites": renamed_sites,
        "renamed_sites_new_files": renamed_sites_new_files,
        "stale_old_name": stale_old_name,
        "old_name_control": old_name_control,
        "tracked_modified": tracked,
        "per_file": per_file,
        "shrink": shrink,
        "negative_control": control,
        "skip_marker_total": marker_total,
        "note": "mtime 不做归因判据：test_bridge_library.py 对 HEAD 是 +427/-3，"
        "多出的 424 行来自 09-26 未提交轮次，本轮只改了 3 行",
    }
    (HERE / "verify_testdiff_r1.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": refuse,
                "renamed_sites": renamed_sites,
                "renamed_sites_new_files": renamed_sites_new_files,
                "stale_old_name": stale_old_name,
                "old_name_control": old_name_control,
                "tracked_modified": len(tracked),
                "shrunk": shrink,
                "negative_control": control,
                "skip_marker_total": marker_total,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
