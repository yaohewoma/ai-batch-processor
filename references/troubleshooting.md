# AI Batch Processor — 故障排查指南

## 运行错误

### `FileNotFoundError: 找不到输入文件`

**症状**：运行 `generate-insights.py` 或 `full-pipeline.py` 时提示文件不存在。

**解决方案**：
```bash
# 确认输入文件路径
ls -la *.json

# 使用绝对路径
python generate-insights.py --input /absolute/path/to/scored.json --output enriched.json
```

### `JSONDecodeError: 合并失败`

**症状**：`merge-insights.py` 报 JSON 解析错误，无法合并 AI 输出。

**原因**：AI 返回的 JSON 格式不符合预期，常见问题：
1. AI 包裹了 markdown 代码块（` ```json ... ``` `）
2. JSON 数组中有格式错误（缺少逗号、引号不匹配）
3. AI 返回的项目数量与输入不一致

**解决方案**：
1. 脚本已内置处理 markdown 包裹的 JSON，无需额外操作
2. 手动检查 AI 返回的 JSON 文件：

```bash
python -c "import json; json.load(open('ai_results/batch_001.json'))"
```

3. 如果格式错误，请 AI 重新生成（附上格式要求）
4. 使用 `--validate-only` 仅校验不合并：

```bash
python merge-insights.py --input scored.json --results ai_results/ --validate-only
```

### 洞察数量与输入不匹配

**症状**：合并后部分项目缺少 `aiInsight` 字段。

**排查**：
1. 检查 AI 是否遗漏了某些项目
2. 检查 `merge-insights.py` 的错误统计输出
3. 使用 `--verbose` 模式查看未匹配项目和孤儿洞察的详细 ID：

```bash
python merge-insights.py --input scored.json --results ai_results/ --output merged.json --verbose
```

```bash
# 检查缺失洞察的项目
python -c "
import json
d = json.load(open('enriched.json'))
missing = [p['topicId'] for p in d['projects'] if 'aiInsight' not in p]
print(f'缺失洞察: {len(missing)} 个项目')
print(missing[:10])
"
```

## 洞察质量问题

### 洞察差异度过低

**症状**：多个项目的 `aiInsight` 内容高度相似，`--check` 验证差异度 < 50%。

**解决方案**：
1. 使用本地洞察引擎（`generate-insights.py`），它基于 MD5 种子保证差异度 > 90%
2. 如果使用外部 AI，检查 Prompt 是否要求"为每个项目生成独特的分析"
3. 在 Prompt 中增加"请根据每个项目的具体内容和评分生成差异化洞察"的指令

### 洞察内容与评分矛盾

**症状**：AI 生成的洞察与已有评分数据矛盾（如给低分项目写"竞争优势明显"）。

**原因**：Prompt 中未传递评分数据作为参考。

**解决方案**：
- 确保 `prepare-tasks.py` 生成的 Prompt 包含了 `avgScore`、`strengths`、`weaknesses`
- 脚本默认会传递这些字段，无需额外配置

### AI 输出字数超标

**症状**：AI 返回的 `summary` 字段超过 30 字，`suggestions` 超过 3 条。

**解决方案**：
1. 在 Prompt 中加强字数限制："严格控制在 {n} 字以内"
2. 减小 `prepare-tasks.py` 中的每批条数，给 AI 更多空间遵循指令
3. **注意：当前脚本不包含自动截断超长字段的功能**（此功能处于计划中，未来版本将实现）。目前建议在 Prompt 层面加强约束，或手动后处理。

## 性能问题

### 任务文件过大

**症状**：`tasks/` 目录下的单个任务文件超过 100KB。

**原因**：每批条数太多，或正文未截断。

**解决方案**：
```bash
# 减小批量大小
python prepare-tasks.py --input scored.json --output tasks/ --batch-size 15

# 确保正文截断到 2000 字（脚本默认行为）
```

### 本地洞察引擎运行慢

**症状**：`generate-insights.py` 处理大量数据时耗时较长。

**原因**：纯 Python 处理，无并发优化。

**解决方案**：
- 数据量 > 5000 条时，建议分批处理
- 考虑使用外部 AI 管线（`full-pipeline.py`）替代