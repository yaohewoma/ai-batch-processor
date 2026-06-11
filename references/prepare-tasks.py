#!/usr/bin/env python3
"""
AI 任务准备脚本 —— 将数据集拆分为 AI 友好的批次
支持嵌入正文、截断、精简字段

用法:
    python prepare_tasks.py --input data.json --output tasks/
    python prepare_tasks.py --input data.json --output tasks/ --batch-size 30 --top 300
    python prepare_tasks.py --input data.json --output tasks/ --filter qualityGrade=S
    python prepare_tasks.py --input data.json --output tasks/ --filter classification.productType=工具
"""
import json
import os
import argparse
import math
import sys
import logging
from typing import Any, Dict, List, Optional, Tuple

# =============================================================================
# 日志配置
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# 配置常量
# =============================================================================

DEFAULT_BATCH_SIZE = 30        # 默认每批条数
TEXT_TRUNCATE = 3000           # 正文截断长度（字）
EXCERPT_TRUNCATE = 200         # 摘要截断长度（字）
STRENGTHS_MAX = 3              # 最多保留优势数
WEAKNESSES_MAX = 3             # 最多保留劣势数
TOKEN_PER_ITEM = 500           # 每条数据估算 token 数
PROMPT_OVERHEAD = 200          # Prompt 模板固定开销 token 数


# =============================================================================
# Prompt 配置
# =============================================================================

PROMPT_HEADER = """你是一个资深的产品分析师。请基于以下项目数据，为每个项目生成AI洞察报告。

要求：
1. 为每个项目输出一个JSON对象，包含以下字段：
   - topicId: 项目ID（字符串）
   - aiInsight: 包含以下结构的洞察对象：
     - summary: 一句话总结（30字以内）
     - competitiveEdge: 核心竞争优势分析（50-80字）
     - risks: 潜在风险点（列表，2-3个，每个30-50字）
     - suggestions: 改进建议（列表，2-3个，每个30-50字）
     - marketOpportunity: 市场机会分析（50-80字）

2. 分析维度：功能性、创新性、用户体验、技术难度、实用性

3. 输出格式：严格JSON数组 [{...}, {...}]，可直接解析。

以下是第{batch_id}批的项目数据（共{count}个）：

{projects_json}

请开始分析并输出JSON数组："""


# =============================================================================
# 辅助函数
# =============================================================================

def _progress_bar(current: int, total: int, prefix: str = "", width: int = 40) -> None:
    """打印简易进度条到 stderr"""
    if total <= 0:
        return
    pct = current / total
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    sys.stderr.write(f"\r{prefix} [{bar}] {current}/{total} ({pct*100:.0f}%)")
    if current >= total:
        sys.stderr.write("\n")
    sys.stderr.flush()


def _get_nested_value(obj: Dict[str, Any], key_path: str) -> Any:
    """从嵌套字典中按路径获取值，如 'classification.productType'"""
    keys = key_path.split(".")
    current: Any = obj
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k)
        else:
            return None
    return current


def _parse_filter(raw_filter: str) -> Tuple[str, str]:
    """解析过滤条件字符串，支持嵌套字段

    格式: key=value 或 nested.key=value
    返回: (key_path, value)
    """
    if "=" not in raw_filter:
        logger.error(
            "过滤条件格式错误: '%s'。请使用 key=value 格式，"
            "例如: --filter qualityGrade=S 或 --filter classification.productType=工具",
            raw_filter,
        )
        sys.exit(1)
    parts = raw_filter.split("=", 1)
    key = parts[0].strip()
    value = parts[1].strip() if len(parts) > 1 else ""
    if not key:
        logger.error("过滤条件键为空: '%s'", raw_filter)
        sys.exit(1)
    return key, value


def _estimate_tokens(projects: List[Dict[str, Any]]) -> Dict[str, int]:
    """估算 token 消耗"""
    total_items = len(projects)
    return {
        "total_projects": total_items,
        "per_item": TOKEN_PER_ITEM,
        "per_batch_estimate": DEFAULT_BATCH_SIZE * TOKEN_PER_ITEM + PROMPT_OVERHEAD,
        "total_estimate": total_items * TOKEN_PER_ITEM + PROMPT_OVERHEAD,
    }


# =============================================================================
# 数据精简
# =============================================================================

def simplify_project(
    project: Dict[str, Any],
    include_text: bool = False,
    text_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """精简项目数据，只保留 AI 分析需要的字段"""
    tid = project.get("topicId", project.get("id", ""))

    # 尝试加载正文
    text_content = ""
    if include_text and text_dir:
        text_path = os.path.join(text_dir, f"topic_{tid}.txt")
        if os.path.exists(text_path):
            with open(text_path, "r", encoding="utf-8") as f:
                text_content = f.read()[:TEXT_TRUNCATE]

    return {
        "topicId": str(tid),
        "title": project.get("title", ""),
        "avgScore": project.get("avgScore", 0),
        "qualityGrade": project.get("qualityGrade", ""),
        "scores": project.get("scores", {}),
        "strengths": project.get("strengths", [])[:STRENGTHS_MAX],
        "weaknesses": project.get("weaknesses", [])[:WEAKNESSES_MAX],
        "oneLiner": project.get("oneLiner", ""),
        "votes": project.get("votes", 0),
        "excerpt": (project.get("excerpt", "") or "")[:EXCERPT_TRUNCATE],
        "text": text_content[:TEXT_TRUNCATE],
    }


# =============================================================================
# 任务文件生成
# =============================================================================

def generate_task_files(
    projects: List[Dict[str, Any]],
    output_dir: str,
    batch_size: int,
    include_text: bool = False,
    text_dir: Optional[str] = None,
) -> int:
    """为每个批次生成独立任务文件，返回批次总数"""
    os.makedirs(output_dir, exist_ok=True)
    batch_count = math.ceil(len(projects) / batch_size)

    manifest: List[Dict[str, Any]] = []

    for batch_id in range(batch_count):
        start = batch_id * batch_size
        end = min(start + batch_size, len(projects))
        batch = projects[start:end]

        simplified = [simplify_project(p, include_text, text_dir) for p in batch]

        task_content = {
            "batchId": batch_id + 1,
            "totalBatches": batch_count,
            "count": len(simplified),
            "projects": simplified,
            "prompt": PROMPT_HEADER.format(
                batch_id=batch_id + 1,
                count=len(simplified),
                projects_json=json.dumps(simplified, ensure_ascii=False, indent=2),
            ),
        }

        batch_path = os.path.join(output_dir, f"batch_{batch_id + 1:03d}.json")
        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump(task_content, f, ensure_ascii=False, indent=2)

        logger.info(
            "  Batch %d/%d: %s (%d projects)",
            batch_id + 1, batch_count, batch_path, len(simplified),
        )
        manifest.append({
            "batchId": batch_id + 1,
            "count": len(simplified),
            "file": os.path.basename(batch_path),
        })
        _progress_bar(batch_id + 1, batch_count, "Generating batched tasks")

    # 保存 manifest
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return batch_count


# =============================================================================
# 主函数
# =============================================================================

def main() -> None:
    """主入口"""
    parser = argparse.ArgumentParser(
        description="AI Batch Processor / Prepare Tasks - 将数据集拆分为 AI 友好的批次，支持正文嵌入和过滤",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python %(prog)s --input data.json --output tasks/ --batch-size 30
  python %(prog)s --input data.json --output tasks/ --top 300 --filter qualityGrade=S
  python %(prog)s --input data.json --output tasks/ --text-dir data/text/
  python %(prog)s --input data.json --output tasks/ --filter classification.productType=工具
        """.strip()
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to input JSON file (projects list)",
    )
    parser.add_argument(
        "--output", required=True,
        help="Output directory for batch task files",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help="Items per batch (default: %(default)s)",
    )
    parser.add_argument(
        "--top", type=int, default=0,
        help="Only process top N projects by votes (0=all)",
    )
    parser.add_argument(
        "--text-dir", default="",
        help="Directory with text files to embed in tasks",
    )
    parser.add_argument(
        "--filter", default="",
        help="Filter by key=value (e.g., qualityGrade=S, classification.productType=工具)",
    )
    args = parser.parse_args()

    # 输入文件校验
    if not os.path.isfile(args.input):
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)

    logger.info("Reading: %s", args.input)
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    projects = data.get("projects", data if isinstance(data, list) else [])

    if not projects:
        logger.warning("No projects found in input data")
        return

    # 过滤非官方
    projects = [p for p in projects if not p.get("isOfficial")]

    # 按投票排序
    projects = sorted(projects, key=lambda x: x.get("votes", 0), reverse=True)

    # 过滤（支持嵌套字段）
    if args.filter:
        filter_key, filter_val = _parse_filter(args.filter)
        if "." in filter_key:
            # 嵌套字段过滤
            projects = [
                p for p in projects
                if str(_get_nested_value(p, filter_key)) == filter_val
            ]
        else:
            projects = [
                p for p in projects
                if str(p.get(filter_key, "")) == filter_val
            ]
        logger.info(
            "  Filtered by %s=%s: %d projects",
            filter_key, filter_val, len(projects),
        )

    # Top N
    if args.top > 0:
        projects = projects[:args.top]

    logger.info("  Projects: %d", len(projects))
    logger.info("  Batch size: %d", args.batch_size)

    # Token 估算输出
    token_est = _estimate_tokens(projects)
    logger.info(
        "  Token estimate: ~%d per item, ~%d per batch, ~%d total",
        token_est["per_item"],
        token_est["per_batch_estimate"],
        token_est["total_estimate"],
    )

    include_text = bool(args.text_dir)
    batch_count = generate_task_files(
        projects, args.output, args.batch_size, include_text, args.text_dir,
    )

    logger.info("")
    logger.info("Done: %d batches in %s/", batch_count, args.output)


if __name__ == "__main__":
    main()