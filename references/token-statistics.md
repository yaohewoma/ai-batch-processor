# Token 统计模块

## 概述

统计 AI API 调用的 token 使用量和成本，支持多模型计费和预算控制。

## 配置

```python
# Token 统计配置
TOKEN_STATS_CONFIG = {
    "enabled": True,
    "track_by_model": True,  # 按模型分别统计
    "track_by_batch": True,  # 按批次分别统计
    "cost_per_1k_tokens": {  # 每 1000 token 的成本（美元）
        "gpt-4": 0.03,
        "gpt-4-turbo": 0.01,
        "gpt-3.5-turbo": 0.002,
        "claude-3-opus": 0.015,
        "claude-3-sonnet": 0.003,
        "claude-3-haiku": 0.00025
    },
    "budget_limit": 100.0,  # 预算上限（美元）
    "alert_threshold": 0.8,  # 预警阈值（80%）
    "log_file": "token_usage.log"
}
```

## 实现

```python
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token 使用记录"""
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    timestamp: datetime
    batch_id: Optional[str] = None
    request_id: Optional[str] = None


@dataclass
class CostSummary:
    """成本汇总"""
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0
    request_count: int = 0


class TokenTracker:
    """Token 追踪器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", True)
        self.track_by_model = config.get("track_by_model", True)
        self.track_by_batch = config.get("track_by_batch", True)
        self.cost_rates = config.get("cost_per_1k_tokens", {})
        self.budget_limit = config.get("budget_limit", float("inf"))
        self.alert_threshold = config.get("alert_threshold", 0.8)
        
        # 统计数据
        self.usage_history: List[TokenUsage] = []
        self.model_stats: Dict[str, CostSummary] = defaultdict(CostSummary)
        self.batch_stats: Dict[str, CostSummary] = defaultdict(CostSummary)
        self.daily_stats: Dict[str, CostSummary] = defaultdict(CostSummary)
        
        # 总计
        self.total = CostSummary()
        
        # 日志
        self.log_file = config.get("log_file")
        if self.log_file:
            self._setup_file_logging()
    
    def _setup_file_logging(self):
        """设置文件日志"""
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(message)s")
        )
        logger.addHandler(file_handler)
    
    def calculate_cost(self, model: str, total_tokens: int) -> float:
        """计算成本"""
        rate = self.cost_rates.get(model, 0.0)
        return (total_tokens / 1000) * rate
    
    def record_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        batch_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """记录 token 使用"""
        if not self.enabled:
            return {}
        
        total_tokens = prompt_tokens + completion_tokens
        cost = self.calculate_cost(model, total_tokens)
        timestamp = datetime.now()
        
        # 创建使用记录
        usage = TokenUsage(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            timestamp=timestamp,
            batch_id=batch_id,
            request_id=request_id
        )
        self.usage_history.append(usage)
        
        # 更新统计
        self._update_stats(usage, cost)
        
        # 检查预算
        self._check_budget()
        
        # 日志记录
        self._log_usage(usage, cost)
        
        return {
            "tokens": total_tokens,
            "cost": cost,
            "model": model,
            "total_cost": self.total.total_cost
        }
    
    def _update_stats(self, usage: TokenUsage, cost: float):
        """更新统计数据"""
        # 总计
        self.total.total_tokens += usage.total_tokens
        self.total.prompt_tokens += usage.prompt_tokens
        self.total.completion_tokens += usage.completion_tokens
        self.total.total_cost += cost
        self.total.request_count += 1
        
        # 按模型统计
        if self.track_by_model:
            model_stat = self.model_stats[usage.model]
            model_stat.total_tokens += usage.total_tokens
            model_stat.prompt_tokens += usage.prompt_tokens
            model_stat.completion_tokens += usage.completion_tokens
            model_stat.total_cost += cost
            model_stat.request_count += 1
        
        # 按批次统计
        if self.track_by_batch and usage.batch_id:
            batch_stat = self.batch_stats[usage.batch_id]
            batch_stat.total_tokens += usage.total_tokens
            batch_stat.prompt_tokens += usage.prompt_tokens
            batch_stat.completion_tokens += usage.completion_tokens
            batch_stat.total_cost += cost
            batch_stat.request_count += 1
        
        # 按日统计
        day_key = usage.timestamp.strftime("%Y-%m-%d")
        daily_stat = self.daily_stats[day_key]
        daily_stat.total_tokens += usage.total_tokens
        daily_stat.prompt_tokens += usage.prompt_tokens
        daily_stat.completion_tokens += usage.completion_tokens
        daily_stat.total_cost += cost
        daily_stat.request_count += 1
    
    def _check_budget(self):
        """检查预算"""
        if self.total.total_cost >= self.budget_limit:
            logger.error(
                "Budget exceeded! Current: $%.2f, Limit: $%.2f",
                self.total.total_cost,
                self.budget_limit
            )
            raise Exception(f"Budget exceeded: ${self.total.total_cost:.2f}")
        
        if self.total.total_cost >= self.budget_limit * self.alert_threshold:
            logger.warning(
                "Budget alert: $%.2f / $%.2f (%.0f%%)",
                self.total.total_cost,
                self.budget_limit,
                (self.total.total_cost / self.budget_limit) * 100
            )
    
    def _log_usage(self, usage: TokenUsage, cost: float):
        """记录日志"""
        logger.info(
            "Token usage: model=%s, tokens=%d, cost=$%.4f, total=$%.2f",
            usage.model,
            usage.total_tokens,
            cost,
            self.total.total_cost
        )
    
    def get_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        return {
            "total": {
                "tokens": self.total.total_tokens,
                "cost": self.total.total_cost,
                "requests": self.total.request_count,
                "avg_tokens_per_request": (
                    self.total.total_tokens / self.total.request_count
                    if self.total.request_count > 0 else 0
                )
            },
            "by_model": {
                model: {
                    "tokens": stats.total_tokens,
                    "cost": stats.total_cost,
                    "requests": stats.request_count
                }
                for model, stats in self.model_stats.items()
            },
            "by_batch": {
                batch: {
                    "tokens": stats.total_tokens,
                    "cost": stats.total_cost,
                    "requests": stats.request_count
                }
                for batch, stats in self.batch_stats.items()
            },
            "budget": {
                "limit": self.budget_limit,
                "used": self.total.total_cost,
                "remaining": self.budget_limit - self.total.total_cost,
                "usage_percent": (self.total.total_cost / self.budget_limit) * 100
            }
        }
    
    def get_batch_summary(self, batch_id: str) -> Dict[str, Any]:
        """获取批次统计"""
        stats = self.batch_stats.get(batch_id, CostSummary())
        return {
            "batch_id": batch_id,
            "tokens": stats.total_tokens,
            "cost": stats.total_cost,
            "requests": stats.request_count,
            "prompt_tokens": stats.prompt_tokens,
            "completion_tokens": stats.completion_tokens
        }
    
    def export_to_json(self, filepath: str):
        """导出统计到 JSON"""
        data = {
            "exported_at": datetime.now().isoformat(),
            "summary": self.get_summary(),
            "history": [
                {
                    "model": u.model,
                    "prompt_tokens": u.prompt_tokens,
                    "completion_tokens": u.completion_tokens,
                    "total_tokens": u.total_tokens,
                    "timestamp": u.timestamp.isoformat(),
                    "batch_id": u.batch_id,
                    "cost": self.calculate_cost(u.model, u.total_tokens)
                }
                for u in self.usage_history
            ]
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def reset(self):
        """重置统计"""
        self.usage_history.clear()
        self.model_stats.clear()
        self.batch_stats.clear()
        self.daily_stats.clear()
        self.total = CostSummary()
```

## 使用示例

### 基本用法

```python
# 初始化追踪器
token_config = {
    "enabled": True,
    "cost_per_1k_tokens": {
        "gpt-4": 0.03,
        "gpt-3.5-turbo": 0.002
    },
    "budget_limit": 50.0,
    "alert_threshold": 0.8
}
tracker = TokenTracker(token_config)

# 记录使用
result = tracker.record_usage(
    model="gpt-4",
    prompt_tokens=1000,
    completion_tokens=500,
    batch_id="batch_001"
)
print(f"本次成本: ${result['cost']:.4f}")
print(f"总成本: ${result['total_cost']:.2f}")

# 获取统计
summary = tracker.get_summary()
print(f"总 token: {summary['total']['tokens']}")
print(f"总成本: ${summary['total']['cost']:.2f}")
print(f"预算使用: {summary['budget']['usage_percent']:.1f}%")
```

### 集成到 AI 调用

```python
class AIProcessor:
    """带 token 统计的 AI 处理器"""
    
    def __init__(self, token_tracker: TokenTracker):
        self.tracker = token_tracker
    
    def analyze(self, text: str, model: str = "gpt-4") -> Dict[str, Any]:
        """分析文本"""
        # 构建 prompt
        prompt = f"分析以下内容并返回 JSON 格式结果:\n{text}"
        
        # 调用 API
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # 记录 token 使用
        usage = response.usage
        self.tracker.record_usage(
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens
        )
        
        # 解析结果
        return json.loads(response.choices[0].message.content)
```

### 批量处理统计

```python
def process_batch_with_stats(
    items: List[Dict[str, Any]],
    processor: AIProcessor,
    batch_id: str
) -> Dict[str, Any]:
    """带统计的批量处理"""
    results = []
    
    for item in items:
        try:
            result = processor.analyze(item["text"])
            results.append({
                "item": item,
                "result": result,
                "status": "success"
            })
        except Exception as e:
            results.append({
                "item": item,
                "error": str(e),
                "status": "failed"
            })
    
    # 获取批次统计
    batch_summary = processor.tracker.get_batch_summary(batch_id)
    
    return {
        "batch_id": batch_id,
        "total_items": len(items),
        "successful": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "token_usage": batch_summary,
        "results": results
    }
```

## 成本估算

### 预估公式

```python
def estimate_cost(
    num_items: int,
    avg_prompt_tokens: int,
    avg_completion_tokens: int,
    model: str,
    cost_rates: Dict[str, float]
) -> float:
    """预估批量处理成本"""
    total_tokens = num_items * (avg_prompt_tokens + avg_completion_tokens)
    rate = cost_rates.get(model, 0.0)
    return (total_tokens / 1000) * rate

# 示例
estimated = estimate_cost(
    num_items=1000,
    avg_prompt_tokens=500,
    avg_completion_tokens=200,
    model="gpt-4",
    cost_rates={"gpt-4": 0.03}
)
print(f"预估成本: ${estimated:.2f}")
```

## 报告生成

```python
def generate_usage_report(tracker: TokenTracker) -> str:
    """生成使用报告"""
    summary = tracker.get_summary()
    
    report = f"""
Token 使用报告
================

总计统计:
- 总请求数: {summary['total']['requests']}
- 总 Token 数: {summary['total']['tokens']:,}
- 总成本: ${summary['total']['cost']:.2f}
- 平均 Token/请求: {summary['total']['avg_tokens_per_request']:.0f}

预算使用:
- 预算上限: ${summary['budget']['limit']:.2f}
- 已使用: ${summary['budget']['used']:.2f}
- 剩余: ${summary['budget']['remaining']:.2f}
- 使用率: {summary['budget']['usage_percent']:.1f}%

按模型统计:
"""
    
    for model, stats in summary['by_model'].items():
        report += f"- {model}: {stats['tokens']:,} tokens, ${stats['cost']:.2f}\n"
    
    return report
```

## 注意事项

1. **实时追踪**：每次 API 调用后立即记录
2. **预算控制**：设置合理的预算上限和预警阈值
3. **成本优化**：根据使用统计选择性价比最高的模型
4. **数据导出**：定期导出统计数据用于分析
5. **多维度统计**：支持按模型、批次、日期等维度统计
