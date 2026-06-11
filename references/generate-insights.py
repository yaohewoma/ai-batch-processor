#!/usr/bin/env python3
"""
本地 AI 洞察引擎 —— 基于结构化数据 + 项目特征生成高差异化洞察
替代外部 LLM API 调用，使用确定性规则和领域知识生成：
  - summary: 一句话总结（30 字以内）
  - competitiveEdge: 核心竞争优势分析（50-80 字）
  - risks: 潜在风险点（2-3 个，每个 30-50 字）
  - suggestions: 改进建议（2-3 个，每个 30-50 字）
  - marketOpportunity: 市场机会分析（50-80 字）

用法:
    python generate_insights.py --input data.json --output data_with_insights.json
    python generate_insights.py --input data.json --dry-run    # 预览前10条
    python generate_insights.py --input data.json --check      # 验证已有洞察质量

核心设计：
  - 确定性生成：同一项目每次运行结果一致（基于 MD5 种子）
  - 高差异化：34 种领域 × 6 个维度 × 多套模板 × 分数驱动
  - 零 API 调用：全部基于规则和模板，处理 3000+ 条仅需几秒
"""
import json
import os
import re
import argparse
import hashlib
import sys
import logging
from collections import Counter
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

MAX_KEYWORDS = 5              # 标题关键词提取上限
NAME_MIN_LEN = 2              # 项目名称最小长度
NAME_MAX_LEN = 15             # 项目名称最大长度
TEXT_TRUNCATE = 80            # competitive_edge / market_opportunity 文本截断长度
RISK_COUNT = 3                # 风险条目上限
SUGGESTION_COUNT = 3          # 建议条目上限
DOMAIN_CONTEXT_LIMIT = 3      # 领域检测最大返回数
DEFAULT_DOMAIN = "通用工具"   # 未检测到领域时的默认值
TOP_DIMS_N = 2                # 获取评分最高维度数
BOTTOM_DIMS_N = 2             # 获取评分最低维度数
DRY_RUN_PREVIEW = 10          # dry-run 模式下预览条数

# 停用词表
STOP_WORDS = {
    "的", "了", "在", "是", "和", "与", "用", "我", "你", "他", "她", "它",
    "一个", "这个", "那个", "什么", "怎么", "如何", "可以", "能够", "就是",
    "code", "with", "solo", "hello", "ai", "more", "than", "coding",
    "so", "to", "for", "the", "a", "an", "and", "or", "【", "】",
}

# 质量等级描述
GRADE_DESC = {"S": "顶级", "A": "优秀", "B": "良好", "C": "基础"}


# =============================================================================
# 配置映射
# =============================================================================

DIM_CN: Dict[str, str] = {
    "functionality": "功能完整度", "innovation": "创新性", "ux": "用户体验",
    "visual": "视觉设计", "techDifficulty": "技术难度", "practicality": "实用价值",
}

TYPE_CN: Dict[str, str] = {
    "工具": "效率工具", "内容": "内容创作", "教育": "教育学习",
    "游戏": "互动娱乐", "社交": "社交平台", "商业": "商业应用", "公益": "公益服务",
    "健康": "健康医疗", "金融": "金融服务", "设计": "创意设计",
}

TRACK_CN: Dict[str, str] = {
    "Frontend": "前端开发", "Backend": "后端服务", "Game": "游戏开发",
    "Data": "数据分析", "DevOps": "运维部署", "Security": "安全领域",
}

TECH_CN: Dict[str, str] = {
    "前端": "前端技术", "后端": "后端服务", "数据库": "数据存储",
    "AI/ML": "机器学习", "LLM应用": "大模型应用", "移动端": "移动开发",
    "Python": "Python生态", "WebAssembly": "WebAssembly", "浏览器扩展": "浏览器插件",
    "区块链": "区块链", "Rust": "Rust", "Go": "Go语言", "Java": "Java",
    "C/C++": "C/C++", "游戏引擎": "游戏引擎", "DevOps": "DevOps",
    "数据可视化": "数据可视化", "AI教育": "AI教育",
}

TARGET_USER_CN: Dict[str, str] = {
    "普通用户": "C端用户", "开发者": "开发者群体", "学生/教育者": "教育从业者",
    "企业用户": "企业客户", "公益受众": "公益受益群体",
}


# =============================================================================
# 领域信号加载
# =============================================================================

def _load_domain_signals() -> Dict[str, List[str]]:
    """从配置文件加载领域信号映射，若文件不存在则使用内置默认值"""
    config_path = os.path.join(os.path.dirname(__file__), "domain_signals.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("domains", {})
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(
            "无法加载领域配置文件 %s: %s，使用内置默认值", config_path, e,
        )
        return {
            "AI对话/聊天": ["对话", "聊天", "chat", "聊天机器人", "智能助手", "ai助手"],
            "AI写作/创作": ["写作", "文章", "文案", "创作", "写作工具", "内容生成"],
            "AI图像/设计": ["图像", "图片", "设计", "绘画", "美术", "画", "视觉"],
            "AI教育/学习": ["学习", "教育", "教学", "课程", "考试", "知识", "培训"],
            "AI医疗/健康": ["医疗", "健康", "看病", "就医", "诊断", "药物", "疾病"],
            "AI效率/办公": ["办公", "效率", "管理", "日程", "任务", "笔记", "记录"],
            "AI电商/营销": ["电商", "购物", "营销", "销售", "商品", "店铺", "推广"],
            "AI游戏/娱乐": ["游戏", "娱乐", "互动", "休闲", "益智", "冒险"],
            "AI社交/社区": ["社交", "社区", "交友", "分享", "圈子", "论坛"],
            "AI数据分析": ["数据", "分析", "可视化", "报表", "图表", "dashboard"],
            "AI编程/开发": ["代码", "编程", "开发", "程序", "调试", "ide", "开发者"],
            "AI翻译/语言": ["翻译", "语言", "多语言", "跨语言", "字幕"],
            "AI音乐/音频": ["音乐", "音频", "声音", "语音", "歌曲", "播客"],
            "AI视频/动画": ["视频", "动画", "短视频", "剪辑", "特效"],
            "AI公益/助老": ["公益", "助老", "老年人", "残障", "无障碍", "志愿服务"],
            "AI求职/职场": ["求职", "面试", "简历", "职场", "就业", "招聘"],
        }


DOMAIN_SIGNALS: Dict[str, List[str]] = _load_domain_signals()


# =============================================================================
# 进度条
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
# 工具函数
# =============================================================================

def deterministic_pick(
    items: List[Any],
    seed_str: str,
    count: int = 1,
) -> List[Any]:
    """基于种子字符串确定性选取，保证幂等性"""
    h = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    if len(items) <= count:
        return items[:]
    indices: List[int] = []
    pool = list(range(len(items)))
    for _ in range(count):
        idx = h % len(pool)
        indices.append(pool[idx])
        pool.pop(idx)
        h = h // len(items) + 1
    return [items[i] for i in indices]


def deduplicate(items: List[Any], max_count: int) -> List[Any]:
    """去重并保留前 max_count 个元素"""
    seen: set = set()
    unique: List[Any] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique[:max_count]


def get_top_dims(
    scores: Dict[str, Any],
    n: int = TOP_DIMS_N,
) -> List[Tuple[str, float]]:
    """获取评分最高的 N 个维度（排除内部字段）"""
    valid = {
        k: v for k, v in scores.items()
        if not k.startswith("_") and isinstance(v, (int, float))
    }
    return sorted(valid.items(), key=lambda x: x[1], reverse=True)[:n]


def get_bottom_dims(
    scores: Dict[str, Any],
    n: int = BOTTOM_DIMS_N,
) -> List[Tuple[str, float]]:
    """获取评分最低的 N 个维度（排除内部字段）"""
    valid = {
        k: v for k, v in scores.items()
        if not k.startswith("_") and isinstance(v, (int, float))
    }
    return sorted(valid.items(), key=lambda x: x[1])[:n]


def extract_keywords(title: str) -> List[str]:
    """从标题中提取有意义的关键词（去停用词）"""
    clean = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', title)
    words = [
        w.strip() for w in clean.split()
        if w.strip() and len(w.strip()) >= 2
    ]
    return [w for w in words if w.lower() not in STOP_WORDS][:MAX_KEYWORDS]


def get_domain_context(p: Dict[str, Any]) -> List[str]:
    """从项目数据中提取领域上下文关键词（34 种领域覆盖）"""
    title = p.get("title", "")
    excerpt = p.get("excerpt", "") or ""
    ai_liner = p.get("aiOneLiner", "") or ""
    combined = (title + " " + excerpt + " " + ai_liner).lower()

    detected = []
    for domain, keywords in DOMAIN_SIGNALS.items():
        if any(kw in combined for kw in keywords):
            detected.append(domain)
    return detected[:DOMAIN_CONTEXT_LIMIT] if detected else [DEFAULT_DOMAIN]


# =============================================================================
# 输入数据校验
# =============================================================================

def validate_project(p: Dict[str, Any], index: int) -> List[str]:
    """校验单个项目数据的必要字段，返回错误列表"""
    errors: List[str] = []
    tid = p.get("topicId", p.get("id", ""))
    if not tid:
        errors.append(f"Item {index}: missing topicId")
    if "scores" not in p:
        errors.append(f"Item {index} ({tid}): missing scores")
    if "avgScore" not in p:
        errors.append(f"Item {index} ({tid}): missing avgScore")
    return errors


def validate_input_data(projects: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """校验输入数据，返回 (有效项目列表, 错误列表)"""
    all_errors: List[str] = []
    valid: List[Dict[str, Any]] = []
    for i, p in enumerate(projects):
        errs = validate_project(p, i)
        if errs:
            all_errors.extend(errs)
        else:
            valid.append(p)
    if all_errors:
        logger.warning("输入数据校验发现 %d 个错误", len(all_errors))
        for e in all_errors[:5]:
            logger.warning("  %s", e)
    return valid, all_errors


# =============================================================================
# 洞察生成器
# =============================================================================

def generate_summary(p: Dict[str, Any]) -> str:
    """生成一句话总结（30 字以内）"""
    name = p.get("productName", "") or ""
    grade = p.get("qualityGrade", "B")
    ptype = p.get("classification", {}).get("productType", "工具")
    votes = p.get("votes", 0)
    scores = p.get("scores", {})
    avg = p.get("avgScore", 5.0)
    top_dims = get_top_dims(scores, 1)
    top_dim_cn = DIM_CN.get(top_dims[0][0], "综合") if top_dims else "综合"
    top_val = round(float(top_dims[0][1]), 1) if top_dims else 5.0
    domains = get_domain_context(p)
    primary_domain = domains[0]
    type_cn = TYPE_CN.get(ptype, ptype)
    grade_desc = GRADE_DESC.get(grade, "良好")
    seed = f"summary-{p['topicId']}"

    templates = []
    if name and NAME_MIN_LEN <= len(name) <= NAME_MAX_LEN:
        templates.append(f"「{name}」{primary_domain}产品，{top_dim_cn}突出")
        templates.append(f"「{name}」聚焦{primary_domain}，{grade_desc}级{type_cn}")
    if votes >= 50:
        templates.append(f"高人气{primary_domain}作品，{votes}票验证市场需求")
    if avg >= 7.0:
        templates.append(f"{grade_desc}级{primary_domain}产品，综合{avg}分表现亮眼")
    if votes >= 10:
        templates.append(f"{primary_domain}作品获{votes}票，{top_dim_cn}是核心卖点")
    if not templates:
        templates.append(
            f"{grade_desc}级{type_cn}，{primary_domain}方向，{top_dim_cn}有潜力",
        )
    return deterministic_pick(templates, seed, 1)[0]


def generate_competitive_edge(p: Dict[str, Any]) -> str:
    """生成核心竞争优势分析（50-80 字）"""
    scores = p.get("scores", {})
    top_dims = get_top_dims(scores, 2)
    votes = p.get("votes", 0)
    avg = p.get("avgScore", 5.0)
    tech_stack = p.get("classification", {}).get("techStack", [])
    domains = get_domain_context(p)
    target_user = p.get("classification", {}).get("targetUser", "普通用户")
    seed = f"edge-{p['topicId']}"

    parts: List[str] = []

    # 哨兵值处理：确保 d1, d2 不是同一引用
    if len(top_dims) >= 2:
        d1, d2 = top_dims[0], top_dims[1]
    elif len(top_dims) == 1:
        d1 = top_dims[0]
        d2 = (top_dims[0][0], top_dims[0][1])  # 安全复制，避免同引用
    else:
        d1 = ("综合", 5.0)
        d2 = ("综合", 5.0)

    dim1_cn = DIM_CN.get(d1[0], "综合")
    dim2_cn = DIM_CN.get(d2[0], "综合")
    d1v = round(float(d1[1]), 1)
    d2v = round(float(d2[1]), 1)

    if d1v >= 8.5:
        parts.append(f"{dim1_cn}（{d1v}分）达到顶尖水准")
    elif d1v >= 7.5:
        parts.append(f"{dim1_cn}（{d1v}分）表现优秀")
    elif d1v >= 6.5:
        parts.append(f"{dim1_cn}（{d1v}分）处于良好水平")
    else:
        parts.append(f"{dim1_cn}（{d1v}分）为基础优势")

    if d2v >= 7.0:
        parts.append(f"{dim2_cn}（{d2v}分）同样出色")
    if votes >= 100:
        parts.append(f"获{votes}票高度认可")
    elif votes >= 30:
        parts.append(f"{votes}票社区支持验证了产品价值")
    if len(tech_stack) >= 4:
        tech_names = "、".join([TECH_CN.get(t, t) for t in tech_stack[:3]])
        parts.append(f"技术栈涵盖{tech_names}等，架构有深度")
    target_cn = TARGET_USER_CN.get(target_user, target_user)
    if target_user != "普通用户":
        parts.append(f"精准定位{target_cn}")

    result = "，".join(parts[:4])
    return result[:TEXT_TRUNCATE]


def generate_risks(p: Dict[str, Any]) -> List[str]:
    """生成潜在风险点（2-3 个）"""
    scores = p.get("scores", {})
    votes = p.get("votes", 0)
    views = p.get("views", 0)
    avg = p.get("avgScore", 5.0)
    bottom_dims = get_bottom_dims(scores, 2)
    domains = get_domain_context(p)
    seed = f"risk-{p['topicId']}"

    risks: List[str] = []
    weak_key, weak_val = bottom_dims[0] if bottom_dims else ("综合", 5.0)
    weak_cn = DIM_CN.get(weak_key, "综合")
    weak_v = round(float(weak_val), 1)

    dim_risks = {
        "functionality": [
            f"功能深度不足（{weak_v}分），复杂需求下可能力不从心",
            "核心场景覆盖可能不完整，建议补齐关键功能模块",
        ],
        "innovation": [
            f"创新性得分{weak_v}，需警惕同质化竞争",
            "产品概念较常规，差异化不足",
        ],
        "ux": [
            f"用户体验（{weak_v}分）有待优化，新用户上手可能有门槛",
        ],
        "visual": [
            f"视觉设计（{weak_v}分）较基础，界面吸引力有限",
        ],
        "techDifficulty": [
            f"技术实现（{weak_v}分）相对简单，扩展性可能受限",
        ],
        "practicality": [
            f"实用性（{weak_v}分），落地场景需进一步验证",
        ],
    }

    weak_templates = dim_risks.get(weak_key, [f"{weak_cn}（{weak_v}分）是明显短板"])
    risks.extend(deterministic_pick(weak_templates, seed + "dim1", 1))

    if votes < 5:
        engagement = [
            "社区关注度极低，产品可能缺乏市场验证",
            "几乎无用户投票，冷启动是当前最大挑战",
        ]
        risks.extend(deterministic_pick(engagement, seed + "eng", 1))
    elif votes < 15:
        risks.append(f"仅{votes}票，用户基数较小，规模化增长面临挑战")

    if len(risks) < 2:
        fallback = [
            f"{domains[0]}赛道竞争激烈，需持续关注竞品动态",
            "跨平台兼容性和性能优化可能未充分测试",
        ]
        risks.extend(deterministic_pick(fallback, seed + "fb", 1))

    return deduplicate(risks, RISK_COUNT)


def generate_suggestions(p: Dict[str, Any]) -> List[str]:
    """生成改进建议（2-3 个）"""
    scores = p.get("scores", {})
    votes = p.get("votes", 0)
    bottom_dims = get_bottom_dims(scores, 2)
    domains = get_domain_context(p)
    tech_stack = p.get("classification", {}).get("techStack", [])
    seed = f"sug-{p['topicId']}"

    suggestions: List[str] = []
    weak_key = bottom_dims[0][0] if bottom_dims else "综合"
    weak_cn = DIM_CN.get(weak_key, "综合")
    weak_v = round(float(bottom_dims[0][1]), 1) if bottom_dims else 5.0

    dim_sugs = {
        "functionality": f"优先补齐{weak_cn}（当前{weak_v}分），完善核心功能闭环",
        "innovation": f"建议深挖{domains[0]}垂直场景，打造差异化创新",
        "ux": f"优化{weak_cn}（当前{weak_v}分），降低新用户上手成本",
        "visual": f"引入设计系统统一视觉语言，提升{weak_cn}吸引力",
        "techDifficulty": f"提升{weak_cn}（{weak_v}分），引入更成熟的技术框架",
        "practicality": f"明确{weak_cn}的落地路径，设计可持续的运营模式",
    }
    suggestions.append(
        dim_sugs.get(weak_key, f"重点改进{weak_cn}（当前{weak_v}分）"),
    )

    if votes < 20:
        vote_sugs = [
            "积极在社区互动推广，提升作品曝光度",
            "制作演示视频或GIF更直观地展示产品价值",
        ]
        suggestions.extend(deterministic_pick(vote_sugs, seed + "vote", 1))

    general_sugs = [
        "建议收集用户反馈并快速迭代",
        f"聚焦{domains[0]}核心场景做深做透",
        "建议完善产品文档和教程",
    ]
    suggestions.extend(deterministic_pick(general_sugs, seed + "gen", 1))

    return deduplicate(suggestions, SUGGESTION_COUNT)


def generate_market_opportunity(p: Dict[str, Any]) -> str:
    """生成市场机会分析（50-80 字）"""
    votes = p.get("votes", 0)
    avg = p.get("avgScore", 5.0)
    domains = get_domain_context(p)
    target_user = p.get("classification", {}).get("targetUser", "普通用户")
    seed = f"opp-{p['topicId']}"

    domain_opps = {
        "AI对话/聊天": "AI对话产品正从工具走向伙伴，垂直场景的对话助手是下一个增长点",
        "AI写作/创作": "AIGC内容创作工具市场快速扩张，差异化定位和垂直深耕是突围关键",
        "AI图像/设计": "AI视觉创作工具正在重塑设计行业，先发优势明显",
        "AI教育/学习": "教育数字化转型加速，AI教学辅助工具的需求持续旺盛",
        "AI医疗/健康": "AI医疗健康赛道受政策支持，智能问诊工具有巨大社会价值",
        "AI效率/办公": "AI办公效率工具正成为职场刚需，市场渗透率持续提升",
        "AI游戏/娱乐": "AI生成内容大幅降低开发成本，独立开发者机会增多",
        "AI数据分析": "数据驱动决策已成共识，AI数据分析工具有持续增长的企业需求",
        "AI编程/开发": "AI辅助开发从代码补全走向全流程，工具链整合是趋势",
        "AI公益/助老": "科技公益受政策扶持，银发经济和无障碍市场空间广阔",
        "AI求职/职场": "就业市场竞争激烈，AI求职工具有明确的付费意愿和高频使用场景",
    }

    base = domain_opps.get(
        domains[0],
        f"{domains[0]}赛道持续发展，AI赋能的产品有差异化突围机会",
    )

    suffix_pool: List[str] = []
    if votes >= 50:
        suffix_pool.append(
            f"已获{votes}票验证的用户需求为后续增长奠定基础",
        )
    elif votes >= 10:
        suffix_pool.append("早期用户反馈可指导产品快速迭代和方向调整")
    else:
        suffix_pool.append("抢占用户心智的关键窗口期，需加速产品打磨")

    target_cn = TARGET_USER_CN.get(target_user, target_user)
    if target_user != "普通用户":
        suffix_pool.append(
            f"精准服务{target_cn}的垂直化策略有助于建立竞争壁垒",
        )

    if avg >= 7.0:
        suffix_pool.append("高质量产品在口碑传播和用户留存中更具优势")

    suffix = deterministic_pick(suffix_pool, seed + "suf", 1)[0]
    result = f"{base}，{suffix}"
    return result[:TEXT_TRUNCATE]


def generate_insight(p: Dict[str, Any]) -> Dict[str, Any]:
    """为单个项目生成完整洞察"""
    return {
        "summary": generate_summary(p),
        "competitiveEdge": generate_competitive_edge(p),
        "risks": generate_risks(p),
        "suggestions": generate_suggestions(p),
        "marketOpportunity": generate_market_opportunity(p),
    }


# =============================================================================
# 主流程
# =============================================================================

def run_generate(
    input_path: str,
    output_path: str,
    dry_run: bool = False,
) -> None:
    """为所有项目生成洞察"""
    if not os.path.isfile(input_path):
        logger.error("Input file not found: %s", input_path)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    projects = data.get("projects", data if isinstance(data, list) else [])

    if not projects:
        logger.warning("No projects found in input data")
        return

    logger.info("Total projects: %d", len(projects))

    # 输入数据校验
    valid_projects, validation_errors = validate_input_data(projects)
    if validation_errors:
        logger.warning(
            "校验发现 %d 个错误，%d 个有效项目将继续处理",
            len(validation_errors), len(valid_projects),
        )

    for i, p in enumerate(valid_projects):
        p["aiInsight"] = generate_insight(p)
        if dry_run and i < DRY_RUN_PREVIEW:
            insight = p["aiInsight"]
            logger.info("")
            logger.info("[%d] %s", i + 1, p.get("title", "")[:60])
            logger.info("  summary: %s", insight["summary"])
            logger.info("  competitiveEdge: %s", insight["competitiveEdge"])
            logger.info("  risks: %s", "; ".join(insight["risks"]))
            logger.info("  suggestions: %s", "; ".join(insight["suggestions"]))
            logger.info("  marketOpportunity: %s", insight["marketOpportunity"])
        _progress_bar(i + 1, len(valid_projects), "Generating insights")

    if not dry_run:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 差异化统计
        summaries: set = set()
        edges: set = set()
        for p in valid_projects:
            insight = p.get("aiInsight", {})
            summaries.add(insight.get("summary", ""))
            edges.add(insight.get("competitiveEdge", ""))

        logger.info("")
        logger.info("Done: %d projects", len(valid_projects))
        logger.info(
            "  Unique summaries: %d (%.1f%%)",
            len(summaries),
            len(summaries) / len(valid_projects) * 100 if valid_projects else 0,
        )
        logger.info(
            "  Unique edges: %d (%.1f%%)",
            len(edges),
            len(edges) / len(valid_projects) * 100 if valid_projects else 0,
        )


def run_check(input_path: str) -> None:
    """验证已有洞察质量"""
    if not os.path.isfile(input_path):
        logger.error("Input file not found: %s", input_path)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    projects = data.get("projects", data if isinstance(data, list) else [])

    if not projects:
        logger.warning("No projects found in input data")
        return

    has_insight = sum(1 for p in projects if p.get("aiInsight"))
    logger.info(
        "With insights: %d/%d (%.1f%%)",
        has_insight, len(projects),
        has_insight / len(projects) * 100 if projects else 0,
    )

    summaries = set(
        p.get("aiInsight", {}).get("summary", "")
        for p in projects if p.get("aiInsight")
    )
    edges = set(
        p.get("aiInsight", {}).get("competitiveEdge", "")
        for p in projects if p.get("aiInsight")
    )
    logger.info(
        "Unique summaries: %d (%.1f%%)",
        len(summaries),
        len(summaries) / len(projects) * 100 if projects else 0,
    )
    logger.info(
        "Unique edges: %d (%.1f%%)",
        len(edges),
        len(edges) / len(projects) * 100 if projects else 0,
    )


def main() -> None:
    """主入口"""
    parser = argparse.ArgumentParser(
        description="AI Batch Processor / Generate Insights - 基于确定性规则生成高差异化 AI 洞察，零 API 调用",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python %(prog)s --input data.json --output enriched.json
  python %(prog)s --input data.json --dry-run
  python %(prog)s --input data.json --check
        """.strip()
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to input JSON file (scored projects)",
    )
    parser.add_argument(
        "--output", default="data_with_insights.json",
        help="Path to output JSON file (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview first 10 projects without writing to file",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Verify existing insights uniqueness and quality",
    )
    args = parser.parse_args()

    if args.check:
        run_check(args.input)
    else:
        run_generate(args.input, args.output, args.dry_run)


if __name__ == "__main__":
    main()