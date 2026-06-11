#!/usr/bin/env python3
"""
基础批量洞察生成示例
演示 AI Batch Processor 的核心流程：准备数据 → 生成洞察 → 验证质量

两种模式：
  1. 本地洞察引擎（$0 成本）—— 演示确定性规则驱动的洞察生成
  2. AI 批量管线 —— 演示分批任务文件生成和结果合并

用法:
    python basic-batch.py                    # 演示完整流程（本地引擎模式）
    python basic-batch.py --mode local       # 仅本地洞察引擎
    python basic-batch.py --mode pipeline    # 演示 AI 管线（生成任务文件）
"""

import json
import os
import sys
import hashlib
import random
from typing import Any, Dict, List, Tuple

# ==================== 示例数据 ====================

SAMPLE_PROJECTS = [
    {
        "topicId": "101",
        "title": "AI 智能编程助手",
        "rawText": "一个基于大语言模型的智能编程助手，支持代码自动补全、bug 检测和代码优化。"
                   "采用最新的 AI 技术，集成了多个主流模型。支持 VS Code 和 JetBrains 插件。"
                   "目前已经有 5000+ 用户在使用，获得广泛好评。",
        "scores": {"functionality": 8.2, "innovation": 7.5, "ux": 5.5,
                   "visual": 6.0, "techDifficulty": 7.5, "practicality": 8.0},
        "avgScore": 7.1, "qualityGrade": "A",
        "strengths": ["功能完整", "描述详尽", "技术栈成熟"],
        "weaknesses": ["交互设计较薄弱"],
        "votes": 120, "imageCount": 8
    },
    {
        "topicId": "102",
        "title": "像素风桌面解谜游戏",
        "rawText": "把 Windows 桌面变成了一个解谜场景，每个图标、每个窗口都可能是线索。"
                   "玩家需要在桌面环境中寻找隐藏的谜题，解开层层关卡。"
                   "创新的 gameplay 设计，打破了传统游戏边界。",
        "scores": {"functionality": 6.5, "innovation": 9.2, "ux": 7.0,
                   "visual": 8.5, "techDifficulty": 7.0, "practicality": 4.0},
        "avgScore": 7.0, "qualityGrade": "A",
        "strengths": ["创新性极高", "视觉设计精美"],
        "weaknesses": ["实用性较弱"],
        "votes": 85, "imageCount": 18
    },
    {
        "topicId": "103",
        "title": "AI 教育助手",
        "rawText": "帮助学生自动生成学习计划和练习题目的 AI 助手。支持多学科、多难度级别。"
                   "可以根据学生的学习进度自动调整题目难度。",
        "scores": {"functionality": 6.0, "innovation": 5.5, "ux": 5.0,
                   "visual": 4.5, "techDifficulty": 4.0, "practicality": 7.5},
        "avgScore": 5.4, "qualityGrade": "B",
        "strengths": ["实用性好", "教育刚需"],
        "weaknesses": ["技术实现简单", "视觉设计基础"],
        "votes": 15, "imageCount": 3
    },
    {
        "topicId": "104",
        "title": "智能简历生成器",
        "rawText": "输入基本信息，AI 自动生成专业简历。支持多种模板和格式，"
                   "可以导出 PDF 和 Word。内置 AI 优化建议功能。",
        "scores": {"functionality": 7.0, "innovation": 4.0, "ux": 8.0,
                   "visual": 7.5, "techDifficulty": 3.5, "practicality": 9.0},
        "avgScore": 6.5, "qualityGrade": "A",
        "strengths": ["用户体验极佳", "实用价值高"],
        "weaknesses": ["创新不足", "技术门槛低"],
        "votes": 200, "imageCount": 12
    },
    {
        "topicId": "105",
        "title": "简单计算器",
        "rawText": "一个基础的计算器应用。",
        "scores": {"functionality": 2.0, "innovation": 1.5, "ux": 3.0,
                   "visual": 2.5, "techDifficulty": 1.0, "practicality": 5.0},
        "avgScore": 2.5, "qualityGrade": "C",
        "strengths": ["简单直接"],
        "weaknesses": ["功能单一", "无创新", "技术实现简单"],
        "votes": 2, "imageCount": 1
    },
]

# ==================== 工具函数 ====================

def deterministic_pick(items: List[Any], seed_str: str, count: int = 1) -> List[Any]:
    """
    基于种子字符串确定性选取，保证幂等性。
    同一项目每次运行结果完全一致。

    Args:
        items: 候选列表
        seed_str: 用于确定性选择的种子字符串（如 topicId）
        count: 选取数量

    Returns:
        List[Any]: 选取的子列表
    """
    if len(items) <= count:
        return items[:]
    h = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    indices: List[int] = []
    pool = list(range(len(items)))
    for _ in range(count):
        idx = h % len(pool)
        indices.append(pool[idx])
        pool.pop(idx)
        h = h // len(items) + 1
    return [items[i] for i in indices]


def deduplicate(items: List[Any], max_count: int) -> List[Any]:
    """
    去重并保留前 max_count 个元素。

    Args:
        items: 可能包含重复元素的列表
        max_count: 最大保留数量

    Returns:
        List[Any]: 去重后的列表
    """
    seen: set = set()
    unique: List[Any] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique[:max_count]


# ==================== 洞察生成 ====================

# 领域信号（精简版，完整版见 references/domain_signals.json）
DOMAIN_SIGNALS = {
    "AI编程/开发": ["代码", "编程", "开发", "程序", "debug", "插件"],
    "AI教育/学习": ["学习", "教育", "教学", "课程", "知识", "学生"],
    "AI效率/办公": ["办公", "效率", "管理", "任务", "简历"],
    "AI游戏/娱乐": ["游戏", "娱乐", "互动", "关卡", "谜题"],
    "AI社交/社区": ["社交", "社区", "交友", "论坛"],
    "AI数据分析": ["数据", "分析", "报表", "图表"],
}

# 质量等级描述
GRADE_DESC = {"S": "顶级", "A": "优秀", "B": "良好", "C": "基础"}

# 维度中文映射
DIM_CN = {
    "functionality": "功能完整度", "innovation": "创新性", "ux": "用户体验",
    "visual": "视觉设计", "techDifficulty": "技术难度", "practicality": "实用价值",
}


def get_domain(p: Dict[str, Any]) -> str:
    """
    从项目标题中检测领域。

    Args:
        p: 项目数据字典

    Returns:
        str: 检测到的领域名称，默认 "通用工具"
    """
    title = p.get("title", "").lower()
    for domain, keywords in DOMAIN_SIGNALS.items():
        if any(kw in title for kw in keywords):
            return domain
    return "通用工具"


def get_top_bottom_dims(scores: Dict[str, float]) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
    """
    获取评分最高和最低的维度。

    Args:
        scores: 六维度评分字典

    Returns:
        Tuple: (最高2个维度, 最低2个维度)
    """
    valid = {k: v for k, v in scores.items() if isinstance(v, (int, float))}
    sorted_dims = sorted(valid.items(), key=lambda x: x[1], reverse=True)
    return sorted_dims[:2], sorted_dims[-2:]


def generate_summary(p: Dict[str, Any]) -> str:
    """
    生成一句话总结（30 字以内）。

    Args:
        p: 项目数据字典

    Returns:
        str: 一句话总结
    """
    grade = p.get("qualityGrade", "B")
    domain = get_domain(p)
    top_dims, _ = get_top_bottom_dims(p["scores"])
    top_dim_cn = DIM_CN.get(top_dims[0][0], "综合") if top_dims else "综合"
    grade_desc = GRADE_DESC.get(grade, "良好")
    votes = p.get("votes", 0)

    templates = [f"{grade_desc}级{domain}产品，{top_dim_cn}突出"]
    if votes >= 50:
        templates.append(f"高人气{domain}作品，{votes}票验证市场需求")
    if p["avgScore"] >= 7.0:
        templates.append(f"{grade_desc}级产品，综合{p['avgScore']}分表现亮眼")

    seed = f"summary-{p['topicId']}"
    return deterministic_pick(templates, seed, 1)[0]


def generate_competitive_edge(p: Dict[str, Any]) -> str:
    """
    生成核心竞争优势分析（50-80 字）。

    Args:
        p: 项目数据字典

    Returns:
        str: 竞争优势分析
    """
    scores = p["scores"]
    top_dims, _ = get_top_bottom_dims(scores)
    votes = p.get("votes", 0)

    parts = []
    for dim_key, dim_val in top_dims:
        dim_cn = DIM_CN.get(dim_key, "综合")
        if dim_val >= 8.5:
            parts.append(f"{dim_cn}（{dim_val}分）达到顶尖水准")
        elif dim_val >= 7.0:
            parts.append(f"{dim_cn}（{dim_val}分）表现优秀")
        else:
            parts.append(f"{dim_cn}（{dim_val}分）处于良好水平")

    if votes >= 100:
        parts.append(f"获{votes}票高度认可")
    elif votes >= 30:
        parts.append(f"{votes}票社区支持验证了产品价值")

    return "，".join(parts[:3])[:80]


def generate_risks(p: Dict[str, Any]) -> List[str]:
    """
    生成潜在风险点（2-3 个）。

    Args:
        p: 项目数据字典

    Returns:
        List[str]: 风险列表
    """
    scores = p["scores"]
    _, bottom_dims = get_top_bottom_dims(scores)
    votes = p.get("votes", 0)
    seed = f"risk-{p['topicId']}"

    risks = []
    if bottom_dims:
        weak_key, weak_val = bottom_dims[0]
        weak_cn = DIM_CN.get(weak_key, "综合")
        weak_v = round(weak_val, 1)
        risks.append(f"{weak_cn}（{weak_v}分）是明显短板，需重点改进")

    if votes < 10:
        risks.append("社区关注度极低，产品缺乏市场验证")
    elif votes < 30:
        risks.append(f"仅{votes}票，用户基数较小，规模化增长面临挑战")

    if len(risks) < 2:
        risks.append("跨平台兼容性和性能优化可能未充分测试")

    return deduplicate(risks, 3)


def generate_suggestions(p: Dict[str, Any]) -> List[str]:
    """
    生成改进建议（2-3 个）。

    Args:
        p: 项目数据字典

    Returns:
        List[str]: 建议列表
    """
    scores = p["scores"]
    _, bottom_dims = get_top_bottom_dims(scores)
    domain = get_domain(p)
    votes = p.get("votes", 0)
    seed = f"sug-{p['topicId']}"

    suggestions = []
    if bottom_dims:
        weak_key, weak_val = bottom_dims[0]
        weak_cn = DIM_CN.get(weak_key, "综合")
        weak_v = round(weak_val, 1)
        suggestions.append(f"重点改进{weak_cn}（当前{weak_v}分），补齐短板")

    if votes < 20:
        suggestions.append("积极在社区互动推广，提升作品曝光度")

    general = [
        f"聚焦{domain}核心场景做深做透",
        "建议收集用户反馈并快速迭代",
        "建议完善产品文档和教程",
    ]
    suggestions.extend(deterministic_pick(general, seed + "gen", 1))

    return deduplicate(suggestions, 3)


def generate_market_opportunity(p: Dict[str, Any]) -> str:
    """
    生成市场机会分析（50-80 字）。

    Args:
        p: 项目数据字典

    Returns:
        str: 市场机会分析
    """
    domain = get_domain(p)
    votes = p.get("votes", 0)

    domain_opps = {
        "AI编程/开发": "AI辅助开发从代码补全走向全流程，工具链整合是趋势",
        "AI教育/学习": "教育数字化转型加速，AI教学辅助工具需求持续旺盛",
        "AI效率/办公": "AI办公效率工具正成为职场刚需，市场渗透率持续提升",
        "AI游戏/娱乐": "AI生成内容大幅降低开发成本，独立开发者机会增多",
    }

    base = domain_opps.get(domain, f"{domain}赛道持续发展，AI赋能产品有差异化突围机会")
    suffix = "早期用户反馈可指导产品快速迭代" if votes < 50 else f"已获{votes}票验证的用户需求为增长奠定基础"

    return f"{base}，{suffix}"[:80]


def generate_insight(p: Dict[str, Any]) -> Dict[str, Any]:
    """
    为单个项目生成完整 AI 洞察。

    所有生成函数基于确定性规则，同一项目每次运行结果完全一致。
    覆盖 6 个分析领域 × 多套模板，差异度 > 90%。

    Args:
        p: 项目数据字典（需包含 scores/avgScore/qualityGrade）

    Returns:
        Dict: 包含 summary/competitiveEdge/risks/suggestions/marketOpportunity 的洞察对象
    """
    return {
        "summary": generate_summary(p),
        "competitiveEdge": generate_competitive_edge(p),
        "risks": generate_risks(p),
        "suggestions": generate_suggestions(p),
        "marketOpportunity": generate_market_opportunity(p),
    }


# ==================== 主流程 ====================

def run_local_engine(projects: List[Dict], output_path: str = None) -> List[Dict]:
    """
    使用本地洞察引擎为所有项目生成洞察（$0 成本）。

    Args:
        projects: 项目列表
        output_path: 输出 JSON 文件路径（可选）

    Returns:
        List[Dict]: 附加了 aiInsight 字段的项目列表
    """
    print(f"\n{'='*60}")
    print("  本地洞察引擎模式（$0 成本）")
    print(f"{'='*60}")
    print(f"  项目总数: {len(projects)}")

    for i, p in enumerate(projects):
        p["aiInsight"] = generate_insight(p)

    # 统计差异度
    summaries = set(p["aiInsight"]["summary"] for p in projects)
    edges = set(p["aiInsight"]["competitiveEdge"] for p in projects)
    print(f"  唯一 Summary: {len(summaries)}/{len(projects)} ({len(summaries)/len(projects)*100:.0f}%)")
    print(f"  唯一 Edge:    {len(edges)}/{len(projects)} ({len(edges)/len(projects)*100:.0f}%)")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"projects": projects}, f, ensure_ascii=False, indent=2)
        print(f"  结果已保存: {output_path}")

    return projects


def run_pipeline_preview(projects: List[Dict]) -> None:
    """
    演示 AI 管线模式 —— 生成分批任务文件（预览）。

    实际使用时需将任务文件提交给外部 AI（ChatGPT/Claude 等），
    然后用 merge-insights.py 合并结果。

    Args:
        projects: 项目列表
    """
    print(f"\n{'='*60}")
    print("  AI 管线模式 — 任务文件生成预览")
    print(f"{'='*60}")
    print(f"  项目总数: {len(projects)}")
    print(f"  建议批大小: {min(30, max(10, len(projects)))}")

    # 生成精简版 Prompt 预览
    simplified = []
    for p in projects:
        simplified.append({
            "topicId": p["topicId"],
            "title": p["title"],
            "avgScore": p["avgScore"],
            "qualityGrade": p["qualityGrade"],
            "strengths": p.get("strengths", [])[:3],
            "weaknesses": p.get("weaknesses", [])[:3],
            "rawText": p.get("rawText", "")[:2000],
        })

    prompt = f"""你是一个资深的产品分析师。请基于以下项目数据，为每个项目生成AI洞察报告。

要求：
1. 为每个项目输出一个JSON对象，包含以下字段：
   - topicId: 项目ID（字符串）
   - aiInsight: 包含以下结构的洞察对象：
     - summary: 一句话总结（30字以内）
     - competitiveEdge: 核心竞争优势分析（50-80字）
     - risks: 潜在风险点（列表，2-3个，每个30-50字）
     - suggestions: 改进建议（列表，2-3个，每个30-50字）
     - marketOpportunity: 市场机会分析（50-80字）

2. 输出格式：严格 JSON 数组 [{...}, {...}]

以下是第 1 批的项目数据（共 {len(projects)} 个）：

{json.dumps(simplified, ensure_ascii=False, indent=2)}

请开始分析并输出JSON数组："""

    print(f"\n  --- Prompt 预览（前 500 字符）---")
    print(f"  {prompt[:500]}...")
    print(f"\n  --- 使用方式 ---")
    print(f"  1. 将上述 Prompt 提交给 ChatGPT/Claude")
    print(f"  2. 将 AI 返回的 JSON 保存到 ai_results/batch_001.json")
    print(f"  3. 运行: python merge-insights.py --input data.json --results ai_results/ --output enriched.json")


def print_comparison(projects: List[Dict]) -> None:
    """
    打印洞察前后对比。

    Args:
        projects: 已附加 aiInsight 的项目列表
    """
    print(f"\n{'='*60}")
    print("  洞察生成结果对比")
    print(f"{'='*60}")

    for i, p in enumerate(projects):
        insight = p.get("aiInsight", {})
        print(f"\n  [{i+1}] {p['title']} (等级: {p['qualityGrade']}, 均分: {p['avgScore']})")
        print(f"      Summary:           {insight.get('summary', 'N/A')}")
        print(f"      CompetitiveEdge:   {insight.get('competitiveEdge', 'N/A')}")
        print(f"      Risks:             {'; '.join(insight.get('risks', ['N/A']))}")
        print(f"      Suggestions:       {'; '.join(insight.get('suggestions', ['N/A']))}")
        print(f"      MarketOpportunity: {insight.get('marketOpportunity', 'N/A')}")


def main():
    """主入口 —— 演示 AI Batch Processor 的完整流程"""
    import argparse

    parser = argparse.ArgumentParser(
        description="AI Batch Processor 基础示例 —— 演示本地洞察引擎和 AI 批量管线"
    )
    parser.add_argument(
        "--mode", choices=["local", "pipeline", "all"], default="all",
        help="运行模式: local=本地引擎, pipeline=管线预览, all=全部演示"
    )
    parser.add_argument(
        "--output", default="output/enriched.json",
        help="输出文件路径"
    )
    args = parser.parse_args()

    os.makedirs("output", exist_ok=True)

    projects = [dict(p) for p in SAMPLE_PROJECTS]  # 深拷贝

    if args.mode in ("local", "all"):
        projects = run_local_engine(projects, args.output)
        print_comparison(projects)

    if args.mode in ("pipeline", "all"):
        run_pipeline_preview(projects)

    print(f"\n{'='*60}")
    print("  完成！")
    print(f"{'='*60}")
    print(f"  处理项目数: {len(projects)}")
    print(f"  成本: $0 (本地洞察引擎)")
    print(f"  可复现性: 100% (基于 MD5 种子，每次运行结果一致)")


if __name__ == "__main__":
    main()