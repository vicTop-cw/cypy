
## 2026-09-25T22:06:00Z

T0r61 轮时间线：publish → task_plan_deep(omega_strong_verify=true, split_n=3) 得 29 子任务 → 10 个叶子按「复现定位 / 修复回归」两单元配对 → 每叶子 omega_spec_create+review → claim/execute/submit → run_check（真实 spawn）→ verify；5 个聚合节点与根在收口阶段补交付物后复验，16/16 已完成。

收口阶段发现的 FIST-Mbt 侧事实：
- MCP 工具名是 `resume`，域函数叫 `resume_task`（server.mbt:905 vs core_task.mbt:496）。
- `retry` 落在 执行中，而 `execute` 只接受 拆分中/已领取（core_task.mbt:366-372）→ 被打回的非叶子任务无法重新登记 deliverable，必须走 pause → resume 绕行；这是状态机断链，已作为 FIST-Mbt 待修项记录，本轮未改动其状态机（属该项目所有者的设计决策）。
- run_check 结果落在 `specs` 表（spec_type='check'，content 为 JSON 文本），跨进程重启仍可见；T0r61 树共 38 条 check 记录（36 passed / 2 failed，两条 failed 都发生在 verify 之前并被重跑覆盖），根节点那条含 e2e_golden 全量 stdout。Omega 侧 15 条 spec 与 15 条 result 全部 approved（10 叶子 + 5 聚合；根任务未带 [omega:required]，不参与强验证）。
- `audit_log` 工具返回空：`src/ops/audit.mbt` 的审计条目只活在进程内存，没有落库分支，跨调用即失——账本取证只能用 `call_log` 表（本轮 cron-cypy 命名空间 337 条）。
- call_log 时钟修好（Int64）后：1030 条记录，ts 区间 2026-09-25T07:01:17Z–11:20:35Z（真实 UTC，此前是 1969-12-25T-22:-13:-40Z 垃圾值）。

Cypy 侧本轮踩到并修掉的真实回归：e2e_golden 一度从 PASS=22 掉到 PASS=9，而 pytest 全绿。原因是 hook 在 chdir 之后才 abspath 相对产物目录（copy2 WinError 3 → 回退路径落在临时目录），finally 又无条件 rmtree 临时目录，删掉了已回报的 .pyd；`cli.run_run` 只看 `success` 不看 `errors`，把「编译产物加载失败」打印成执行成功，于是腐烂藏在绿灯后面。三处已修并由 tests/test_hook.py、tests/test_cli.py 的精确回归用例钉住。
