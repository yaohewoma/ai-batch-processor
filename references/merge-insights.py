#!/usr/bin/env python3
"""
AI 洞察结果合并脚本 —— 校验并合并 AI 输出到主数据

用法:
    python merge_insights.py --input data.json --results results/ --output merged.json
    python merge_insights.py --input data.json --results results/ --output merged.json --validate-only
    python merge_insights.py --input data.json --results results/ --output merged.json --verbose
"""
import json
import os
import argparse
import glob
import shutil
import tempfile
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
# 常量
# =============================================================================

REQUIRED_INSIGHT_FIELDS = [
    "summary", "competitiveEdge", "risks", "suggestions", "marketOpportunity",
]


# =============================================================================
# JSON 校验
# =============================================================================

def validate_single_item(item: Dict[str, Any], batch_name: str) -> List[str]:
    """校验单条洞察数据，返回错误列表"""
    errors: List[str] = []

    if "topicId" not in item:
        errors.append("Missing topicId")
    if "aiInsight" not in item:
        errors.append("Missing aiInsight")

    if "aiInsight" in item:
        insight = item["aiInsight"]
        for field in REQUIRED_INSIGHT_FIELDS:
            if field not in insight:
                errors.append(f"Missing aiInsight.{field}")
        if "risks" in insight and not isinstance(insight["risks"], list):
            errors.append("aiInsight.risks is not a list")
        if "suggestions" in insight and not isinstance(insight["suggestions"], list):
            errors.append("aiInsight.suggestions is not a list")

    return errors


def validate_batch(
    batch_data: List[Dict[str, Any]],
    batch_name: str,
    expected_count: int = 0,
) -> List[str]:
    """校验整批数据，返回错误列表"""
    errors: List[str] = []

    if not isinstance(batch_data, list):
        errors.append(
            f"Batch is not a list (got {type(batch_data).__name__})",
        )
        return errors

    if expected_count > 0 and len(batch_data) != expected_count:
        errors.append(
            f"Count mismatch: expected {expected_count}, got {len(batch_data)}",
        )

    for i, item in enumerate(batch_data):
        item_errors = validate_single_item(item, batch_name)
        if item_errors:
            errors.append(f"Item {i}: {', '.join(item_errors)}")

    return errors


def load_and_validate(
    results_dir: str,
    verbose: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """加载并校验所有批次结果

    Returns:
        (all_results, stats) 元组
    """
    all_results: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {
        "total_files": 0, "total_items": 0, "valid_items": 0,
        "errors": {},
    }

    result_files = sorted(
        glob.glob(os.path.join(results_dir, "batch_*_result.json")),
    )

    for filepath in result_files:
        filename = os.path.basename(filepath)
        stats["total_files"] += 1

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # 处理可能的 markdown 包裹
            cleaned = content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]

            batch_data = json.loads(cleaned.strip())

            batch_errors = validate_batch(batch_data, filename)
            stats["total_items"] += len(batch_data)

            if batch_errors:
                stats["errors"][filename] = batch_errors
                logger.error(
                    "  %s: %d errors", filename, len(batch_errors),
                )
                for err in batch_errors[:3]:
                    logger.error("     %s", err)
                if verbose and len(batch_errors) > 3:
                    logger.error(
                        "     ... and %d more errors", len(batch_errors) - 3,
                    )
            else:
                stats["valid_items"] += len(batch_data)
                logger.info("  %s: %d items valid", filename, len(batch_data))

            all_results.extend(batch_data)

        except json.JSONDecodeError as e:
            logger.error("  %s: JSON parse error - %s", filename, e)
            stats.setdefault("errors", {})
            stats["errors"][filename] = [f"JSON parse error: {e}"]
            stats["total_items"] += 0  # 确保字段存在
        except Exception as e:
            logger.error("  %s: %s", filename, e)
            stats.setdefault("errors", {})
            stats["errors"][filename] = [f"Error: {e}"]
            stats["total_items"] += 0  # 确保字段存在

    return all_results, stats


# =============================================================================
# 合并
# =============================================================================

def merge_insights(
    main_data_path: str,
    all_results: List[Dict[str, Any]],
    output_path: str,
    verbose: bool = False,
) -> Dict[str, Any]:
    """将洞察结果合并回主数据，使用原子写入

    Returns:
        统计字典，包含 merged/total/unmatched/orphan 等字段
    """
    logger.info("Reading main data: %s", main_data_path)
    with open(main_data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    projects = data.get("projects", data if isinstance(data, list) else [])

    # 构建洞察映射
    insight_map: Dict[str, Dict[str, Any]] = {}
    for item in all_results:
        tid = str(item.get("topicId", ""))
        if tid and "aiInsight" in item:
            insight_map[tid] = item["aiInsight"]

    # 合并
    merged = 0
    unmatched_projects: List[str] = []
    for project in projects:
        tid = str(project.get("topicId", project.get("id", "")))
        if tid in insight_map:
            project["aiInsight"] = insight_map[tid]
            merged += 1
        else:
            unmatched_projects.append(tid)

    logger.info("  Merged: %d/%d projects", merged, len(projects))

    # 孤儿洞察检测
    project_ids = {str(p.get("topicId", p.get("id", ""))) for p in projects}
    orphan_insights = [tid for tid in insight_map if tid not in project_ids]

    if unmatched_projects:
        logger.warning(
            "  Unmatched projects (no insight found): %d", len(unmatched_projects),
        )
        if verbose and unmatched_projects:
            logger.warning(
                "    IDs: %s", ", ".join(unmatched_projects[:10]),
            )
            if len(unmatched_projects) > 10:
                logger.warning(
                    "    ... and %d more", len(unmatched_projects) - 10,
                )

    if orphan_insights:
        logger.warning(
            "  Orphan insights (no matching project): %d", len(orphan_insights),
        )
        if verbose and orphan_insights:
            logger.warning(
                "    IDs: %s", ", ".join(orphan_insights[:10]),
            )
            if len(orphan_insights) > 10:
                logger.warning(
                    "    ... and %d more", len(orphan_insights) - 10,
                )

    # 原子性写入：先写临时文件，再 shutil.move
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        suffix=".json", prefix="merged_", dir=output_dir,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shutil.move(tmp_path, output_path)
    except Exception:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    logger.info("  Output: %s", output_path)
    return {
        "merged": merged, "total": len(projects),
        "unmatched": len(unmatched_projects), "orphan": len(orphan_insights),
    }


# =============================================================================
# 主函数
# =============================================================================

def main() -> None:
    """主入口"""
    parser = argparse.ArgumentParser(
        description="AI Batch Processor / Merge Insights - 校验并合并 AI 输出洞察到主数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python %(prog)s --input data.json --results results/ --output merged.json
  python %(prog)s --input data.json --results results/ --validate-only
  python %(prog)s --input data.json --results results/ --output merged.json --verbose
        """.strip()
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to main data JSON file (original projects)",
    )
    parser.add_argument(
        "--results", required=True,
        help="Directory with AI result files (batch_*_result.json)",
    )
    parser.add_argument(
        "--output", default="merged.json",
        help="Path to output merged JSON file (default: %(default)s)",
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Only validate AI results, do not merge",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable verbose output with detailed error/mismatch information",
    )
    args = parser.parse_args()

    # 输入校验
    if not os.path.isfile(args.input):
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)

    if not os.path.isdir(args.results):
        logger.error("Results directory not found: %s", args.results)
        sys.exit(1)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled")

    logger.info("=" * 60)
    logger.info("  AI 洞察结果合并工具")
    logger.info("=" * 60)

    # 加载并校验
    all_results, stats = load_and_validate(args.results, verbose=args.verbose)

    total_errors = sum(len(v) for v in stats.get("errors", {}).values())

    logger.info("")
    logger.info("Validation Summary:")
    logger.info("  Files: %d", stats["total_files"])
    logger.info("  Items: %d", stats["total_items"])
    logger.info("  Valid: %d", stats["valid_items"])
    if total_errors:
        logger.warning("  Errors: %d", total_errors)

    if args.validate_only:
        if all_results:
            logger.info(
                "  Validate-only mode: %d results loaded, no merge performed",
                len(all_results),
            )
        return

    # 合并
    if all_results:
        merge_stats = merge_insights(
            args.input, all_results, args.output, verbose=args.verbose,
        )

        logger.info("")
        logger.info("=" * 60)
        logger.info("  Merge Summary")
        logger.info("=" * 60)
        logger.info("  Merged: %d/%d", merge_stats["merged"], merge_stats["total"])
        if merge_stats.get("unmatched", 0):
            logger.warning("  Unmatched projects: %d", merge_stats["unmatched"])
        if merge_stats.get("orphan", 0):
            logger.warning("  Orphan insights: %d", merge_stats["orphan"])
        logger.info("=" * 60)
    else:
        logger.error("")
        logger.error("No valid results to merge")


if __name__ == "__main__":
    main()