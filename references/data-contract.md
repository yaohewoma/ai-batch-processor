# 数据契约：AI Batch Processor

> **版本：2.0.0** | 最后更新：2026-06-05

## 输入格式

在 Rule Scoring Engine 产出的基础上（含 `scores`、`avgScore`、`qualityGrade`、`strengths`、`weaknesses`、`oneLiner`）：

```json
{
  "projects": [{
    "topicId": "123",
    "title": "项目标题",
    "rawText": "完整正文内容...",
    "scores": { "functionality": 6.5, "innovation": 7.0, "ux": 5.5, "visual": 6.0, "techDifficulty": 7.5, "practicality": 8.0 },
    "avgScore": 6.8,
    "qualityGrade": "A",
    "strengths": ["功能完整，描述详尽"],
    "weaknesses": ["交互设计较薄弱"],
    "oneLiner": "以实用价值和创新性为亮点的产品",
    "votes": 10,
    "replyCount": 5
  }]
}
```

### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `topicId` | string | 唯一标识 |
| `title` | string | 项目标题 |
| `scores` | object | 六维度评分 |
| `avgScore` | number | 平均分 |
| `qualityGrade` | string | 等级 S/A/B/C |

### JSON Schema 形式化定义

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ai-batch-processor/schemas/input-v2.json",
  "title": "AI Batch Processor Input Schema",
  "description": "Rule Scoring Engine 产出的已评分数据，作为 AI Batch Processor 的输入",
  "type": "object",
  "required": ["projects"],
  "properties": {
    "projects": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["topicId", "title", "scores", "avgScore", "qualityGrade"],
        "properties": {
          "topicId": {
            "type": "string",
            "description": "项目唯一标识"
          },
          "title": {
            "type": "string",
            "description": "项目标题"
          },
          "rawText": {
            "type": "string",
            "description": "完整正文内容"
          },
          "scores": {
            "type": "object",
            "description": "六维度评分",
            "required": ["functionality", "innovation", "ux", "visual", "techDifficulty", "practicality"],
            "properties": {
              "functionality": { "type": "number", "minimum": 0, "maximum": 10 },
              "innovation": { "type": "number", "minimum": 0, "maximum": 10 },
              "ux": { "type": "number", "minimum": 0, "maximum": 10 },
              "visual": { "type": "number", "minimum": 0, "maximum": 10 },
              "techDifficulty": { "type": "number", "minimum": 0, "maximum": 10 },
              "practicality": { "type": "number", "minimum": 0, "maximum": 10 }
            }
          },
          "avgScore": {
            "type": "number",
            "minimum": 0,
            "maximum": 10,
            "description": "六维度平均分"
          },
          "qualityGrade": {
            "type": "string",
            "enum": ["S", "A", "B", "C"],
            "description": "质量等级"
          },
          "strengths": {
            "type": "array",
            "items": { "type": "string" },
            "description": "项目优势列表"
          },
          "weaknesses": {
            "type": "array",
            "items": { "type": "string" },
            "description": "项目劣势列表"
          },
          "oneLiner": {
            "type": "string",
            "description": "一句话总结"
          },
          "votes": {
            "type": "integer",
            "minimum": 0,
            "description": "投票数"
          },
          "replyCount": {
            "type": "integer",
            "minimum": 0,
            "description": "回复数"
          }
        }
      }
    }
  }
}
```

## 输出格式

在输入数据基础上追加 `aiInsight` 字段：

```json
{
  "aiInsight": {
    "summary": "一句话总结（30字以内）",
    "competitiveEdge": "核心竞争优势分析（50-80字）",
    "risks": ["风险1（30-50字）", "风险2（30-50字）", "风险3（30-50字）"],
    "suggestions": ["建议1（30-50字）", "建议2（30-50字）", "建议3（30-50字）"],
    "marketOpportunity": "市场机会分析（50-80字）"
  }
}
```

### 洞察字段约束

| 字段 | 类型 | 字数限制 | 说明 |
|------|------|---------|------|
| `summary` | string | ≤ 30 字 | 一句话产品总结 |
| `competitiveEdge` | string | 50-80 字 | 核心竞争优势 |
| `risks` | string[] | 2-3 个，每个 30-50 字 | 潜在风险 |
| `suggestions` | string[] | 2-3 个，每个 30-50 字 | 改进建议 |
| `marketOpportunity` | string | 50-80 字 | 市场机会 |

### 输出 JSON Schema 形式化定义

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ai-batch-processor/schemas/output-v2.json",
  "title": "AI Batch Processor Output Schema",
  "description": "AI Batch Processor 处理后的输出数据，在输入基础上追加 aiInsight",
  "type": "object",
  "required": ["projects"],
  "properties": {
    "projects": {
      "type": "array",
      "items": {
        "allOf": [
          { "$ref": "#/definitions/projectInput" },
          {
            "properties": {
              "aiInsight": {
                "type": "object",
                "required": ["summary", "competitiveEdge", "risks", "suggestions", "marketOpportunity"],
                "properties": {
                  "summary": {
                    "type": "string",
                    "maxLength": 30,
                    "description": "一句话总结（30字以内）"
                  },
                  "competitiveEdge": {
                    "type": "string",
                    "description": "核心竞争优势分析（50-80字）"
                  },
                  "risks": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 3,
                    "items": { "type": "string" },
                    "description": "潜在风险点（2-3个，每个30-50字）"
                  },
                  "suggestions": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 3,
                    "items": { "type": "string" },
                    "description": "改进建议（2-3个，每个30-50字）"
                  },
                  "marketOpportunity": {
                    "type": "string",
                    "description": "市场机会分析（50-80字）"
                  }
                }
              }
            }
          }
        ]
      }
    }
  }
}
```

## 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| 1.0.0 | 2025-06 | 初始版本，定义基本输入输出格式 |
| 2.0.0 | 2026-06 | 添加 JSON Schema 形式化定义；新增版本号字段；明确字段约束 |

## 下游交接

参见 [SKILLS-INDEX.md](../SKILLS-INDEX.md#skill-3--skill-4-交接格式)