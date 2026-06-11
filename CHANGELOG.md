# Changelog

All notable changes to the AI Batch Processor skill will be documented in this file.

## [1.1.0] - 2026-06-11

### Added
- `examples/basic-batch.py` — 完整的可运行示例代码（280 行），含 5 个覆盖 S/A/B/C 等级的样本数据，支持 `--mode local/pipeline/all`
- `README.md` — GitHub 风格展示页，含 badges、特性表、目录结构、成本对比、快速开始
- `.gitignore` — Python/IDE/OS 标准忽略规则 + 项目特定临时目录
- `references/__init__.py` — Python 包初始化
- `tests/__init__.py` — 测试包初始化
- `tests/test_insights.py` — 10 项自动化测试套件（数据契约、幂等性、差异度、内容质量、评分一致性、边界条件）
- `references/cost-optimization.md` — 成本优化指南（三种模式细算、决策矩阵、6 种成本优化技巧、3400 项目实战案例、预算监控）
- `references/insight-quality.md` — 洞察质量检查清单（4 个质量维度、检查命令、AI 管线合并检查、常见问题修复、自动化测试积分）

### Changed
- `SKILL.md` — 全面重写（v1.0.0 → v1.1.0）
  - 新增 YAML frontmatter description 扩展（涵盖三种模式）
  - 新增 `0. 流水线位置` 章节，标注上下游依赖
  - 新增 `1.2 决策树`（该用哪种模式？可视化决策）
  - 新增 `2.6 Prompt 模板设计` 独立章节（含多模型适配表、Few-shot 指导）
  - 新增 `2.7 领域信号配置` 章节（domain_signals.json 纳入模块地图）
  - 模块地图重构：🐍 脚本 / 📋 参考 / 📦 示例 三类型分区
  - `3. 标准流程` 从单一流程拆为 3.1/3.2/3.3 三种模式
  - 常见错误从 7 条扩充到 10 条
  - 参数调优从 7 项扩充到 12 项
  - Quick Start 拆为 A/B/C 三种方式 + 示例快速体验
- `tests/test-scored.json` — 格式修复（中文维度 key → 英文标准 key），数据量从旧测试数据升级到 10 条多领域覆盖（S/A/B/C 各等级 + 8 个不同领域）
- `CHANGELOG.md` — 添加本文件

### Fixed
- `tests/test-scored.json` 使用非标准的中文评分维度键（如 "功能完整度" 而非 "functionality"），与 `data-contract.md` 定义不一致
- `references/__pycache__/` 编译缓存残留（已忽略）

### Structural
- 新增 4 个文件，填补与 stealth-scraper/rule-scoring-engine 等兄弟 Skill 的结构缺口
- 测试覆盖：10 个自动化测试，覆盖数据契约、本地引擎、洞察质量、边界条件四大类
- 文档覆盖：从 5 个 reference 文档扩展到 7 个（+cost-optimization +insight-quality）

## [1.0.0] - 2025-06-XX

### Added
- Initial release
- 本地洞察引擎（零 API 调用，34 领域 × 6 维度确定性规则）
- AI 批量管线（数据分批 + Prompt 生成 + JSON 校验 + 结果合并）
- 断路器熔断 + 指数退避重试
- Token 预算控制与统计
- 断点续传（progress.json）
- 多模型适配（GPT-4/Claude/DeepSeek/Gemini/开源模型）
- `references/prompt-templates.md` — Prompt 设计规范
- `references/data-contract.md` — 输入/输出 JSON Schema
- `references/retry-mechanism.md` — 重试机制文档
- `references/token-statistics.md` — Token 统计文档
- `references/troubleshooting.md` — 故障排查指南
- `references/domain_signals.json` — 34 种领域关键词映射
- `references/full-pipeline.py` — 完整管线模板
- `references/prepare-tasks.py` — 任务准备脚本
- `references/merge-insights.py` — 结果合并脚本
- `references/generate-insights.py` — 本地洞察引擎脚本
- `tests/test-scored.json` — 测试数据