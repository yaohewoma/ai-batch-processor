# 重试机制模块

## 概述

为 AI API 调用提供健壮的重试机制，支持指数退避、断路器模式和自动降级。

## 配置

```python
# 重试配置
RETRY_CONFIG = {
    "max_retries": 3,  # 最大重试次数
    "base_delay": 1.0,  # 基础延迟（秒）
    "max_delay": 60.0,  # 最大延迟（秒）
    "exponential_base": 2,  # 指数退避基数
    "jitter": True,  # 添加随机抖动
    "retryable_errors": [  # 可重试的错误类型
        "rate_limit_exceeded",
        "server_error",
        "timeout",
        "connection_error"
    ],
    "non_retryable_errors": [  # 不可重试的错误类型
        "invalid_api_key",
        "invalid_request",
        "content_filter"
    ]
}

# 断路器配置
CIRCUIT_BREAKER_CONFIG = {
    "enabled": True,
    "failure_threshold": 5,  # 连续失败次数阈值
    "reset_timeout": 300,  # 断路器重置超时（秒）
    "half_open_requests": 3  # 半开状态请求数
}
```

## 实现

```python
import time
import random
import logging
from typing import Any, Callable, Dict, List, Optional, TypeVar
from dataclasses import dataclass
from enum import Enum
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """断路器状态"""
    CLOSED = "closed"  # 正常状态
    OPEN = "open"  # 断开状态
    HALF_OPEN = "half_open"  # 半开状态


@dataclass
class RetryStats:
    """重试统计"""
    total_attempts: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    retries: int = 0
    total_delay: float = 0.0


class CircuitBreaker:
    """断路器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", True)
        self.failure_threshold = config.get("failure_threshold", 5)
        self.reset_timeout = config.get("reset_timeout", 300)
        self.half_open_requests = config.get("half_open_requests", 3)
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.half_open_count = 0
    
    def can_execute(self) -> bool:
        """检查是否可以执行请求"""
        if not self.enabled:
            return True
        
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # 检查是否可以转为半开状态
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_count = 0
                return True
            return False
        
        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_count < self.half_open_requests
        
        return False
    
    def record_success(self):
        """记录成功"""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_count += 1
            if self.half_open_count >= self.half_open_requests:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0
    
    def record_failure(self):
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def reset(self):
        """重置断路器"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.half_open_count = 0


class RetryManager:
    """重试管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.max_retries = config.get("max_retries", 3)
        self.base_delay = config.get("base_delay", 1.0)
        self.max_delay = config.get("max_delay", 60.0)
        self.exponential_base = config.get("exponential_base", 2)
        self.jitter = config.get("jitter", True)
        self.retryable_errors = set(config.get("retryable_errors", []))
        self.non_retryable_errors = set(config.get("non_retryable_errors", []))
        
        # 断路器
        circuit_config = config.get("circuit_breaker", {})
        self.circuit_breaker = CircuitBreaker(circuit_config)
        
        # 统计
        self.stats = RetryStats()
    
    def is_retryable(self, error: Exception) -> bool:
        """判断错误是否可重试"""
        error_type = type(error).__name__.lower()
        
        # 检查不可重试的错误
        for non_retryable in self.non_retryable_errors:
            if non_retryable in error_type or non_retryable in str(error).lower():
                return False
        
        # 检查可重试的错误
        for retryable in self.retryable_errors:
            if retryable in error_type or retryable in str(error).lower():
                return True
        
        # 默认：服务器错误和网络错误可重试
        if hasattr(error, "status_code"):
            return error.status_code >= 500
        
        return True
    
    def calculate_delay(self, attempt: int) -> float:
        """计算延迟时间"""
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        
        if self.jitter:
            # 添加 ±25% 的随机抖动
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0, delay)
    
    def execute_with_retry(
        self,
        func: Callable[..., T],
        *args,
        **kwargs
    ) -> T:
        """带重试的执行函数"""
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            self.stats.total_attempts += 1
            
            # 检查断路器
            if not self.circuit_breaker.can_execute():
                raise Exception("Circuit breaker is open")
            
            try:
                result = func(*args, **kwargs)
                self.stats.successful_attempts += 1
                self.circuit_breaker.record_success()
                return result
            
            except Exception as e:
                last_error = e
                self.stats.failed_attempts += 1
                self.circuit_breaker.record_failure()
                
                # 检查是否可重试
                if not self.is_retryable(e):
                    logger.error("Non-retryable error: %s", str(e))
                    raise
                
                # 最后一次尝试失败
                if attempt == self.max_retries:
                    logger.error(
                        "Max retries (%d) exceeded. Last error: %s",
                        self.max_retries,
                        str(e)
                    )
                    raise
                
                # 计算延迟并等待
                delay = self.calculate_delay(attempt)
                self.stats.retries += 1
                self.stats.total_delay += delay
                
                logger.warning(
                    "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                    attempt + 1,
                    self.max_retries + 1,
                    str(e),
                    delay
                )
                time.sleep(delay)
        
        raise last_error


def with_retry(config: Dict[str, Any]):
    """重试装饰器"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        retry_manager = RetryManager(config)
        
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            return retry_manager.execute_with_retry(func, *args, **kwargs)
        
        wrapper.retry_manager = retry_manager
        return wrapper
    
    return decorator
```

## 使用示例

### 基本用法

```python
# 初始化重试管理器
retry_config = {
    "max_retries": 3,
    "base_delay": 1.0,
    "max_delay": 30.0,
    "exponential_base": 2,
    "jitter": True,
    "retryable_errors": ["rate_limit_exceeded", "server_error", "timeout"],
    "non_retryable_errors": ["invalid_api_key", "invalid_request"]
}
retry_manager = RetryManager(retry_config)

# 带重试的 API 调用
def call_ai_api(prompt: str) -> str:
    """调用 AI API"""
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# 执行带重试的调用
try:
    result = retry_manager.execute_with_retry(call_ai_api, "分析这个产品...")
    print(result)
except Exception as e:
    print(f"最终失败: {e}")

# 查看统计
print(f"总尝试: {retry_manager.stats.total_attempts}")
print(f"成功: {retry_manager.stats.successful_attempts}")
print(f"重试次数: {retry_manager.stats.retries}")
```

### 使用装饰器

```python
@with_retry({
    "max_retries": 3,
    "base_delay": 2.0,
    "circuit_breaker": {
        "enabled": True,
        "failure_threshold": 5
    }
})
def analyze_with_ai(text: str) -> Dict[str, Any]:
    """带重试的 AI 分析"""
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": f"分析: {text}"}]
    )
    return json.loads(response.choices[0].message.content)

# 使用
result = analyze_with_ai("产品描述...")
```

### 批量处理

```python
class BatchProcessor:
    """带重试的批量处理器"""
    
    def __init__(self, retry_config: Dict[str, Any]):
        self.retry_manager = RetryManager(retry_config)
        self.results = []
        self.errors = []
    
    def process_batch(self, items: List[Dict[str, Any]], 
                     process_func: Callable) -> Dict[str, Any]:
        """处理一批数据"""
        batch_results = []
        batch_errors = []
        
        for i, item in enumerate(items):
            try:
                result = self.retry_manager.execute_with_retry(
                    process_func, item
                )
                batch_results.append({
                    "index": i,
                    "item": item,
                    "result": result,
                    "status": "success"
                })
            except Exception as e:
                batch_errors.append({
                    "index": i,
                    "item": item,
                    "error": str(e),
                    "status": "failed"
                })
        
        self.results.extend(batch_results)
        self.errors.extend(batch_errors)
        
        return {
            "total": len(items),
            "success": len(batch_results),
            "failed": len(batch_errors),
            "results": batch_results,
            "errors": batch_errors
        }
```

## 错误分类

### 可重试错误

| 错误类型 | HTTP 状态码 | 说明 |
|---------|------------|------|
| rate_limit_exceeded | 429 | 请求频率超限 |
| server_error | 500, 502, 503 | 服务器内部错误 |
| timeout | - | 请求超时 |
| connection_error | - | 网络连接错误 |

### 不可重试错误

| 错误类型 | HTTP 状态码 | 说明 |
|---------|------------|------|
| invalid_api_key | 401 | API 密钥无效 |
| invalid_request | 400 | 请求参数错误 |
| content_filter | 400 | 内容被过滤 |
| quota_exceeded | 429 | 配额耗尽 |

## 注意事项

1. **指数退避**：避免频繁重试导致服务器压力增大
2. **随机抖动**：防止多个客户端同时重试造成"惊群效应"
3. **断路器**：快速失败，避免资源浪费
4. **错误分类**：区分可重试和不可重试的错误
5. **统计监控**：记录重试统计，便于问题排查
