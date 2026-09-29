## BUG-1 [2026-09-26T05:30:06Z] [low] OPEN
- summary: [probe] report_bug 单发诊断（可删）
- detail: 诊断用：确认 report_bug 在 cwd=Cypy 根时是否响应。

## BUG-2 [2026-09-26T05:30:21Z] [low] OPEN
- summary: [probe] B publish_task=True 最小载荷
- detail: 诊断
- task_id: T0r2

## BUG-3 [2026-09-26T05:30:21Z] [low] OPEN
- summary: [probe] C publish_task=True + reported_by
- detail: 诊断
- reported_by: probe
- task_id: T0r3

## BUG-4 [2026-09-26T05:30:58Z] [high] OPEN
- summary: [cache] cypy_bridge/compiler.py:3656 clear_cache 把 .pyd 删除失败当成功：裸 except 吞掉后仍从 manifest 删条目
- detail: 现象：`clear_cache(module_name)` 在 `try: os.remove(pyd_path) except: pass`（:3656-3659）之后无条件 `del manifest[cache_key]` + `_save_manifest(manifest)`；全量分支（:3668-3671）同样吞掉删除失败并无条件 `_save_manifest({})`。
后果：Windows 上被 import 的扩展模块文件锁是常态（同文件 :3760 附近就有为绕开 file lock 而换临时目录的逻辑），删除失败时磁盘上的 .pyd 仍在，但 manifest 已声称没有 → 上层按 manifest 判断「已清理」，可继续命中陈旧二进制；表现为「清了缓存但行为没变」，且全程零诊断。
复现（确定性、不编译）：构造 BridgeCacheManager，写一条 manifest 指向临时 .pyd，monkeypatch `os.remove` 抛 OSError，再调 `clear_cache(name)`；断言「删除失败 ⇒ 条目仍在 manifest 或返回值/日志能观察到失败」。当前实现两条都不满足。
判据实测：`grep -n 'except:' cypy_bridge/compiler.py` → 3658、3670 两处（全仓三包裸 except 共 2 处、`except … : pass` 共 20 处，见 `.fist-polish-20260926/markers_baseline.json`）。
建议：删除失败就不动 manifest 条目（保持「未清理」的事实），并把失败收集成可判定结果（例如返回 (cleared, failed) 或记 warning），不要静默写空 manifest。
- reported_by: cypy-polisher
- task_id: T0r4

## BUG-5 [2026-09-26T05:30:58Z] [high] OPEN
- summary: [cache] cypy_bridge/compiler.py:3656 clear_cache 把 .pyd 删除失败当成功：裸 except 吞掉后仍从 manifest 删条目
- detail: 短明细
- reported_by: cypy-polisher
- task_id: T0r5

