"""
AI 批量任务编排管线
将大规模数据拆分为 AI 友好的批次，生成结构化 Prompt，校验并合并结果

用法:
    python full_pipeline.py --input data.json --output tasks/ --mode generate
    python full_pipeline.py --input data.json --output merged.json --mode merge --results-dir results/
    python full_pipeline.py --input data.json --output tasks/ --mode generate --dry-run
    python full_pipeline.py --input data.json --output merged.json --mode merge --results-dir results/ --dry-run

依赖: 无外部依赖，纯 Python 标准库
"""
import json
import argparse
import math
import os
import shutil
import sys
import logging
from datetime import datetime
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

BATCH_SIZE_DEFAULT = 30          # 每批默认条数，建议 30~50
TEXT_TRUNCATE = 2000             # 正文截断长度（字）
TOKEN_PER_ITEM = 500             # 每条数据的估算 token 数
PROMPT_OVERHEAD = 200            # Prompt 模板固定开销 token 数
MAX_STRENGTHS = 3                # 最多保留的优势条目数
MAX_WEAKNESSES = 3               # 最多保留的劣势条目数

PROMPT_TEMPLATE = """你是一个资深的产品分析师。请基于以下项目数据，为每个项目生成AI洞察报告。

要求：
1. 为每个项目输出一个JSON对象，包含以下字段：
   - topicId: 项目ID（字符串）
   - aiInsight: 包含以下结构的洞察对象：
     - summary: 一句话总结（30字以内）
     - competitiveEdge: 核心竞争优势分析（50-80字）
     - risks: 潜在风险点（列表，2-3个，每个30-50字）
     - suggestions: 改进建议（列表，2-3个，每个30-50字）
     - marketOpportunity: 市场机会分析（50-80字）

2. 分析维度：
   - 功能性：功能是否完整、是否解决真实问题
   - 创新性：是否有独特卖点、是否与竞品差异化
   - 用户体验：交互设计是否友好
   - 技术难度：技术实现复杂度
   - 实用性：实际应用场景、用户价值

3. 输出格式：
   请输出一个JSON数组，每个元素是一个项目的洞察对象。
   确保JSON格式正确，可以直接被解析。

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


# =============================================================================
# 数据精简
# =============================================================================

def simplify_project(project: Dict[str, Any]) -> Dict[str, Any]:
    """从完整数据中提取 AI 分析所需的最小子集，减少 token 消耗"""
    return {
        "topicId": str(project.get("topicId", project.get("id", ""))),
        "title": project.get("title", ""),
        "avgScore": project.get("avgScore", 0),
        "qualityGrade": project.get("qualityGrade", ""),
        "scores": project.get("scores", {}),
        "strengths": project.get("strengths", [])[:MAX_STRENGTHS],
        "weaknesses": project.get("weaknesses", [])[:MAX_WEAKNESSES],
        "oneLiner": project.get("oneLiner", ""),
        "rawText": (project.get("rawText", "") or "")[:TEXT_TRUNCATE],
    }


# =============================================================================
# 分批
# =============================================================================

def split_batches(
    projects: List[Dict[str, Any]],
    batch_size: int = BATCH_SIZE_DEFAULT,
) -> List[List[Dict[str, Any]]]:
    """将数据拆分为多个批次"""
    batches: List[List[Dict[str, Any]]] = []
    for i in range(0, len(projects), batch_size):
        batches.append(projects[i:i + batch_size])
    return batches


# =============================================================================
# 任务文件生成
# =============================================================================

def generate_task_files(
    batches: List[List[Dict[str, Any]]],
    output_dir: str,
    dry_run: bool = False,
) -> None:
    """为每个批次生成任务文件，供外部 AI 消费"""
    if dry_run:
        logger.info("[DRY-RUN] 将生成 %d 个批次的任务文件到 %s", len(batches), output_dir)
        for batch_id, batch in enumerate(batches):
            simplified = [simplify_project(p) for p in batch]
            logger.info(
                "  [DRY-RUN] Batch %d/%d: %d projects, ~%d tokens",
                batch_id + 1, len(batches), len(simplified),
                len(simplified) * TOKEN_PER_ITEM + PROMPT_OVERHEAD,
            )
        return

    os.makedirs(output_dir, exist_ok=True)

    for batch_id, batch in enumerate(batches):
        simplified = [simplify_project(p) for p in batch]
        task = {
            "batchId": batch_id + 1,
            "totalBatches": len(batches),
            "generatedAt": datetime.now().isoformat(),
            "count": len(simplified),
            "projects": simplified,
            "prompt": PROMPT_TEMPLATE.format(
                batch_id=batch_id + 1,
                count=len(simplified),
                projects_json=json.dumps(simplified, ensure_ascii=False, indent=2),
            ),
        }

        batch_path = os.path.join(output_dir, f"batch_{batch_id + 1:03d}.json")
        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False, indent=2)

        logger.info(
            "Generated batch %d/%d: %s (%d projects)",
            batch_id + 1, len(batches), batch_path, len(simplified),
        )
        _progress_bar(batch_id + 1, len(batches), "Generating batches")


# =============================================================================
# 输出校验
# =============================================================================

def validate_batch_output(
    output_text: str,
    expected_count: int,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """校验 AI 输出的 JSON 格式

    Returns:
        (valid_results, errors) 元组
        - valid_results: 校验通过的结果列表
        - errors: 错误信息列表
    """
    errors: List[str] = []

    try:
        # 处理可能的 markdown 包裹
        cleaned = output_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        results = json.loads(cleaned.strip())

        if not isinstance(results, list):
            raise ValueError("Output is not a JSON array")

        if len(results) != expected_count:
            logger.warning(
                "Expected %d items, got %d", expected_count, len(results),
            )
            errors.append(
                f"Count mismatch: expected {expected_count}, got {len(results)}",
            )

        # 校验必要字段
        valid_results: List[Dict[str, Any]] = []
        for i, item in enumerate(results):
            item_errors: List[str] = []
            if "topicId" not in item:
                item_errors.append("Missing topicId")
            if "aiInsight" not in item:
                item_errors.append("Missing aiInsight")
            if item_errors:
                errors.append(f"Item {i}: {', '.join(item_errors)}")
            else:
                valid_results.append(item)

        return valid_results, errors

    except json.JSONDecodeError as e:
        errors.append(f"JSON parse error: {e}")
        logger.error("Validation failed: %s", e)
        return [], errors
    except Exception as e:
        errors.append(f"Validation error: {e}")
        logger.error("Validation failed: %s", e)
        return [], errors


# =============================================================================
# 合并结果
# =============================================================================

def merge_results(
    all_results: List[List[Dict[str, Any]]],
    original_data_path: str,
    output_path: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """将 AI 结果合并回主数据

    Returns:
        统计摘要字典，包含 merged/total/unmatched/orphan 等字段
    """
    # 构建洞察映射
    insight_map: Dict[str, Dict[str, Any]] = {}
    for batch in all_results:
        for item in batch:
            insight_map[item["topicId"]] = item["aiInsight"]

    # 加载原始数据
    with open(original_data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    projects = data if isinstance(data, list) else data.get("projects", [])

    if dry_run:
        logger.info("[DRY-RUN] 将合并 %d 条洞察到 %d 个项目", len(insight_map), len(projects))
        # 统计未匹配
        project_ids = {
            str(p.get("topicId", p.get("id", ""))) for p in projects
        }
        unmatched = [tid for tid in insight_map if tid not in project_ids]
        unmatched_projects = [tid for tid in project_ids if tid not in insight_map]
        if unmatched:
            logger.warning("[DRY-RUN] 孤儿洞察: %d 条", len(unmatched))
        if unmatched_projects:
            logger.warning("[DRY-RUN] 未匹配项目: %d 个", len(unmatched_projects))
        return {
            "merged": 0, "total": len(projects), "unmatched": len(unmatched_projects),
            "orphan": len(unmatched),
        }

    # 合并前备份原始文件
    if os.path.exists(original_data_path):
        backup_path = original_data_path + ".backup." + datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(original_data_path, backup_path)
        logger.info("Backup created: %s", backup_path)

    # 合并
    merged_count = 0
    unmatched_projects: List[str] = []
    for project in projects:
        tid = str(project.get("topicId", project.get("id", "")))
        if tid in insight_map:
            project["aiInsight"] = insight_map[tid]
            merged_count += 1
        else:
            unmatched_projects.append(tid)

    # 孤儿洞察检测
    project_ids = {str(p.get("topicId", p.get("id", ""))) for p in projects}
    orphan_insights = [tid for tid in insight_map if tid not in project_ids]

    logger.info(
        "Merged %d/%d projects with AI insights", merged_count, len(projects),
    )

    if unmatched_projects:
        logger.warning(
            "Unmatched projects (no insight found): %d", len(unmatched_projects),
        )
    if orphan_insights:
        logger.warning(
            "Orphan insights (no matching project): %d", len(orphan_insights),
        )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Saved merged data to %s", output_path)
    return {
        "merged": merged_count, "total": len(projects),
        "unmatched": len(unmatched_projects), "orphan": len(orphan_insights),
    }


# =============================================================================
# 主流程
# =============================================================================

def run_generate(args: argparse.Namespace) -> None:
    """仅生成任务文件"""
    # 输入校验
    if not os.path.isfile(args.input):
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    projects = data if isinstance(data, list) else data.get("projects", [])

    if not projects:
        logger.warning("No projects found in input file")
        return

    batches = split_batches(projects, args.batch_size)
    generate_task_files(batches, args.output, dry_run=args.dry_run)

    if not args.dry_run:
        logger.info(
            "Total: %d projects in %d batches", len(projects), len(batches),
        )
        logger.info("Batch size: %d", args.batch_size)
        if batches:
            est_tokens = len(batches[0]) * TOKEN_PER_ITEM + PROMPT_OVERHEAD
            logger.info("Estimated tokens per batch: ~%d", est_tokens)
    else:
        logger.info(
            "[DRY-RUN] Total: %d projects in %d batches", len(projects), len(batches),
        )


def run_merge(args: argparse.Namespace) -> None:
    """合并 AI 结果"""
    if not args.results_dir:
        logger.error(
            "--results-dir is required in merge mode. "
            "Usage: python full_pipeline.py --mode merge --input data.json "
            "--output merged.json --results-dir results/"
        )
        sys.exit(1)

    if not os.path.isdir(args.results_dir):
        logger.error("Results directory not found: %s", args.results_dir)
        sys.exit(1)

    if not os.path.isfile(args.input):
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)

    all_results: List[List[Dict[str, Any]]] = []
    batch_stats: List[Dict[str, Any]] = []

    result_files = sorted(
        f for f in os.listdir(args.results_dir) if f.endswith(".json")
    )

    for filename in result_files:
        path = os.path.join(args.results_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            batch = json.load(f)
        if isinstance(batch, list):
            all_results.append(batch)
            batch_stats.append({"file": filename, "items": len(batch), "errors": 0})
        elif isinstance(batch, dict) and "results" in batch:
            all_results.append(batch["results"])
            batch_stats.append({
                "file": filename,
                "items": len(batch["results"]),
                "errors": 0,
            })

    stats = merge_results(all_results, args.input, args.output, dry_run=args.dry_run)

    if not args.dry_run:
        # 统计摘要报告
        logger.info("=" * 60)
        logger.info("  统计摘要报告")
        logger.info("=" * 60)
        logger.info("  批次文件数: %d", len(result_files))
        logger.info("  总结果数: %d", sum(s["items"] for s in batch_stats))
        logger.info("  合并成功: %d/%d", stats["merged"], stats["total"])
        if stats.get("unmatched", 0):
            logger.warning("  未匹配项目: %d", stats["unmatched"])
        if stats.get("orphan", 0):
            logger.warning("  孤儿洞察: %d", stats["orphan"])
        logger.info("=" * 60)


# =============================================================================
# 入口
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI Batch Processor - 将大规模数据拆分为 AI 友好的批次，生成结构化 Prompt，校验并合并结果",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python %(prog)s --input data.json --output tasks/ --mode generate --batch-size 30
  python %(prog)s --input data.json --output merged.json --mode merge --results-dir results/
  python %(prog)s --input data.json --output tasks/ --mode generate --dry-run
        """.strip()
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to input JSON file (scored projects)",
    )
    parser.add_argument(
        "--output", required=True,
        help="Output file or directory path",
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE_DEFAULT,
        help="Items per batch (default: %(default)s)",
    )
    parser.add_argument(
        "--mode", choices=["generate", "merge"], default="generate",
        help="generate: create task files for AI | merge: combine AI results back to main data",
    )
    parser.add_argument(
        "--results-dir",
        help="Directory with AI output files (required for merge mode)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be done without writing any files",
    )
    args = parser.parse_args()

    if args.mode == "generate":
        run_generate(args)
    else:
        run_merge(args)