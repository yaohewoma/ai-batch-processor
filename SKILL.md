---
name: "ai-batch-processor"
version: "1.1.0"
description: "Orchestrates large-scale AI batch pipelines with three flexible modes: zero-cost local insight engine (34 domains × 6 dimensions, deterministic rules), AI batch pipeline (split data, generate structured prompts, validate JSON, merge results), and hybrid mode. Invoke when user needs to process hundreds to thousands of items through LLMs or local rule engines."
---

# AI Batch Processor — AI 批量任务编排

> **执行前必做：** 生成任务管线前，必须先阅读 [`references/full-pipeline.py`](references/full-pipeline.py) 获取完整管线模板；本地洞察模式先读 [`references/generate-insights.py`](references/generate-insights.py)。
> **核心原则：** 每批 30~50 条，Prompt 中严格限定 JSON Schema（字段名 + 类型 + 字数/数量限制），输出端校验后再合并。所有字段必须标注字数范围，否则 AI 输出不可控。

## 0. 流水线位置

```
stealth-scraper → rule-scoring-engine → ai-batch-processor → data-audit-toolkit
                                            ↑ 本 Skill            → [下游: 质量审计]
```

- **上游依赖**：[rule-scoring-engine](../rule-scoring-engine/SKILL.md) — 提供已评分数据（含 scores/avgScore/qualityGrade/strengths/weaknesses/oneLiner）
- **下游 Skill**：[data-audit-toolkit](../data-audit-toolkit/SKILL.md) — 审计洞察生成质量、检查洞察差异度
- **输入格式**：`{ projects: [{ ..., scores, avgScore, qualityGrade, strengths, weaknesses }] }`（详见 [数据契约](../SKILLS-INDEX.md#skill-2--skill-3-交接格式)）
- **产出格式**：在原数据上追加 `aiInsight: { summary, competitiveEdge, risks, suggestions, marketOpportunity }`
- **总索引**：[SKILLS-INDEX.md](../SKILLS-INDEX.md)

## 1. 何时使用本 Skill

### 1.1 触发条件

以下场景应使用本 skill：
- 有数百到数千条数据需要 AI 逐条分析生成洞察（SWOT、改进建议、市场机会等）
- 需要 AI 输出严格结构化的 JSON（有明确的字段和类型要求）
- 需要分批处理以控制单次 token 消耗和上下文窗口
- 需要自动校验 AI 输出的格式正确性和数量完整性
- 预算有限，需要零成本或低成本方案替代全量 AI 调用
- 需要可复现的洞察生成（同数据跑两次结果一致）
- 用户提到"批量AI分析"、"分批处理"、"AI打分"、"批量生成洞察"、"降低成本" 等关键词

以下场景不应使用本 skill：
- 只有几十条数据 —— 直接一次性给 AI 即可
- 不需要结构化输出 —— 不需要 JSON Schema 校验
- 用户有自己的 AI API 调用方式 —— 本 skill 偏任务编排，不负责 API 调用
- 数据没有任何结构化评分/标签 —— 本地引擎无法驱动（可用流水线模式）

### 1.2 决策树：该用哪种模式？

```
                        有评分数据吗？
                       /            \
                     是              否
                     |               |
              预算充足吗？      →  流水线模式
             /          \        (prepare-tasks + AI + merge-insights)
           是            否
           |             |
    需要深度分析吗？    本地洞察引擎
    /          \      (generate-insights.py, $0)
  是            否
  |             |
流水线模式   本地洞察引擎

最佳实践: 本地引擎全量($0) + 流水线 Top N 深度分析($2.5) = 混合模式
```

### 1.3 前置约束

1. 先读 [`references/full-pipeline.py`](references/full-pipeline.py) 和 [`references/generate-insights.py`](references/generate-insights.py)，理解两种核心模式
2. 向用户确认：数据总量、每批条数（建议 30~50）、输出字段 Schema
3. Prompt 设计参考 [`references/prompt-templates.md`](references/prompt-templates.md)
4. **每个输出字段必须标注字数范围**，否则 AI 输出不可控
5. **输出格式必须是 JSON 数组**，方便校验和合并
6. 数据精简：只传 AI 分析需要的字段，正文截断到 2000 字
7. 必须给 AI 传已有的评分和标签（avgScore/strengths/weaknesses）作为参考
8. 洞察完成后提醒用户用 `data-audit-toolkit` skill 做质量审计

## 2. 模块与命令导航

先判断用户目标属于哪个大模块，再进入对应子模块阅读 reference。

### 2.1 模块地图

| 类型 | 大模块 | 解决什么问题 | 参考文件 |
|------|------|------------|---------|
| 🐍 脚本 | 本地洞察引擎 | 确定性规则生成 AI 洞察，零 API 调用，差异度 > 90% | [`references/generate-insights.py`](references/generate-insights.py) |
| 🐍 脚本 | 完整管线模板 | 可运行的端到端脚本 (generate + merge)，供外部 AI 消费 | [`references/full-pipeline.py`](references/full-pipeline.py) |
| 🐍 脚本 | 任务准备脚本 | 数据分批 + Prompt 生成 + 正文嵌入 + 质量过滤 | [`references/prepare-tasks.py`](references/prepare-tasks.py) |
| 🐍 脚本 | 结果合并脚本 | JSON 校验 + Markdown 包裹处理 + 洞察合并 + 错误统计 | [`references/merge-insights.py`](references/merge-insights.py) |
| 📋 参考 | 数据契约 | 输入/输出 JSON Schema 形式化定义，上下游交接规范 | [`references/data-contract.md`](references/data-contract.md) |
| 📋 参考 | Prompt 模板 | 角色设定 + JSON Schema + 分析维度 + 字数限制 + Few-shot | [`references/prompt-templates.md`](references/prompt-templates.md) |
| 📋 参考 | 领域信号配置 | 34 种领域关键词映射，驱动本地洞察引擎的领域检测 | [`references/domain_signals.json`](references/domain_signals.json) |
| 📋 参考 | 重试机制 | 指数退避、断路器模式、错误分类、重试装饰器 | [`references/retry-mechanism.md`](references/retry-mechanism.md) |
| 📋 参考 | Token 统计 | token 使用量追踪、多模型成本计算、预算控制 | [`references/token-statistics.md`](references/token-statistics.md) |
| 📋 参考 | 成本优化 | 三种模式成本细算（含公式）、决策矩阵、3400 项目实战 | [`references/cost-optimization.md`](references/cost-optimization.md) |
| 📋 参考 | 洞察质量 | 4 维度质量度量、检查命令、AI 管线合并验证、常见修复 | [`references/insight-quality.md`](references/insight-quality.md) |
| 📋 参考 | 故障排查 | 合并失败、洞察质量、性能问题的解决方案 | [`references/troubleshooting.md`](references/troubleshooting.md) |
| 📦 示例 | 基础示例 | 可独立运行的演示脚本，含 5 个样本数据（S/A/B/C 全覆盖） | [`examples/basic-batch.py`](examples/basic-batch.py) |
| 📦 测试 | 自动测试 | 10 项测试套件（契约/幂等/差异度/质量/一致性/边界） | [`tests/test_insights.py`](tests/test_insights.py) |

- `references/` - 参考文档与运行脚本
- `examples/` - 使用示例，演示完整数据管线
- `tests/` - 测试固件（JSON格式）

### 2.2 本地洞察引擎（零 API 调用）

**必读 reference**：[`references/generate-insights.py`](references/generate-insights.py)

独立可运行的脚本，用确定性规则替代外部 LLM API，生成高差异化洞察。**推荐作为默认方案。**

| 模式 | 命令 | 说明 |
|------|------|------|
| 生成洞察 | `python generate-insights.py --input scored.json --output enriched.json` | 为所有项目生成洞察 |
| 预览 | `python generate-insights.py --input scored.json --dry-run` | 预览前 10 条，确认质量 |
| 验证 | `python generate-insights.py --input enriched.json --check` | 验证已有洞察的差异度 |

**核心设计**：
- 基于 MD5(topicId + 字段名) 种子保证幂等性 —— 同一项目每次运行结果完全一致
- 34 种领域 × 6 个维度 × 多套模板 → 差异度 > 90%
- 分数驱动 + 领域感知 + 投票数加权 → 生成内容与实际数据高度相关
- 处理 3000+ 条仅需数秒，纯 Python 标准库

**路由提醒**：这是推荐的首选方案。只有在需要真正的 AI 语义理解（如分析项目文案的潜台词）时才切换到流水线模式。

### 2.3 完整管线模板

**必读 reference**：[`references/full-pipeline.py`](references/full-pipeline.py)

完整的可运行 Python 脚本，包含两种模式：

| 模式 | 命令 | 说明 |
|------|------|------|
| 生成任务 | `python full-pipeline.py --mode generate --input scored.json --output tasks/` | 将数据分批，生成 Prompt 任务文件 |
| 合并结果 | `python full-pipeline.py --mode merge --input scored.json --results ai_results/ --output enriched.json` | 读取 AI 输出，校验格式，合并回主数据 |

**路由提醒**：生成模式不调用任何 AI API，只产出任务文件。用户需自行将任务文件提交给 ChatGPT/Claude 等外部 AI，然后将返回的 JSON 文件放入 `ai_results/` 目录进行合并。

### 2.4 任务准备脚本

**必读 reference**：[`references/prepare-tasks.py`](references/prepare-tasks.py)

独立可运行的脚本，支持正文嵌入、截断、Top N 筛选、质量过滤。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | 必填 | 输入 JSON 文件 |
| `--output` | 必填 | 任务文件输出目录 |
| `--batch-size` | 30 | 每批条数 |
| `--top` | 0 (全量) | 按投票数取 Top N |
| `--filter` | 无 | 过滤条件，如 `qualityGrade=S` 或 `classification.productType=工具` |
| `--text-dir` | 无 | 正文目录，提供则嵌入正文 |

**路由提醒**：自动过滤官方项目，按投票数降序排序。输出 `manifest.json` 记录所有批次元数据。

### 2.5 结果合并脚本

**必读 reference**：[`references/merge-insights.py`](references/merge-insights.py)

独立可运行的脚本，校验 AI 返回的 JSON 格式、合并洞察到主数据。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | 必填 | 主数据 JSON 文件 |
| `--results` | 必填 | AI 结果文件目录 |
| `--output` | `merged.json` | 合并输出文件 |
| `--validate-only` | false | 仅校验不合并 |
| `--verbose` | false | 详细输出未匹配 master 和 orphan insights 的 ID |

**路由提醒**：自动处理 markdown 包裹的 JSON (` ```json ... ``` `)，输出详细错误统计（成功/失败/未匹配/孤儿洞察数量）。

### 2.6 Prompt 模板设计

**必读 reference**：[`references/prompt-templates.md`](references/prompt-templates.md)

设计 AI Prompt 时必须遵守的规范。每个 Prompt 需包含以下要素：

| 要素 | 要求 | 示例 |
|------|------|------|
| 角色设定 | 明确 AI 身份 | "资深产品分析师" |
| JSON Schema | 字段名、类型、字数范围 | `summary: string (30字以内)` |
| 分析维度 | 3~5 个引导方向 | 功能性、创新性、用户体验 |
| 数量提示 | 告知这批有多少条 | "共 {count} 个项目" |
| 输出格式 | 严格 JSON 数组 | `[{...}, {...}]` |
| Few-shot 示例 | 1-2 个 JSON 输出示例 | 显著提升小模型格式稳定性 |

**多模型适配**：

| 模型 | 推荐批大小 | 注意事项 |
|------|-----------|----------|
| GPT-4o / GPT-4 | 50 | JSON 稳定性高，偶尔需要处理 markdown 包裹 |
| Claude 3.5 Sonnet | 40 | 添加 `{` 开头提示，JSON Schema 理解较好 |
| DeepSeek V3 | 30 | 中文理解优秀，JSON 严格性略低于 GPT-4 |
| Gemini 1.5 Pro | 30 | 建议增加 Few-shot 示例 |
| 开源模型 (Qwen/Llama) | 10-15 | 必须添加 Few-shot，增强后处理容错 |

**路由提醒**：必须给 AI 传已有的评分和标签（avgScore/strengths/weaknesses）作为参考，避免 AI 凭空分析与已有数据矛盾。温度参数建议设为 0.3-0.5。

### 2.7 领域信号配置

**必读 reference**：[`references/domain_signals.json`](references/domain_signals.json)

JSON 配置文件，定义 34 种 AI 应用领域的检测关键词。供本地洞察引擎自动识别项目所属领域，驱动领域专属的洞察模板。

| 领域类别 | 示例领域 | 关键词数 |
|---------|---------|---------|
| AI 对话/创作 | 聊天、写作、图像、音乐、视频 | 5~8 个/领域 |
| AI 行业应用 | 教育、医疗、办公、电商、金融 | 5~8 个/领域 |
| AI 技术工具 | 编程、数据分析、翻译 | 5~8 个/领域 |
| AI 特殊场景 | 游戏、社交、公益、求职 | 5~8 个/领域 |

**路由提醒**：领域信号文件可热加载，用户可自定义添加新领域和关键词，无需修改 Python 代码。

## 3. 生成洞察的标准流程

### 3.1 本地洞察引擎流程（推荐首选）

1. **确认数据**：输入数据已通过上游评分，包含 scores/avgScore/qualityGrade/strengths/weaknesses
2. **预览质量**：`python generate-insights.py --input scored.json --dry-run`
3. **全量生成**：`python generate-insights.py --input scored.json --output enriched.json`
4. **验证差异度**：`python generate-insights.py --input enriched.json --check`
5. **审计检查**：提醒用户用 `data-audit-toolkit` skill 检查洞察质量

### 3.2 AI 管线流程（需要深度分析时）

1. **确认规模**：多少条数据？每批多少条？（参照 2.6 模型适配表）
2. **定义输出 Schema**：列出每个字段名、类型、字数范围，参考 [`references/prompt-templates.md`](references/prompt-templates.md)
3. **设计 Prompt**：基于 Prompt 模板定制，确定角色、维度、Few-shot 示例
4. **分批准备**：`python prepare-tasks.py --input scored.json --output tasks/ --batch-size 30`
5. **提交 AI**：将 `tasks/` 目录下的任务文件逐个提交给外部 AI
6. **合并结果**：`python merge-insights.py --input scored.json --results ai_results/ --output enriched.json`
7. **审计检查**：提醒用户用 `data-audit-toolkit` skill 检查洞察质量

### 3.3 混合模式流程（最佳实践）

1. 本地引擎全量生成基础洞察（$0）
2. 按 qualityGrade=S 或 avgScore≥7.0 筛选 Top 项目
3. 对 Top 50~100 项目用 AI 管线做深度分析（$2.5~5）
4. 合并结果，既有广度又有深度

## 4. 常见错误

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 不限制字数 | AI 输出 500 字 summary，token 严重浪费 | 每个字段标注 `(30字以内)` 或 `(50-80字)` |
| 不限制建议数量 | AI 输出 1 个或 10 个建议，格式不可控 | 标注 `(列表，2-3个)` |
| 不传参考数据 | AI 凭空分析，给低分项目写"竞争优势明显" | 传 `avgScore`、`strengths`、`weaknesses` |
| 不截断正文 | 3000-5000 字长文消耗大量 token | 正文截断到 2000 字 |
| 不分批 | 500 条一次给 AI，只认真分析前 20 条 | 每批 30~50 条（参照模型适配表） |
| 不校验 JSON | AI 输出格式错误（缺逗号、markdown 包裹），合并失败 | 用 `merge-insights.py` 自动校验和修复 |
| 角色设定太泛 | "AI 助手" → 输出偏通用 | 用"资深产品分析师"等具体角色 |
| 不添加 Few-shot | 小模型/开源模型输出格式不统一 | 添加 1-2 个 JSON 输出示例 |
| 忘记审计 | 洞察质量无保障 | 完成后用 `data-audit-toolkit` 检查 |
| 全量 AI 调用 | 500 项目 $50 成本 | 先用本地引擎（$0），只对 Top 项目用 AI |

## 5. 参数调优速查

| 参数 | 默认值 | 说明 | 何时调参 |
|------|--------|------|---------|
| `--batch-size` | 30 | 每批处理条数 | GPT-4 可到 50，Claude Haiku 降到 15 |
| 正文截断长度 | 2000 字 | 传给 AI 的正文上限 | 正文普遍短时减小，需更多上下文时增大至 3000 |
| 洞察字段数 | 5 | summary/edge/risks/suggestions/opportunity | 需更详细时增加字段 |
| summary 字数 | ≤30 字 | 一句话总结字数上限 | 需要更详细时放宽到 50 字 |
| competitiveEdge 字数 | 50-80 字 | 竞争优势分析字数范围 | 需要更深入时放宽到 80-120 字 |
| risks 数量 | 2-3 个 | 风险点数量 | 需要更多时增加到 4-5 |
| suggestions 数量 | 2-3 个 | 建议数量 | 需要更多时增加到 4-5 |
| `--top` | 0 (全量) | 按投票数筛选 Top N | 数据量过大（>5000）时先用 Top N 过滤 |
| `--filter` | 无 | 质量等级/类型过滤 | 只关注高质量时设 `qualityGrade=S` |
| Temperature | 0.3-0.5 | AI 输出温度 | 需要更多创意性时增大到 0.7 |
| 成本预算 | 无 | token 预算上限 | 设置 `budget_limit` 和 `alert_threshold=0.8` |
| 重试次数 | 3 | API 调用最大重试次数 | 网络不稳定时增大到 5 |

## 6. Quick Start

### 方式 A：本地洞察引擎（推荐，$0 成本）

```bash
# 1. 零依赖，Python 3.8+ 即可运行
# 2. 准备已评分数据（上游 rule-scoring-engine 产出）
#    输入格式：{ "projects": [{ "topicId", "title", ..., "scores": {...}, "avgScore": 6.8, "qualityGrade": "A" }] }

# 3. 预览前 10 条，确认质量
python references/generate-insights.py --input scored.json --dry-run

# 4. 全量生成洞察
python references/generate-insights.py --input scored.json --output enriched.json

# 5. 验证洞察差异度
python references/generate-insights.py --input enriched.json --check
# 输出：Unique summaries: 492 (98.4%)，Unique edges: 487 (97.4%)
```

### 方式 B：AI 批量管线（需要深度分析时）

```bash
# 1. 生成分批任务文件
python references/prepare-tasks.py --input scored.json --output tasks/ --batch-size 30

# 2. 将 tasks/ 下的文件逐个提交给 ChatGPT/Claude
#    （参照 references/prompt-templates.md 理解 Prompt 结构）

# 3. 将 AI 返回的 JSON 文件放入 ai_results/ 目录

# 4. 校验 + 合并
python references/merge-insights.py --input scored.json --results ai_results/ --output enriched.json

# 5. 管线一键模式（等价于步骤 1+4）
python references/full-pipeline.py --mode generate --input scored.json --output tasks/
# ... 提交给 AI ...
python references/full-pipeline.py --mode merge --input scored.json --results ai_results/ --output enriched.json
```

### 方式 C：混合模式（最佳实践）

```bash
# 1. 本地引擎全量生成（$0）
python references/generate-insights.py --input scored.json --output enriched.json

# 2. 筛选 Top 高质量项目
python references/prepare-tasks.py --input scored.json --output tasks/ --filter qualityGrade=S --top 50

# 3. 对 Top 50 用 AI 深度分析（~$2.5）
# ... 提交给 AI，合并结果 ...

# 总成本：$0 + $2.5 = $2.5
```

### 基础示例

```bash
# 快速体验完整流程（含 5 个样本数据）
cd examples/
python basic-batch.py                  # 演示本地引擎模式
python basic-batch.py --mode pipeline  # 演示 AI 管线模式
```

---

**版本历史**：
- 1.0.0 (2025-06)：初始版本，定义基本分批管线模式
- 1.1.0 (2026-06)：新增 examples/ 目录；完善决策树；补充领域信号配置文档；优化模块地图分类（区分脚本 vs 参考 vs 示例）；增强模型适配指导