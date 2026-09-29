# R3-修复（bug fix）环节正文

## 一、本环口径

- 半径：R3-寻虫 入账的 6 件（BUG-55..BUG-60，服务端 T0r63..T0r68）。
- 三条硬约束：**不弱化既有测试**、**冻结语义优先于模块 docstring**、**修法必须打到调用面而不是改源码字面**。
- 每条都记『所选修法 + 被放弃的替代方案及理由』；不能两全的那一半如实留在裁决面，不签成已修。
- 前后对照用的是上一环留下的同一批三态复现夹具（`hunt_r3_repro.py`，0=现形 / 1=不现形 / 2=夹具坏），修前快照在 `.fist-loop-20260927/tmp_r3/before_C*.out`。

## 二、逐件修法与证据

### BUG-55（T0r63）— 复现 C1

- 主张：generic_transformer 读 type_params，parser 的泛型节点带的是 generic_params ⇒ 泛型收集恒为空
- 声明面：cypyc/transformer/generic_transformer.py:5『注册泛型参数』
- 修法：_collect_generics 同时认 generic_params 与 type_params（前者是 FuncDef/StructDef 的叫法，后者是 DuckDef 的叫法，两族都得收）
- 放弃的替代方案：把 parser 的属性改名成 type_params：会撞 SYNTAX/11-generics 的既有语义面与 3 个 analyzer + 1 个 codegen 读取点，改一处牵四文件
- 改动文件：`cypyc/transformer/generic_transformer.py`
- 回归锁：pos 1 条 + 对照 1 条（`test_bug55_generic_params_nodes_are_collected`、`test_bug55_duck_def_type_params_still_collected`）
- 前后：before rc=0 `{"generic_nodes": 1, "collected": 0}` → after rc=1 `{"generic_nodes": 1, "collected": 1}`
- 结论：**已翻**（原主张的现形判据不再成立）。

### BUG-56（T0r64）— 复现 C3

- 主张：cypyc transpile 的 --check-only/--emit-ast/--generate-setup/--emit-cython 只印给用户，run_transpile 一个都不读
- 声明面：docs/USAGE.md:66-70 与 `transpile --help`；四条承诺逐字可对照
- 修法：在 run_transpile 里落地四个旗标：check_only 走 CypyHook._parse_and_analyze 且不产码；emit_ast 打印解析后的节点树；emit_cython 打印 .pyx 文本；generate_setup 用 SetupGenerator 在产物目录写 setup.py。bridge 模式下 emit_cython 明确回话『这里产的是 C』而不是静默
- 放弃的替代方案：把四个旗标从 CLI 上摘掉：手册与 --help 已对外承诺，摘旗是缩对外接口面，且违反指挥官裁定「接线而不是砍 CLI」
- 改动文件：`cypyc/cli.py`
- 回归锁：pos 5 条 + 对照 1 条（`test_bug56_check_only_reports_and_generates_nothing`、`test_bug56_check_only_fails_on_broken_source`、`test_bug56_emit_ast_prints_parsed_nodes`、`test_bug56_emit_cython_prints_cython_code`、`test_bug56_generate_setup_writes_buildable_script`、`）
- 前后：before rc=0 `{"flag_readers": {"run_default": ["check_only", "emit_ast", "emit_cython", "generate_setup"], "run_build": ["check_only"]}}` → after rc=1 `{"flag_readers": {"run_transpile": ["check_only", "emit_ast", "emit_cython", "generate_setup"], "run_default": ["check_only", "emit_ast", "emit_cython", "generate_setup"]`
- 结论：**已翻**（原主张的现形判据不再成立）。

### BUG-57（T0r65）— 复现 C4

- 主张：CUnion/union 的 docstring 示例 CUnion(int, float) 一跑就抛 TypeError（对 Python 内建类型取 ctypes.sizeof）
- 声明面：cypy_bridge/union.py:23-31 与 :179 的示例文本；同文件 __init__ 自述『可以是ctypes类型或类型名称字符串』
- 修法：示例改成文档自己承诺的两种可用形状（ctypes 类型 / C 类型名字符串）；对 Python 内建类型给 UnionTypeError 并写清可接受形状，不再让 ctypes 抛『this type has no size』这种看不懂的错
- 放弃的替代方案：把 int/float 隐式映射到 c_int/c_double：Cython 的 int/float 宽度（32 位）与 CPython 的 int（64 位）不同，选哪个都是新的语义决定，SYNTAX/26 未对 bridge 侧 CUnion 定宽 ⇒ 属裁决面，本轮不代作
- 改动文件：`cypy_bridge/union.py`
- 回归锁：pos 2 条 + 对照 1 条（`test_bug57_documented_member_shapes_work`、`test_bug57_builtin_member_type_is_diagnosed`、`test_bug57_union_docstrings_advertise_only_runnable_shapes`）
- 前后：before rc=0 `{"raised": "TypeError: this type has no size"}` → after rc=1 `{"raised": "UnionTypeError: Union member 'int' is a Python builtin type; pass a ctypes type (ctypes.c_int) or a "}`
- 结论：**已翻**（原主张的现形判据不再成立）。

### BUG-58（T0r66）— 复现 C5

- 主张：realloc(ptr, 0) 先 free 再 return None，而签名是 -> int、文档只说返回地址
- 声明面：cypy_bridge/memory.py:195-216
- 修法：注解改 Optional[int]，docstring 写明 size<=0 走 C 的 realloc(p,0) 口径（释放并返回 None），并说明它与 malloc(0) 抛 MemoryError 不是同一条规则
- 放弃的替代方案：改成返回 0 或抛 MemoryError：既有 tests/test_bridge_library.py::test_realloc_zero_size 断言 assertIsNone(result)，改返回值必须弱化/删除既有测试 ⇒ 撞红线。行为半边的不对称留裁决
- 改动文件：`cypy_bridge/memory.py`
- 回归锁：pos 1 条 + 对照 2 条（`test_bug58_realloc_annotation_matches_return_shape`、`test_bug58_realloc_zero_size_still_returns_none_and_frees`、`test_bug58_control_malloc_zero_still_raises`）
- 前后：before rc=0 `{"returned": "None", "annotation": "int"}` → after rc=0 `{"returned": "None", "annotation": "Optional"}`
- 结论：**未翻，且这是刻意的**——C5 的现形判据钉的是『返回 None』这一半，那半边被既有测试钉住；本环只消除注解/文档与返回值的互斥，observed 里 annotation 已从 int 变 Optional
- 交回裁决：realloc(p,0) 是否应改为返回 0（并与 malloc(0) 对称）——若改，须同轮改既有测试并记为口径变更

### BUG-59（T0r67）— 复现 C6

- 主张：get_compilation_order 把环内模块塞进 set 再 extend ⇒ 环存在时推荐编译序随进程哈希种子变化
- 声明面：cypyc/project/module_dependency_graph.py:200-212（文档只说『跳过循环中的模块』）
- 修法：extend(sorted(cycle_modules)) ⇒ 同一张图在任何 PYTHONHASHSEED 下给同一推荐序，环内模块仍排在最后且按名字定序
- 放弃的替代方案：只改文档补一句『环内顺序不定』：把不可重现构建写成规格，等于放弃 topological_sort 那半边已经保证的确定性
- 改动文件：`cypyc/project/module_dependency_graph.py`
- 回归锁：pos 1 条 + 对照 0 条（`test_bug59_compilation_order_stable_across_hash_seeds`）
- 前后：before rc=0 `{"per_seed_orders": {"0": "['d', 'b', 'c', 'a', 'e']", "1": "['d', 'e', 'a', 'b', 'c']", "7": "['d', 'b', 'a', 'c', 'e']", "42": "['c', 'e', 'b', 'd', 'a']", "99": "['e',` → after rc=1 `{"per_seed_orders": {"0": "['a', 'b', 'c', 'd', 'e']", "1": "['a', 'b', 'c', 'd', 'e']", "7": "['a', 'b', 'c', 'd', 'e']", "42": "['a', 'b', 'c', 'd', 'e']", "99": "['a',`
- 结论：**已翻**（原主张的现形判据不再成立）。

### BUG-60（T0r68）— 复现 C8

- 主张：BuildBlockChecker 的 docstring 规则 2（指针语法只能在构建块内部使用）没有实现
- 声明面：cypyc/analyzer/build_block_checker.py:5-6 对 :75-84
- 修法：规则 2 按 SYNTAX/04-pointer-types.md『指针使用限制』重写：指针声明的合法位置是函数作用域，构建块只是其中一种；并写明指针寻址合法性/所有权检查在 pointer_checker，本模块不重复把关
- 放弃的替代方案：补实现（块外指针就报错）：会打断仓库里 36 处 `: *t` 的合法写法，且与冻结层 SYNTAX/04 直接冲突——冻结语义优先于模块 docstring
- 改动文件：`cypyc/analyzer/build_block_checker.py`
- 回归锁：pos 1 条 + 对照 1 条（`test_bug60_docstring_rule2_aligns_with_frozen_syntax`、`test_bug60_control_other_rules_still_enforced`）
- 前后：before rc=0 `{"node_kinds": ["PointerType"], "errors": []}` → after rc=0 `{"node_kinds": ["PointerType"], "errors": []}`
- 结论：**未翻，且这是刻意的**——C8 的现形判据是『块外指针不报错』，而按 SYNTAX/04 那正是期望行为：入账主张里的『要么补实现』半边经冻结层核对后不成立，只有 docstring 那半边是真缺陷
- 交回裁决：是否把『结构体字段不能是指针』这条 SYNTAX 限制落成检查（本环未做）

## 三、锁与判据

- 锁：`tests/test_loop_20260927_fix_r3.py` 共 17 条（pos 11 / 对照 6），声明名 == `--collect-only` == PASSED 三向相等，跑线 `============================= 17 passed in 5.25s ==============================`。
- 判据自证：`fix_r3_evidence.json` 的 judge_selfprobe = {"must_catch_no_flip_on_C1": true, "must_not_miss_flip_on_C1": true, "must_catch_spurious_flip_on_C5": true}（同一判定函数必须能抓『没翻』、不误抓『翻了』）。
- 声明侧（C5/C8 这两件不靠翻转，靠可机器否证的字面）：{"c5_observed": {"returned": "None", "annotation": "Optional"}, "c8_doc_checks": {"old_rule2_literal_gone": true, "mentions_frozen_doc": true, "mentions_function_scope": true}}

## 四、三套判据体系与红线（同一时刻复算）

- pytest：`1920 passed in 470.29s (0:07:50)`；收集 1920 条，下限 1920（= R3-寻虫 同盘面实测 `1903` + 本环 17 条锁；两个数各自实测得到，不是从公式反推的）。
- 自研套件：`Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`（green=true）。
- e2e golden：`[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`（green=true）。
- git 红线：HEAD 仍 `17d68b4`、暂存 0 档、脏行 166；本仓另有 worktree E:/IDEProjects/AI/Cypy、E:/IDEProjects/AI/_cypy_head_baseline（不是本环建的，未动）。
- 改动半径 7 档，全部归属本单：`cypy_bridge/memory.py`、`cypy_bridge/union.py`、`cypyc/analyzer/build_block_checker.py`、`cypyc/cli.py`、`cypyc/project/module_dependency_graph.py`、`cypyc/transformer/generic_transformer.py`、`tests/test_loop_20260927_fix_r3.py`
- lint：硬违例（E9/W605）0 条、亲笔新文件违例 0 条、E501 逐文件 {"cypyc/analyzer/build_block_checker.py": 3, "cypyc/cli.py": 1} （上限=修前存量 {"cypyc/cli.py": 1, "cypyc/analyzer/build_block_checker.py": 3}，只准减不准增）；存量 W293 {"cypy_bridge/memory.py": 38, "cypy_bridge/union.py": 29, "cypyc/analyzer/build_block_checker.py": 27, "cypyc/cli.py": 53, "cypyc/transformer/generic_transformer.py": 7}。

## 五、什么现象**不算**本环的证明

- 『文件里有 sorted/Optional 字样』不算：BUG-59 用 5 个独立子进程各带一个 PYTHONHASHSEED 复算同一张图（同进程改环境变量测不出来，字符串哈希在解释器启动时就定了）；BUG-58 用 `typing.get_type_hints` 读实际注解，而不是读源码字面。
- 只跑正例不算：17 条锁里 7 条是对照——不传旗标时产物形状不变、DuckDef 的 `type_params` 仍被收、`malloc(0)` 仍抛 MemoryError、改了 docstring 之后构建块检查器仍必须在拦别的规则。
- 「17 条锁今天绿」不足以说明锁承重：另出`.fist-loop-20260927/fix_r3_head_proof.json` 把同一份测试叠到上一提交的产品码树上跑，要求每组都有红、对照不得因行为差异而红。该件自带 caveat：HEAD 不等于本环开工基线（红线禁止 commit，工作树有数百行未提交改动），所以它是次级证据，主证据是本环开工前就落盘的 before 快照翻转对照。
- 『账本里出现了 FIXED 字样』不算：段落账按终态复算（每条目恰 1 段、条目标题行逐字未动、`- 修法：` 那一行原文可回读）。

## 六、本环自身缺陷（判据/工具与操作分栏，逐条留字）

判据与工具类：

1. 把 `git worktree add … HEAD` 当『本环修前基线』用是错的：红线禁止 commit ⇒ 工作树有数百行未提交改动，旧树同时缺本轮与前几轮的东西。本轮第一条红因就是`module 'cypy_bridge.memory' has no attribute '_as_address'`（旧树根本没这符号），与本轮修法无关。改为两级证据：主证据=开工前落盘的 before 快照翻转，次证据=旧码树且必带 caveat。
2. 对照锁的『红』未分级会被自己写的规则反咬：`test_bug58_realloc_zero_size_...` 在旧码树上因陈旧符号而红，而规则说『对照不得红』。补了分栏——`no attribute`/`ImportError` 记 stale 并留原文，行为差异型红仍 refuse；不分级要么误伤要么放水。
3. 新写的判据件首版有语法错与死代码：`fix_r3_evidence.py` 里 `ifbbc.count`（少空格）与两处 `... if False else None` 的半截逻辑。靠 `py_compile` 当场抓出，但更该做的是『写完立刻 compile 再往下排步骤』，而不是写完先写别的。
4. 手写 JSON 出双错才被抓：`fix_r3_plan.json` 里 `"T0e66"`（task_id 打错）与一句未转义引号 （`抛 "this type has no size"`）⇒ `json.load` 直接失败。修正做法：入账编号不手打，从入账件反解；本件 task_id 已与 `hunt_r3_filed.json` 双向对上才留字。
5. 锁的夹具源码写错形状：BUG-55 的对照先写 `duck Comparable[T]:` 放在顶层，parser 报 `Unexpected token DUCK at 1:1`。读 `tests/test_duck.py` 才知 duck 定义必须在 `meta:` 块里——夹具坏了会让『正例通过』变成假绿，所以对照本身也要实测。
6. BUG-59 的第一版断言是照猜的形状写的（以为无环部分输出 `['d','e']`），实跑是 `['z','y','x']` 与 `['y','x','a','b','c']`。改成『先把盘面打印出来，再写期望』，并把期望换成结构式断言（环内名字序在最后 + 纯无环图给确定序），不锁死一次性的字面顺序。
7. 回归锁里自己埋了未定义行为：BUG-58 原先写 `free(0)` 想『验证释放路径走通』，实际是把已释放地址再走一遍 free（double-free 面）。改成不再触碰该地址，并在校验里写明为什么不能这么测。
8. lint 门禁初版口径不可用：把整文件的 E501 当硬门 ⇒ 本轮之前就存在的超长行会让它永远红。换成三条可分栏判据：E9/W605 零条（只可能由本轮引入）、亲笔新文件零违例、E501 逐文件不得高于修前存量计数（只准减）。
9. 报告正文里的『上一环实测』一开始是从公式造的（`1920-17`）。改成直接读 `hunt_r3_baselines.json` 的实测 `passed` 并把两个数都印出来——派生数不是测量数。
10. 基线件自己的两格是恒真形状（run1 已归档 `fix_r3_baselines_run1.json` + `r3fix_logs_run1/`）：lint 格用 `":E9" in ln` 与 `ln.split(':')[4]` 读 flake8 输出，真实格式是 `path:line:col: CODE msg` ⇒ 158 行全部解析失败，被记成『hard_violations=0 / e501_by_file 空』；git 格取 `worktree list` 的 `split()[-1]` 得到 `['[master]', 'HEAD)']` 而不是路径。现在改成正则解析 + 两条自检：解析行数 != 输出行数即 refuse、一行都没解析出来即 refuse。
11. 报告门禁 ④⑤ 初版与 ① 同路径同阈值（`per_bug >= 6`）⇒ 三条恒真重复门禁。『每一行都有 X』这类逐行主张 `report_kit` 解析不了，硬写就等于把主张换成一个数。补 `fix_r3_plan_check.py` 把逐行主张算成 derived 布尔（含与上一环入账件双向对 task_id），门禁改指这些布尔键。
12. `fix_r3_plan_check.py` 初版把台账的 `flipped` 与翻转件的 `ok` 直接相等比较：C5/C8 的 `ok` 语义是『声明侧形状对』，与『翻没翻』不是一回事 ⇒ 会把正确状态判成不一致。改成只与 `after_rc == 1` 对齐，并在两个旗的语义处写明区别。

操作类：

13. 在测量窗口内起 `git worktree add` 的风险：它会拿 `.git/index` 锁，而 `fix_r3_baselines.py` 收尾要跑 `git status --porcelain` 与 `git diff --cached` ⇒ 并发可能把 git 红线格毒成瞬时假值。已把旧码树复算排到全量之后，并把该顺序写进本环流程。
14. `/tmp` 在 Windows 上不是同一棵树：bash 的 `/tmp/r3fix/out/setup.py` 与 Python 解析出的路径不重合，造出『文件找不到』的假失败。改用仓库内 `.fist-loop-20260927/tmp_r3/` 当工作区，实测产物与判据件同盘可追溯。
15. 删临时 worktree 时 shell 的 cwd 还在里面 ⇒ `git worktree remove --force` 报 `Permission denied`、`rm -rf` 报 `Device or resource busy`，登记已摘但目录成孤儿。收尾顺序应为 `remove → prune →（换目录）rmdir`。另：本仓另有一条别人建的 `E:/IDEProjects/AI/_cypy_head_baseline` worktree，列出来看清再动。
16. 时间盒：上一环（R3-寻虫）墙钟 214 分钟，超自定 ≤100 分钟红线，成因是两次上下文压缩后靠回忆重建状态。本环改进为『开工第一件事把 before 快照落盘』，判据件随做随写。
17. 顺序错了一次：基线件跑完 12 分钟才回头发现 lint/git 两格是恒真形状，等于白测一轮再重跑。正确顺序是先让判据件在**合成违例**上过一遍（本次 158 行输出全解析不出、worktree 路径解析成 `HEAD)` 都是三秒钟能看出来的），再排全量。已把 run1 与日志留档，run2 作为唯一权威时刻。
18. 渲染件的退出码被写坏：`return Path(...).write_text(...) or 0` 让 `sys.exit()` 收到字符数 19470，Windows 截成 **98** 且不打印任何原因 ⇒ 看起来像"神秘失败"，实际正文已写盘。改成写完后 `return 0`。这类"退出码不是 0/1 的大数"以后一律按脚本自己的返回值检查，不要拿 `write_text` 的字符数当状态。
19. 账本驱动的写前针头断言抓到我自己复述的 needle：BUG-56 我写『摘掉旗标是缩对外接口面』，台账原文其实是『摘旗是缩对外接口面』；BUG-58 写『仍返回 None』而原文是『释放并返回 None』。⇒ 断言没让坏文本落盘（先拒后写），但暴露了 needle 是我凭记忆重打的。规矩：针头要从被检文本里复制，不重打。
20. 账本驱动的写后自检数错了东西：用 `section.splitlines()[0]` 取标题行，而段落以 `\n` 开头 ⇒ 取到空串，`ln.strip() == ""` 在 1300 行账本里匹到 205 行，六件各报"段落数 205"。段落其实只追加了一次（`grep -c` 实测 6）。改成按条目切段、段内数"同时含 MARK 与本轮标记"的行，并补 `--verify` 模式：文本已落盘后可反复复算终态而不触发幂等守卫（守卫本身也被`--dry-run` 必须被拒这条控制实验证过：rc=1、`MARK` 计数仍 6）。

合计 20 条（判据/工具 12 + 操作 8）。

## 七、交回与转结

- 交回裁决（本环刻意不做，理由在各件段落里）：
  1. BUG-58 的第二半：`realloc(p, 0)` 返回 None 与 `malloc(0)` 抛 MemoryError 不对称。本环只消除『注解/文档与返回值互斥』（改 `Optional[int]` + 文档写清分支），因为对称化必须弱化 `tests/test_bridge_library.py::test_realloc_zero_size`（红线）。若要改成返回 0 或抛错，请连同该测试一起作为口径变更登记。
  2. BUG-60 的第二半：是否把 SYNTAX/04 的『指针声明只能在函数作用域内』落成强制检查（含『结构体字段不得是指针』）。本环只对齐 docstring 口径；补检查会打到 36 处合法写法，属新增门禁，交回裁决。
  3. BUG-57 的另一条修法：Python 内建类型 → ctypes 宽度映射（`int`→`c_int` 还是 `c_long`）。Cython 侧 `int` 是 32 位、CPython 的 `int` 无界，选哪个都是新语义 ⇒ 本环给的是专属错误文案 + 可用示例，映射规则请裁决。
  4. BUG-56 的边角：`run_default`（不可达 else 分支）仍读这四个旗标。要不要删/接，牵动『首参是 .cypy 文件时自动当 transpile』的兼容承诺（docs/USAGE.md:404），本环未动。
  5. BUG-59 的下游：确定的编译序是否要进 golden 基准（`scripts/e2e_golden.sh` 现在 25/25 不含编译序断言）。本环只保证 `get_compilation_order` 可重现，未扩基准。
- 沿用未动的转结：BUG-40/41/43/49/50/52/53 处置、BUG-54 跨进程 `build/` 隔离、`watch` 删除事件是否清 `-o` 旧产物、`close_root_generic.py` 的 L4 产物门前置、`_visit_ExprStmt` 分发语义、analyzer 侧是否恢复 meta 守卫、已发布法则文本与终态实现的字面差。
- 时间盒：自定红线 ≤100 分钟/环节。本环开工 2026-09-28 00:00（本地，动手前先把 before 快照落盘）→ 正文生成于 2026-09-28 00:56，墙钟约 56 分钟（其中 pytest 全量 470.29s (0:07:50) + 自研套件与 e2e 各一轮）。终版报告落盘时刻以页脚为准。

