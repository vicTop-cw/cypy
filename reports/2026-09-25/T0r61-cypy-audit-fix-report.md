# 2026-09-25 · Cypy 审查修复轮（FIST T0r61）汇报

> 驱动方式：FIST-Mbt（兄弟项目）任务编排 + Omega 强验证 + call_log 全量调用审计，
> 自驱式递归拆解；执行体为 10 个子代理单元（5 簇 × 复现/修复），指挥官只做分流与终审。
> 判据源：`E:\IDEProjects\AI\DownLoads\open-code-review\Tnr-FIST-Mbt-Cypy代码审查报告.md`（Cypy 293 条 / critical 6 / high 73）。

## 一、结果摘要

- 审查报告的 29 条 Cypy 关键项经**第二遍亲审**核对：**26 项仍存在**（critical 5 / high 21），2 项此前已修，1 项 PARTIAL。
- 本轮 **26 项全部修复**，每项配一条**精确**永久回归用例（合计净增 213 条测试）；唯一未处理项为
  `cypyc/incremental/file_monitor.py` 的 stop() 竞态与 `on_moved`/`_watched_files` 残留（见第五节）。
- 三条非 LLM 外部锚点全部达标：`python -m pytest tests test_suite -q` = 1681 passed / 0 failed、
  `bash scripts/e2e_golden.sh` = PASS=22 FAIL=0、`python scripts/run_tests.py` = 47 passed / 0 failed。
- 31 个自门控复现脚本留在 `Find_BUG/audit_2026q3/`（exit 1 = 复现，exit 0 = 已修，5 簇 4/6/9/8/4），
  `repro_gate.py` 提供 reproduce / fixed / scripts 三态判据，已登记为 FIST 外部检查命令。
- FIST 账本已收口：`T0r61` 全树 16/16 任务 `已完成`，38 条服务端 run_check 记录（36 passed / 2 failed）、
  30 条 Omega 语料与成果复验（15 spec + 15 result，均 approved）、337 次调用全在 `call_log` 表可回放。
- 修复过程中额外发现并处理了**审查报告没有的 6 类真缺陷**（见第六节），其中两项是本轮唯一的一次
  「修到一半把判据打烂」的事故源。

## 二、任务分配记录

| 节点 | 内容 | 执行体 | 状态 |
|---|---|---|---|
| `T0r61` | 本轮根任务（[gate:required]） | human_steward 发布 | 已完成 |
| `T0r61.1` | 增量编译链与依赖图 | leader 拆解 | 已完成 |
| `T0r61.1.1/.2` | dependency_graph 词表恒空 / ast_differ 摘要与状态 | 子代理 ×2 | 已完成 |
| `T0r61.2` | 前端解析、预处理与类型判等 | leader 拆解 | 已完成 |
| `T0r61.2.1/.2` | include 逃逸、宏递归/转义/盲替换、Tab 缩进、`Type.__eq__` | 子代理 ×2 | 已完成 |
| `T0r61.3` | 运行时桥接语义 | leader 拆解 | 已完成 |
| `T0r61.3.1/.2` | pointer 所有权、defer/nogil 单例、pointer_checker、comptime 短路、meta、memory、union、types | 子代理 ×2 | 已完成 |
| `T0r61.4` | 代码生成与项目编译产物 | leader 拆解 | 已完成 |
| `T0r61.4.1/.2` | try/finally 变量名、PyErr_Clear 吞异常、NULL INCREF、`.pyd` 平台标签、project_compiler 四项 | 子代理 ×2 | 已完成 |
| `T0r61.5` | 测试与自检基建 | leader 拆解 | 已完成 |
| `T0r61.5.1/.2` | `tests[-1]` 错挂、`self.skip` 遮蔽、弱断言与变异 | 子代理 ×2 | 已完成 |

每个叶子按 `建语料 → 验证者审语料 → claim → execute → 成果复验 → submit → run_check → verify` 走完，
`[gate:required]` 节点在缺少**新鲜且通过**的外部检查时被服务端硬拒（实测两类拒因：
`T0r61.3.1` 的首个 run_check 判 failed；一次 verify 因驱动脚本把旧 `now` 烘进复用的 args，
判据时间戳反而早于任务最后更新而被门禁挡回，改判据后重跑通过）。

收口阶段（聚合节点与根）踩到 FIST-Mbt 的状态机断链：`task_plan_deep` 把聚合节点级联成
`待验收` 却不带 deliverable，于是 `omega_result_verify` 报「尚无交付物」、`verify` 被 Omega 门禁挡回；
按 `reject → retry` 回弹后 `retry` 落在 `执行中`，而唯一能登记交付物的 `execute` 只接受
`拆分中/已领取`（`src/core/core_task.mbt:366-372`）。合法绕行是 `pause → resume`（工具名 `resume`，
不是域函数名 `resume_task`）回到 `已领取` 再补交付物，五簇与根均以此走完。

## 三、资源消耗

- 子代理：10 个单元（5 复现 + 5 修复），其中 2 个修复单元在 150 轮上限处被截断，
  指挥官以 gate + 源码逐点复核确认交付真实落地后补完账本。
- 主进程命令：全量 pytest 5 次（各约 11 分钟）、e2e golden 6 次、run_tests 3 次、
  复现闸门 31×N 次；FIST MCP 调用 `call_log` 表内 `ns='cron-cypy'` 共 337 条（含收口三轮），
  `executions` 26 条、`specs` 68 条（38 check + 15 spec + 15 result），全部可回放。
- 磁盘：新增测试文件 4 个、复现脚本 31 个、驱动脚本 `scripts/fist.py`、元提示词
  `Gen_Prompts/20260925.15.00.00.md`；FIST 收敛记忆落在 `memory/target.md`、`memory/thinking.md`；
  `output/` 与 `build/` 为可再生构建产物，未入库。

## 四、判据与证据

- 外部判据（FIST `run_check` 真实 spawn，门禁状态由服务端从 exit_code 推导，不接受调用方自报）：
  1. `python -m pytest tests test_suite -q -o addopts=""` → **1681 passed / 0 failed**（基线 1466）
  2. `bash scripts/e2e_golden.sh` → **PASS=22 FAIL=0 UNREG/RUNFAIL=0 WARN=1**（与基线同口径）
  3. `python scripts/run_tests.py` → **Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0**
  4. `python Find_BUG/audit_2026q3/repro_gate.py <簇前缀> fixed` → 5 簇 31 脚本全部 exit 0
- 上述四条的服务端执行原文（stdout/stderr/exit）都落在这颗任务的 check 记录里，可逐条取证：
  `python scripts/fist.py get '{"task_id":"T0r61"}'` 及 `specs` 表 `spec_type='check'`（38 条）。
- 逐条改点的 file:line 级说明与复现证据，存于 FIST `cron-cypy` 命名空间各叶子的 deliverable，
  以及 `Find_BUG/audit_2026q3/` 脚本输出。
- 账本勘误：五簇聚合节点与根的 deliverable 文本里写的是「29 个自门控复现脚本」，实测为 **31**
  （4+6+9+8+4）。任务已 `已完成`，FIST 无合法迁移可改写已完成记录的 deliverable，故在此处留痕，
  不回改账本。

## 五、遗留风险

1. **`cypyc/incremental/file_monitor.py` 未在本轮范围内**：stop() 与回调调度的竞态、
   原子保存产生的 `on_moved` 事件未转发、`_watched_files` 只增不减。增量链其它三项已修，这一项仍开放。
2. `cypyc/analyzer/type_checker.py` 的 `object/Any` 无条件放行仍是 `Optional[int]`→`Optional[str]`
   漏报的元凶；本轮只把 `Type.__eq__` 修正确（并已钉桩证明它不改变任何端到端诊断）。
3. 依赖边召回仍有结构性缺口：`GenericType.name`、`Attribute.attr`、`Import` 模块名在 AST 里是裸 `str`，
   故 `def f(b: Box<Point>)` 只采到 `Point` 的边。修它需扩展「kind → 字符串名字属性」词表，风险半径大于本轮授权。
4. 宏/预处理器仍保留两处静默降级：`_reparse_code` 解析失败退回原块（改硬报错会影响多行宏体），
   `cython_generator.py` 的 `{param}` 模板替换仍是盲文本替换（同族缺陷的另一份实现）。
5. `examples/struct.cypy`、`examples/minimal_test.cypy`、`examples/generic.cypy` 在会话开始前就已是
   脏且部分二进制损坏的状态；`exception` 语法可词法不可语法。这些是既有债，未由本轮引入或修复。
6. 构建产物目录被本轮的 e2e 复跑大量写入（`output/`、`build/`、`cypy_hook/__pycache__/` 等），
   均为 gitignore 范围；`output/hello.*` 三个文件是我为定位回归手工删除的，可再生。
7. **`examples/*.out` 这 23 个 golden 基准从未入库**（`git ls-files` 无、`.gitignore` 也未覆盖，
   文件 mtime 早至 2026-09-18）。也就是说 `scripts/e2e_golden.sh` 依赖的外部锚点只活在本地工作区：
   新克隆或 CI 干净检出上它会把所有示例判成 `UNREG`，锚点静默退化成空转。本轮未擅自 `git add`，
   只在此留痕。

## 六、超额内容（审查报告之外、本轮顺带查明）

1. **`cypyc run` 吞掉运行错误仍回报成功**：`cli.run_run` 只看 `result.success`，而 `hook.run()` 把
   `run_module` 的异常塞进 `result.errors` 后返回 `(success=True, None)`——这正是 13 个 golden 在
   一片 pytest 绿灯里烂掉的直接原因。已改为 `success and not errors` 才报成功。
2. **`cypy_hook` 产物路径两处真实缺陷**：`out_dir_abs` 在 `chdir` 之后才 `abspath`（相对输出目录被解析到
   不存在的 `<tmp>/output`），以及 `finally` 无条件删除临时目录、却可能同时删除正在回报的产物
   （导入即 `DLL load failed`）。两处均为回归，已修。
3. `cypy_bridge/__init__.py` 以 `union` **函数**遮蔽同名子模块；`Pointer.__eq__` 无 `__hash__`；
   `memory` 的 `malloc` 注解 `-> c_void_p` 实返 `int` 令下游 `isinstance` 分支永久失效。
4. `dependency_graph.py` 的 `-={name} - set(generic_params)` 优先级写法（StructDef/TypeAlias/TraitDef 三处），
   边一旦真实采集就会生成 phantom 泛型依赖。
5. `ast_differ._type_to_str` 对 AST 节点走 `str()`，把 `__repr__` 的行号带进摘要——真实语料 31/76 文件的
   纯格式化会被误判成语义变更（第二个独立的 line/col 泄漏点）。
6. `test_suite/fixtures/parser.py` 调用不存在的 `Preprocessor.preprocess`，使预处理器长期零覆盖；
   `scripts/sync_demo.py` 在 GBK 控制台因 `✓` 直接崩溃。

## 七、后续建议

1. 把 `python Find_BUG/audit_2026q3/repro_gate.py <prefix> fixed` 与 `bash scripts/e2e_golden.sh`
   写进 CI（当前 CI 只跑 `python -m pytest tests/`，而 `test_suite/` 与 e2e 判据都不在覆盖内——
   这正是自检基建能自伤三个月的原因）。进 CI 前先把 `examples/*.out` 这 23 个 golden 入库
   （见第五节第 7 条），否则干净检出上 e2e 锚点是空转的。
2. 下一轮优先做第五节 1、2 两条（文件监视器 + 类型检查放行），它们与本轮成果同源但超出授权半径。
3. 兄弟项目侧（本轮实测，均属 FIST-Mbt，未擅自改动其设计）：
   - `run_check` 仍是任意命令 `spawn`（无白名单、无鉴权），本轮把它当外部判据用是安全的
     （命令均为本仓库测试），但它对任意 MCP 客户端开放面未变。
   - 状态机断链：`retry` 落在 `执行中`，而 `execute` 只接受 `拆分中/已领取`
     （`src/core/core_task.mbt:366-372`），被打回的任务因此**无法重新登记 deliverable**；
     又因 `task_plan_deep` 把聚合节点级联成无 deliverable 的 `待验收`，Omega 成果复验门禁直接锁死。
     现只能靠 `pause → resume` 绕行，建议给 `execute` 放开 `执行中/待验收` 或补一个 amend 迁移。
   - `audit_log` 对本轮无取证价值：`src/ops/audit.mbt` 头部即声明「AuditLog 为进程内追加式日志，
     不落库」，所以每次唤醒新起 server 进程后查询恒返回空数组（实测如此）。跨进程账本只能靠
     `call_log` 表，建议把审计条目同样落库。
   - 工具名与域函数名不一致：MCP 侧是 `resume`，域侧是 `resume_task`（`server.mbt:905` vs
     `core_task.mbt:496`），按域名调用会得到 `Tool not found`，本轮踩过一次。

## 八、来源

- 判据源：`Tnr-FIST-Mbt-Cypy代码审查报告.md`（2026-09-24，ocr 全扫 + 亲审补录）
- 任务与证据：FIST-Mbt `cron-cypy` 命名空间 `T0r61` 树（specs / results / checks / call_log 表）
- 复现与闸门：`Find_BUG/audit_2026q3/`（31 脚本 + `repro_gate.py` + scratch 证据）
- 驱动：`scripts/fist.py`（stdio JSON-RPC，自动补装 ESM require shim，注入 `created_by=agent`）
- 元提示词：`Gen_Prompts/20260925.15.00.00.md`
