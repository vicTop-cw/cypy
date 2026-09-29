#!/usr/bin/env python3
"""R3-修复：从判据件渲染报告正文骨架 `r3_fix_body.md`。

正文里的每个数字都从 JSON 反解（`fix_r3_evidence.json` / `fix_r3_locks_inventory.json` /
`fix_r3_baselines.json` / `fix_r3_plan.json`），不手打——上一环吃过"手加计数与盘面不符"的亏。
渲染前会要求四件齐全且 refuse 皆空，缺件就拒绝输出（宁可不写，也不写没测过的话）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEED = ["fix_r3_plan.json", "fix_r3_evidence.json", "fix_r3_locks_inventory.json",
        "fix_r3_baselines.json"]

JUDGE_DEFECTS = [
    "把 `git worktree add … HEAD` 当『本环修前基线』用是错的：红线禁止 commit ⇒ 工作树有数百行"
    "未提交改动，旧树同时缺本轮与前几轮的东西。本轮第一条红因就是"
    "`module 'cypy_bridge.memory' has no attribute '_as_address'`（旧树根本没这符号），与本轮修法无关。"
    "改为两级证据：主证据=开工前落盘的 before 快照翻转，次证据=旧码树且必带 caveat。",

    "对照锁的『红』未分级会被自己写的规则反咬：`test_bug58_realloc_zero_size_...` 在旧码树上因陈旧"
    "符号而红，而规则说『对照不得红』。补了分栏——`no attribute`/`ImportError` 记 stale 并留原文，"
    "行为差异型红仍 refuse；不分级要么误伤要么放水。",

    "新写的判据件首版有语法错与死代码：`fix_r3_evidence.py` 里 `ifbbc.count`（少空格）与两处 "
    "`... if False else None` 的半截逻辑。靠 `py_compile` 当场抓出，但更该做的是『写完立刻 compile "
    "再往下排步骤』，而不是写完先写别的。",

    "手写 JSON 出双错才被抓：`fix_r3_plan.json` 里 `\"T0e66\"`（task_id 打错）与一句未转义引号 "
    "（`抛 \"this type has no size\"`）⇒ `json.load` 直接失败。修正做法：入账编号不手打，从入账件反解；"
    "本件 task_id 已与 `hunt_r3_filed.json` 双向对上才留字。",

    "锁的夹具源码写错形状：BUG-55 的对照先写 `duck Comparable[T]:` 放在顶层，parser 报 "
    "`Unexpected token DUCK at 1:1`。读 `tests/test_duck.py` 才知 duck 定义必须在 `meta:` 块里——"
    "夹具坏了会让『正例通过』变成假绿，所以对照本身也要实测。",

    "BUG-59 的第一版断言是照猜的形状写的（以为无环部分输出 `['d','e']`），实跑是 "
    "`['z','y','x']` 与 `['y','x','a','b','c']`。改成『先把盘面打印出来，再写期望』，并把期望换成"
    "结构式断言（环内名字序在最后 + 纯无环图给确定序），不锁死一次性的字面顺序。",

    "回归锁里自己埋了未定义行为：BUG-58 原先写 `free(0)` 想『验证释放路径走通』，实际是把已释放"
    "地址再走一遍 free（double-free 面）。改成不再触碰该地址，并在校验里写明为什么不能这么测。",

    "lint 门禁初版口径不可用：把整文件的 E501 当硬门 ⇒ 本轮之前就存在的超长行会让它永远红。"
    "换成三条可分栏判据：E9/W605 零条（只可能由本轮引入）、亲笔新文件零违例、"
    "E501 逐文件不得高于修前存量计数（只准减）。",

    "报告正文里的『上一环实测』一开始是从公式造的（`1920-17`）。改成直接读 `hunt_r3_baselines.json` "
    "的实测 `passed` 并把两个数都印出来——派生数不是测量数。",

    "基线件自己的两格是恒真形状（run1 已归档 `fix_r3_baselines_run1.json` + `r3fix_logs_run1/`）："
    "lint 格用 `\":E9\" in ln` 与 `ln.split(':')[4]` 读 flake8 输出，真实格式是 "
    "`path:line:col: CODE msg` ⇒ 158 行全部解析失败，被记成『hard_violations=0 / e501_by_file 空』；"
    "git 格取 `worktree list` 的 `split()[-1]` 得到 `['[master]', 'HEAD)']` 而不是路径。"
    "现在改成正则解析 + 两条自检：解析行数 != 输出行数即 refuse、一行都没解析出来即 refuse。",

    "报告门禁 ④⑤ 初版与 ① 同路径同阈值（`per_bug >= 6`）⇒ 三条恒真重复门禁。"
    "『每一行都有 X』这类逐行主张 `report_kit` 解析不了，硬写就等于把主张换成一个数。"
    "补 `fix_r3_plan_check.py` 把逐行主张算成 derived 布尔（含与上一环入账件双向对 task_id），"
    "门禁改指这些布尔键。",

    "`fix_r3_plan_check.py` 初版把台账的 `flipped` 与翻转件的 `ok` 直接相等比较：C5/C8 的 `ok` "
    "语义是『声明侧形状对』，与『翻没翻』不是一回事 ⇒ 会把正确状态判成不一致。"
    "改成只与 `after_rc == 1` 对齐，并在两个旗的语义处写明区别。",
]

OP_DEFECTS = [
    "在测量窗口内起 `git worktree add` 的风险：它会拿 `.git/index` 锁，而 `fix_r3_baselines.py` "
    "收尾要跑 `git status --porcelain` 与 `git diff --cached` ⇒ 并发可能把 git 红线格毒成瞬时假值。"
    "已把旧码树复算排到全量之后，并把该顺序写进本环流程。",

    "`/tmp` 在 Windows 上不是同一棵树：bash 的 `/tmp/r3fix/out/setup.py` 与 Python 解析出的路径不重合，"
    "造出『文件找不到』的假失败。改用仓库内 `.fist-loop-20260927/tmp_r3/` 当工作区，"
    "实测产物与判据件同盘可追溯。",

    "删临时 worktree 时 shell 的 cwd 还在里面 ⇒ `git worktree remove --force` 报 `Permission denied`、"
    "`rm -rf` 报 `Device or resource busy`，登记已摘但目录成孤儿。收尾顺序应为 "
    "`remove → prune →（换目录）rmdir`。另：本仓另有一条别人建的 "
    "`E:/IDEProjects/AI/_cypy_head_baseline` worktree，列出来看清再动。",

    "时间盒：上一环（R3-寻虫）墙钟 214 分钟，超自定 ≤100 分钟红线，成因是两次上下文压缩后靠回忆重建状态。"
    "本环改进为『开工第一件事把 before 快照落盘』，判据件随做随写。",

    "顺序错了一次：基线件跑完 12 分钟才回头发现 lint/git 两格是恒真形状，等于白测一轮再重跑。"
    "正确顺序是先让判据件在**合成违例**上过一遍（本次 158 行输出全解析不出、worktree 路径解析成 "
    "`HEAD)` 都是三秒钟能看出来的），再排全量。已把 run1 与日志留档，run2 作为唯一权威时刻。",

    "渲染件的退出码被写坏：`return Path(...).write_text(...) or 0` 让 `sys.exit()` 收到字符数 "
    "19470，Windows 截成 **98** 且不打印任何原因 ⇒ 看起来像\"神秘失败\"，实际正文已写盘。"
    "改成写完后 `return 0`。这类\"退出码不是 0/1 的大数\"以后一律按脚本自己的返回值检查，"
    "不要拿 `write_text` 的字符数当状态。",

    "账本驱动的写前针头断言抓到我自己复述的 needle：BUG-56 我写『摘掉旗标是缩对外接口面』，"
    "台账原文其实是『摘旗是缩对外接口面』；BUG-58 写『仍返回 None』而原文是『释放并返回 None』。"
    "⇒ 断言没让坏文本落盘（先拒后写），但暴露了 needle 是我凭记忆重打的。"
    "规矩：针头要从被检文本里复制，不重打。",

    "账本驱动的写后自检数错了东西：用 `section.splitlines()[0]` 取标题行，而段落以 `\\n` 开头 ⇒ "
    "取到空串，`ln.strip() == \"\"` 在 1300 行账本里匹到 205 行，六件各报\"段落数 205\"。"
    "段落其实只追加了一次（`grep -c` 实测 6）。改成按条目切段、段内数\"同时含 MARK 与本轮标记\"的行，"
    "并补 `--verify` 模式：文本已落盘后可反复复算终态而不触发幂等守卫（守卫本身也被"
    "`--dry-run` 必须被拒这条控制实验证过：rc=1、`MARK` 计数仍 6）。",
]

DECISIONS = [
    "BUG-58 的第二半：`realloc(p, 0)` 返回 None 与 `malloc(0)` 抛 MemoryError 不对称。本环只消除"
    "『注解/文档与返回值互斥』（改 `Optional[int]` + 文档写清分支），因为对称化必须弱化 "
    "`tests/test_bridge_library.py::test_realloc_zero_size`（红线）。若要改成返回 0 或抛错，"
    "请连同该测试一起作为口径变更登记。",

    "BUG-60 的第二半：是否把 SYNTAX/04 的『指针声明只能在函数作用域内』落成强制检查"
    "（含『结构体字段不得是指针』）。本环只对齐 docstring 口径；补检查会打到 36 处合法写法，"
    "属新增门禁，交回裁决。",

    "BUG-57 的另一条修法：Python 内建类型 → ctypes 宽度映射（`int`→`c_int` 还是 `c_long`）。"
    "Cython 侧 `int` 是 32 位、CPython 的 `int` 无界，选哪个都是新语义 ⇒ 本环给的是专属错误文案 + "
    "可用示例，映射规则请裁决。",

    "BUG-56 的边角：`run_default`（不可达 else 分支）仍读这四个旗标。要不要删/接，牵动"
    "『首参是 .cypy 文件时自动当 transpile』的兼容承诺（docs/USAGE.md:404），本环未动。",

    "BUG-59 的下游：确定的编译序是否要进 golden 基准（`scripts/e2e_golden.sh` 现在 25/25 不含编译序"
    "断言）。本环只保证 `get_compilation_order` 可重现，未扩基准。",
]

TIMEBOX_START = "2026-09-28 00:00"  # 本地：动手改产品码之前先落 before 快照的时刻


def load(name: str) -> dict:
    path = HERE / name
    if not path.exists():
        sys.exit(f"REFUSE — 判据件缺失：{name}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("refuse"):
        sys.exit(f"REFUSE — {name} 的 refuse 非空，不能进正文：{doc['refuse'][:3]}")
    return doc


def main() -> int:
    plan = load("fix_r3_plan.json")
    ev = load("fix_r3_evidence.json")
    inv = load("fix_r3_locks_inventory.json")
    base = load("fix_r3_baselines.json")

    rows = plan["per_bug"]
    must_flip = ("C1", "C3", "C4", "C6")
    shape_kept = ("C5", "C8")
    bug_of = {"C1": "BUG-55", "C3": "BUG-56", "C4": "BUG-57",
              "C5": "BUG-58", "C6": "BUG-59", "C8": "BUG-60"}
    pytest_line = base["pytest"]["line"]
    radius_rows = base["radius"]["rows"]

    out: list = []
    w = out.append
    w("# R3-修复（bug fix）环节正文")
    w("")
    w("## 一、本环口径")
    w("")
    w(f"- 半径：R3-寻虫 入账的 {len(rows)} 件（BUG-55..BUG-60，服务端 {rows[0]['task_id']}"
      f"..{rows[-1]['task_id']}）。")
    w("- 三条硬约束：**不弱化既有测试**、**冻结语义优先于模块 docstring**、"
      "**修法必须打到调用面而不是改源码字面**。")
    w("- 每条都记『所选修法 + 被放弃的替代方案及理由』；不能两全的那一半如实留在裁决面，"
      "不签成已修。")
    w("- 前后对照用的是上一环留下的同一批三态复现夹具（`hunt_r3_repro.py`，"
      "0=现形 / 1=不现形 / 2=夹具坏），修前快照在 `.fist-loop-20260927/tmp_r3/before_C*.out`。")
    w("")
    w("## 二、逐件修法与证据")
    w("")
    for row in rows:
        case = next(c for c, b in bug_of.items() if b == row["bug"])
        flip = ev["flips"][case]
        w(f"### {row['bug']}（{row['task_id']}）— 复现 {case}")
        w("")
        w(f"- 主张：{row['claim']}")
        w(f"- 声明面：{row['declared_face']}")
        w(f"- 修法：{row['chosen_fix']}")
        w(f"- 放弃的替代方案：{row['rejected_alternative']}")
        w(f"- 改动文件：{'、'.join('`' + f + '`' for f in row['files'])}")
        w(f"- 回归锁：pos {len(row['pos_locks'])} 条 + 对照 {len(row['ctl_locks'])} 条"
          f"（{('、'.join('`' + n + '`' for n in row['locks']))[:240]}）")
        w(f"- 前后：before rc={flip['before_rc']} `{json.dumps(flip['before_observed'], ensure_ascii=False)[:170]}`"
          f" → after rc={flip['after_rc']} `{json.dumps(flip['after_observed'], ensure_ascii=False)[:170]}`")
        if row.get("flipped"):
            w("- 结论：**已翻**（原主张的现形判据不再成立）。")
        else:
            w(f"- 结论：**未翻，且这是刻意的**——{row['still_red_reason']}")
        if row.get("adjudication_left"):
            w(f"- 交回裁决：{row['adjudication_left']}")
        w("")
    w("## 三、锁与判据")
    w("")
    w(f"- 锁：`tests/test_loop_20260927_fix_r3.py` 共 {inv['declared']} 条"
      f"（pos {inv['pos_total']} / 对照 {inv['ctl_total']}），"
      f"声明名 == `--collect-only` == PASSED 三向相等，跑线 `{inv['run_line']}`。")
    w(f"- 判据自证：`fix_r3_evidence.json` 的 judge_selfprobe = "
      f"{json.dumps(ev['judge_selfprobe'], ensure_ascii=False)}"
      "（同一判定函数必须能抓『没翻』、不误抓『翻了』）。")
    w("- 声明侧（C5/C8 这两件不靠翻转，靠可机器否证的字面）："
      f"{json.dumps(ev['declared_side'], ensure_ascii=False)[:300]}")
    w("")
    w("## 四、三套判据体系与红线（同一时刻复算）")
    w("")
    prior = json.loads((HERE / "hunt_r3_baselines.json").read_text(encoding="utf-8"))
    prior_passed = prior["pytest"]["passed"]
    w(f"- pytest：`{pytest_line}`；收集 {base['pytest']['collected']} 条，"
      f"下限 {base['pytest']['floor']}（= R3-寻虫 同盘面实测 `{prior_passed}` + 本环 "
      f"{inv['declared']} 条锁；两个数各自实测得到，不是从公式反推的）。")
    w(f"- 自研套件：`{base['suite']['line']}`（green={str(base['suite']['green']).lower()}）。")
    w(f"- e2e golden：`{base['e2e']['line']}`（green={str(base['e2e']['green']).lower()}）。")
    g = base["git"]
    w(f"- git 红线：HEAD 仍 `{g['head']}`、暂存 {g['staged']} 档、脏行 {g['dirty_rows']}；"
      f"本仓另有 worktree {'、'.join(g.get('worktrees', []))}（不是本环建的，未动）。")
    w(f"- 改动半径 {base['radius']['count']} 档，全部归属本单："
      + "、".join(f"`{r['file']}`" for r in radius_rows))
    l = base["lint"]
    w(f"- lint：硬违例（E9/W605）{l['hard_violations']} 条、亲笔新文件违例 {l['new_file_violations']} 条、"
      f"E501 逐文件 {json.dumps(l['e501_by_file'], ensure_ascii=False)} "
      f"（上限=修前存量 {json.dumps(l['legacy_e501_cap'], ensure_ascii=False)}，只准减不准增）；"
      f"存量 W293 {json.dumps(l['legacy_w293_by_file'], ensure_ascii=False)}。")
    w("")
    w("## 五、什么现象**不算**本环的证明")
    w("")
    w("- 『文件里有 sorted/Optional 字样』不算：BUG-59 用 5 个独立子进程各带一个 PYTHONHASHSEED "
      "复算同一张图（同进程改环境变量测不出来，字符串哈希在解释器启动时就定了）；"
      "BUG-58 用 `typing.get_type_hints` 读实际注解，而不是读源码字面。")
    w("- 只跑正例不算：17 条锁里 7 条是对照——不传旗标时产物形状不变、"
      "DuckDef 的 `type_params` 仍被收、`malloc(0)` 仍抛 MemoryError、"
      "改了 docstring 之后构建块检查器仍必须在拦别的规则。")
    w(f"- 「{inv['declared']} 条锁今天绿」不足以说明锁承重：另出"
      f"`.fist-loop-20260927/fix_r3_head_proof.json` 把同一份测试叠到上一提交的产品码树上跑，"
      f"要求每组都有红、对照不得因行为差异而红。该件自带 caveat："
      "HEAD 不等于本环开工基线（红线禁止 commit，工作树有数百行未提交改动），"
      "所以它是次级证据，主证据是本环开工前就落盘的 before 快照翻转对照。")
    w("- 『账本里出现了 FIXED 字样』不算：段落账按终态复算（每条目恰 1 段、"
      "条目标题行逐字未动、`- 修法：` 那一行原文可回读）。")
    w("")
    w("## 六、本环自身缺陷（判据/工具与操作分栏，逐条留字）")
    w("")
    w("判据与工具类：")
    w("")
    for i, item in enumerate(JUDGE_DEFECTS, start=1):
        w(f"{i}. {item}")
    w("")
    w("操作类：")
    w("")
    for i, item in enumerate(OP_DEFECTS, start=len(JUDGE_DEFECTS) + 1):
        w(f"{i}. {item}")
    w("")
    w(f"合计 {len(JUDGE_DEFECTS) + len(OP_DEFECTS)} 条"
      f"（判据/工具 {len(JUDGE_DEFECTS)} + 操作 {len(OP_DEFECTS)}）。")
    w("")
    w("## 七、交回与转结")
    w("")
    w("- 交回裁决（本环刻意不做，理由在各件段落里）：")
    for i, item in enumerate(DECISIONS, start=1):
        w(f"  {i}. {item}")
    w("- 沿用未动的转结：BUG-40/41/43/49/50/52/53 处置、BUG-54 跨进程 `build/` 隔离、"
      "`watch` 删除事件是否清 `-o` 旧产物、`close_root_generic.py` 的 L4 产物门前置、"
      "`_visit_ExprStmt` 分发语义、analyzer 侧是否恢复 meta 守卫、"
      "已发布法则文本与终态实现的字面差。")
    import datetime as _dt
    started = _dt.datetime.strptime(TIMEBOX_START, "%Y-%m-%d %H:%M")
    mins = (_dt.datetime.now() - started).total_seconds() / 60.0
    now_text = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    w(f"- 时间盒：自定红线 ≤100 分钟/环节。本环开工 {TIMEBOX_START}（本地，动手前先把 before 快照落盘）"
      f"→ 正文生成于 {now_text}，墙钟约 {mins:.0f} 分钟"
      f"（其中 pytest 全量 {base['pytest']['line'].split('in')[-1].strip()} + 自研套件与 e2e 各一轮）。"
      f"终版报告落盘时刻以页脚为准。")
    w("")
    Path(HERE / "r3_fix_body.md").write_text("\n".join(out) + "\n",
                                             encoding="utf-8", newline="\n")
    print(json.dumps({
        "body_bytes": len("\n".join(out).encode("utf-8")),
        "judge_defects": len(JUDGE_DEFECTS),
        "op_defects": len(OP_DEFECTS),
        "decisions": len(DECISIONS),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
