# -*- coding: utf-8 -*-
"""FIST Omega (Ω) 验证系统。

机制由 sigma-lang 项目演进而来（参考 tnr/src/omega/ 设计，Ω-min 阶段）：
- spec.py  — Ω-spec JSON 解析 + schema 校验 + fingerprint
- gate.py  — Ω-gate 跑批验证（input → expected，含错误路径）
- check.py — 项目结构验证（对照 PROJECT-SPEC/01）

Omega 分两层：
- fist-omega   — FIST 项目自我迭代进化使用（FIST 私有，位于本 omega/ 目录）
- project-omega — 管家发布项目级目标任务后，拳长用 `fist.py project-init`
                 为每个项目部署的 Omega 框架（PROJECT-SPEC 规范 + omega/ 验证系统），
                 提升项目开发准确率。
"""
