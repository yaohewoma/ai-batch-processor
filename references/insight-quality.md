# 洞察质量度量与检查清单

> 如何度量和保证本地洞察引擎 + AI 管线生成的洞察质量

## 一、质量维度

### 1.1 差异度 (Differentiation Rate)

**定义**：不同项目之间，同一字段（summary / competitiveEdge 等）的内容差异程度。

**计算方式**：

```python
def differentiation_rate(projects, field):
    values = [p["aiInsight"][field] for p in projects]
    unique = len(set(v for v in values if v))
    return unique / len(values) * 100
```

**基准**：

| 字段 | 最低标准 | 良好 | 优秀 |
|------|---------|------|------|
| summary | > 60% | > 80% | > 95% |
| competitiveEdge | > 60% | > 80% | > 95% |
| risks | > 40% | > 60% | > 80% |
| suggestions | > 30% | > 50% | > 70% |
| marketOpportunity | > 40% | > 60% | > 80% |

> 说明：risks 和 suggestions 允许较低差异度，因为常见问题（如"优化UX"、"增强推广"）确实会跨项目重复。

### 1.2 内容完整性 (Completeness)

| 检查项 | 标准 |
|--------|------|
| 所有字段非空 | 100% |
| summary 非空字符串 | 100% |
| competitiveEdge 非空字符串 | 100% |
| risks 列表非空（>= 2 个） | 100% |
| suggestions 列表非空（>= 2 个） | 100% |
| marketOpportunity 非空字符串 | 100% |

### 1.3 字数合规性 (Length Compliance)

| 字段 | 标准范围 | 严重偏离阈值 |
|------|---------|-------------|
| summary | 15-30 字 | > 50 字 or < 5 字 |
| competitiveEdge | 30-120 字 | > 200 字 or < 15 字 |
| risks 单个项 | 15-50 字 | > 100 字 or < 5 字 |
| suggestions 单个项 | 15-50 字 | > 100 字 or < 5 字 |
| marketOpportunity | 30-200 字 | > 300 字 or < 15 字 |

### 1.4 内容一致性 (Consistency)

| 检查项 | 通过标准 |
|--------|---------|
| S 级项目 insight 不含负面词汇 | summary/competitiveEdge 不含 "差/弱/低/不足" |
| C 级项目 insight 不夸大 | summary/competitiveEdge 不含 "顶尖/一流/卓越/非凡" |
| 高评分 (>= 8.0) 项目建议偏向增量优化 | 不说"全面改造/重构" |
| 低评分 (< 4.0) 项目建议偏向基础改进 | 应有"补齐短板/优化基础"类词汇 |
| risks 与 scores 软关联 | 低分维度应出现在 risk 中 |
| suggestions 与 risks 软关联 | 每个 risk 应有 1 个对应的 suggestion |

## 二、本地引擎质量检查命令

```bash
# 1. 基础差异度检查
python references/generate-insights.py --input enriched.json --check

# 2. 详细质量报告（需结合 data-audit-toolkit）
# 在 data-audit-toolkit 中运行：
python references/audit_insights.py --input enriched.json --report quality-report.html

# 3. 抽查策略（人工）
# 每 50 条随机抽查 3 条，检查是否有明显错误
python -c "
import json, random
data = json.load(open('enriched.json'))['projects']
samples = random.sample(data, min(3, len(data)))
for p in samples:
    print(f\"\\n{p['title']} ({p['qualityGrade']}, {p['avgScore']})\")
    print(f\"  Summary: {p['aiInsight']['summary']}\")
    print(f\"  Edge: {p['aiInsight']['competitiveEdge']}\")
    print(f\"  Risks: {p['aiInsight']['risks']}\")
    print(f\"  Suggestions: {p['aiInsight']['suggestions']}\")
"
```

## 三、AI 管线质量检查清单

### 合并前检查

```bash
# 检查 AI 返回的 JSON 文件有效性
python references/merge-insights.py --input scored.json --results ai_results/ --validate-only --verbose
```

输出示例：

```
[VALIDATE] ai_results/batch_001.json
  ✓ JSON 格式有效
  ✓ 包含 30 个项目
  ✓ 所有 topicId 存在于 master 数据

[VALIDATE] ai_results/batch_002.json
  ✓ JSON 格式有效
  ✓ 包含 30 个项目
  ! 发现 2 个 orphan insights (topicId 在主数据中不存在)
```

### 合并后检查

```bash
# 详细合并（含错误统计）
python references/merge-insights.py --input scored.json --results ai_results/ --output enriched.json --verbose
```

输出示例：

```
[MERGE] 合并完成:
  ✓ 成功合并: 298 条
  ✗ 失败（格式错误）: 0 条
  - 未匹配（AI 返回了不在 master 中的项目）: 2 条
  - 缺失（master 中有但 AI 未返回的项目）: 0 条
  - 孤儿洞察总数: 2 条
```

### 合并后差异度检查

```bash
python -c "
import json

with open('enriched.json') as f:
    data = json.load(f)['projects']

# 检查所有已合并字段
for field in ['summary', 'competitiveEdge']:
    values = [p['aiInsight'].get(field, '') for p in data]
    unique = len(set(v for v in values if v))
    rate = unique / len(values) * 100
    status = '✓' if rate >= 60 else '✗'
    print(f'{status} {field}: {unique}/{len(values)} ({rate:.1f}%)')
"
```

## 四、常见质量问题与修复

| 问题 | 症状 | 原因 | 修复 |
|------|------|------|------|
| 空洞话术 | 多个项目 insight 完全一致 | Prompt 太泛，无参考数据 | 传 scores/strengths/weaknesses，增加差异化指令 |
| AI 偷懒 | 第 20+ 条开始输出套话 | 一批太多条 | 减小批大小到 20-30 |
| 格式混乱 | JSON 被 markdown 包裹 | AI 习惯性输出 | merge-insights.py 自动处理 |
| 字数失控 | 500 字 summary | 未设字数限制 | Prompt 中标注 "(30字以内)" |
| 评分矛盾 | 低分项目 insight 说"竞争力强" | 未传参考数据 | 必传 avgScore/strengths/weaknesses |
| 建议空洞 | "优化用户体验" 通用 | 未结合具体数据 | Prompt 中要求基于 weaknesses 生成 |
| 幻觉 | AI 编造不存在的信息 | 正文过长，AI 发散 | 正文截断到 2000 字，限制分析维度 |

## 五、自动化质量度量的建议积分

将测试套件 (`tests/test_insights.py`) 集成到 CI/CD 或预提交检查：

```bash
# 运行完整测试套件
python tests/test_insights.py

# 预期输出:
# 通过: 10  失败: 0  跳过: 0
# ✓ 全部 10 个测试通过！

# 仅测试质量相关
python tests/test_insights.py --filter quality

# 仅测试数据契约
python tests/test_insights.py --filter contract
```

**测试覆盖**：

| 测试类别 | 测试项 | 自动/手动 |
|---------|-------|----------|
| 数据契约 | 必填字段、scores 格式、qualityGrade 有效性 | 自动 |
| 幂等性 | 同一项目两次运行结果一致 | 自动 |
| 字段完整性 | 所有 insight 字段非空 | 自动 |
| 差异度 | summary/edge 唯一率 >= 60% | 自动 |
| 内容限制 | 字数和数量在限制范围内 | 自动 |
| 评分一致性 | S 级不含负面词、C 级不夸大 | 自动 |
| 边界条件 | 空数据、极端评分不崩溃 | 自动 |
| 语义正确性 | insight 是否真正准确有意义 | **人工抽查** |
| 领域匹配 | 领域检测是否准确 | **人工抽查** |