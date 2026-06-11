# ai-batch-processor

> **一句话**：500 个项目 AI 分析，成本从 $50 降到 $8.5

AI 批量任务编排器，通过分批处理、本地洞察引擎和断点续传，大幅降低 LLM API 调用成本的同时保持分析质量。

## 快速开始

```bash
# 查看示例
python examples/basic-pipeline.py

# 运行完整管线
python references/full-pipeline.py --input scored.json --output enriched.json
```

## 模块地图

| 目录/文件 | 说明 |
|-----------|------|
| `SKILL.md` | Skill 主文档 |
| `examples/` | 使用示例 |
| `references/` | 参考实现（full-pipeline, generate-insights, prepare-tasks, merge-insights） |
| `tests/` | 测试数据 |
| `CHANGELOG.md` | 变更日志 |

## 核心能力

- 分批处理：按 score 分桶，高分段用 LLM，低分段用本地规则
- 本地洞察引擎：模板化 SWOT、市场机会、竞争壁垒生成
- 断点续传：checkpoint 机制支持中断恢复
- 洞察差异度验证：确保批量生成不重复

## 适用场景

- 大批量项目的 AI 分析
- 需要控制 API 成本的场景
- 需要结构化竞争分析输出的场景

## GitHub

https://github.com/yaohewoma/ai-batch-processor