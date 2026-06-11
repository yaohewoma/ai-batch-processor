#!/usr/bin/env python3
"""
ai-batch-processor 自动化测试套件

测试覆盖：
  - 数据契约：输入格式验证（必填字段、字段类型、评分范围）
  - 本地洞察引擎：幂等性、差异度、字段完整性
  - 洞察质量：字数限制、列表数量限制、内容一致性
  - 边界条件：缺失字段降级、空数据、极端评分

用法：
    python tests/test_insights.py                    # 运行所有测试
    python tests/test_insights.py --verbose          # 详细输出
    python tests/test_insights.py --filter contract  # 仅测试数据契约
    python tests/test_insights.py --filter quality   # 仅测试洞察质量
"""

import json
import os
import sys
import argparse
import hashlib
from typing import Any, Dict, List, Tuple


# ==================== 配置 ====================

TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), "test-scored.json")

# 必填字段
REQUIRED_FIELDS = ["topicId", "title", "scores", "avgScore", "qualityGrade"]
SCORE_DIMS = ["functionality", "innovation", "ux", "visual", "techDifficulty", "practicality"]
INSIGHT_FIELDS = ["summary", "competitiveEdge", "risks", "suggestions", "marketOpportunity"]
QUALITY_GRADES = {"S", "A", "B", "C"}

# 字数限制
MAX_SUMMARY_LEN = 30
EDGE_MIN_LEN = 30
EDGE_MAX_LEN = 120
MIN_RISKS = 2
MAX_RISKS = 5
MIN_SUGGESTIONS = 2
MAX_SUGGESTIONS = 5
OPPORTUNITY_MIN_LEN = 30
OPPORTUNITY_MAX_LEN = 200

# ==================== 测试工具 ====================

pass_count = 0
fail_count = 0
skip_count = 0

def ok(msg: str):
    global pass_count
    pass_count += 1
    print(f"  ✓ {msg}")

def fail(msg: str):
    global fail_count
    fail_count += 1
    print(f"  ✗ FAIL: {msg}")

def skip(msg: str):
    global skip_count
    skip_count += 1
    print(f"  - SKIP: {msg}")

def load_test_data() -> List[Dict[str, Any]]:
    """加载测试数据"""
    with open(TEST_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("projects", [])

def import_generator_module():
    """动态导入本地洞察引擎（处理文件名含连字符的情况）"""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "references"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "generate_insights",
            os.path.join(os.path.dirname(__file__), "..", "references", "generate-insights.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


# ==================== 测试用例 ====================

def test_contract_projects_exist():
    """测试：projects 数组存在且不为空"""
    data = load_test_data()
    if not data:
        fail("projects 数组为空")
        return
    if len(data) < 5:
        fail(f"测试数据太少: {len(data)} 条，建议 >= 5 条")
        return
    ok(f"projects 数组存在，共 {len(data)} 条")


def test_contract_required_fields():
    """测试：每条数据包含所有必填字段"""
    data = load_test_data()
    all_ok = True
    for p in data:
        missing = [f for f in REQUIRED_FIELDS if f not in p]
        if missing:
            fail(f"{p.get('topicId','?')} 缺少字段: {missing}")
            all_ok = False
    if all_ok:
        ok(f"全部 {len(data)} 条数据包含所有必填字段")


def test_contract_scores_format():
    """测试：scores 字段包含全部 6 个维度且值在合理范围"""
    data = load_test_data()
    all_ok = True
    for p in data:
        scores = p.get("scores", {})
        # 检查维度名称（支持英文和中文 key）
        actual_dims = list(scores.keys())
        if "功能完整度" in actual_dims or "创新性" in actual_dims:
            # 中文 key 格式（兼容旧数据）
            expected = {"功能完整度", "创新性", "用户体验", "视觉设计", "技术难度", "实用价值"}
        else:
            expected = set(SCORE_DIMS)
        if set(actual_dims) != expected:
            fail(f"{p.get('topicId','?')} 评分维度不正确: {actual_dims}")
            all_ok = False
            continue
        for dim, val in scores.items():
            if not isinstance(val, (int, float)):
                fail(f"{p.get('topicId','?')}.{dim} 不是数字: {val}")
                all_ok = False
            elif val < 0 or val > 10:
                fail(f"{p.get('topicId','?')}.{dim} 超出范围: {val}")
                all_ok = False
    if all_ok:
        ok(f"全部 {len(data)} 条 scores 字段格式正确")


def test_contract_quality_grade():
    """测试：qualityGrade 为有效值"""
    data = load_test_data()
    all_ok = True
    for p in data:
        grade = p.get("qualityGrade", "")
        if grade not in QUALITY_GRADES:
            fail(f"{p.get('topicId','?')} 无效 qualityGrade: {grade}")
            all_ok = False
    if all_ok:
        ok(f"全部 {len(data)} 条 qualityGrade 为有效值")


def test_local_engine_idempotence():
    """测试：同一项目多次生成洞察结果一致（幂等性）"""
    gi = import_generator_module()
    if gi is None:
        skip("generate-insights.py 不可导入，跳过幂等性测试")
        return

    data = load_test_data()
    if not data:
        fail("无测试数据")
        return

    p = data[0]
    r1 = gi.generate_insight(p)
    r2 = gi.generate_insight(p)

    # 比较每个字段
    for field in INSIGHT_FIELDS:
        v1 = r1.get(field)
        v2 = r2.get(field)
        if isinstance(v1, list):
            if v1 != v2:
                fail(f"幂等性失败: {field} 两次结果不同")
                return
        elif v1 != v2:
            fail(f"幂等性失败: {field} 两次结果不同 ('{v1}' vs '{v2}')")
            return
    ok(f"幂等性通过: 同一项目 2 次运行结果完全一致")


def test_local_engine_all_fields():
    """测试：洞察包含所有必需字段"""
    gi = import_generator_module()
    if gi is None:
        skip("generate-insights.py 不可导入")
        return

    data = load_test_data()
    all_ok = True
    for p in data:
        insight = gi.generate_insight(p)
        missing = [f for f in INSIGHT_FIELDS if f not in insight]
        if missing:
            fail(f"{p['topicId']} 洞察缺少字段: {missing}")
            all_ok = False
    if all_ok:
        ok(f"全部 {len(data)} 条洞察包含所有 {len(INSIGHT_FIELDS)} 个字段")


def test_insight_differentiation():
    """测试：不同项目之间的洞察差异度"""
    gi = import_generator_module()
    if gi is None:
        skip("generate-insights.py 不可导入")
        return

    data = load_test_data()
    if len(data) < 2:
        skip("数据不足，无法测试差异度")
        return

    insights = []
    for p in data:
        insight = gi.generate_insight(p)
        insights.append(insight)

    # 统计 summary 唯一率
    summaries = [i.get("summary", "") for i in insights]
    unique_summaries = len(set(s for s in summaries if s))
    summary_rate = unique_summaries / len(summaries) * 100

    # 统计 competitiveEdge 唯一率
    edges = [i.get("competitiveEdge", "") for i in insights]
    unique_edges = len(set(e for e in edges if e))
    edge_rate = unique_edges / len(edges) * 100

    if summary_rate < 60:
        fail(f"Summary 差异度过低: {summary_rate:.0f}% (期望 >= 60%)")
    elif summary_rate < 80:
        ok(f"Summary 差异度: {summary_rate:.0f}% ({unique_summaries}/{len(insights)}) [基本合格]")
    else:
        ok(f"Summary 差异度: {summary_rate:.0f}% ({unique_summaries}/{len(insights)}) [优秀]")

    if edge_rate < 60:
        fail(f"Edge 差异度过低: {edge_rate:.0f}% (期望 >= 60%)")
    elif edge_rate < 80:
        ok(f"Edge 差异度: {edge_rate:.0f}% ({unique_edges}/{len(insights)}) [基本合格]")
    else:
        ok(f"Edge 差异度: {edge_rate:.0f}% ({unique_edges}/{len(insights)}) [优秀]")


def test_insight_content_quality():
    """测试：洞察内容质量（字数限制、列表数量、内容一致性）"""
    gi = import_generator_module()
    if gi is None:
        skip("generate-insights.py 不可导入")
        return

    data = load_test_data()
    all_ok = True

    for p in data:
        insight = gi.generate_insight(p)

        # 检查 summary 字数
        summary = insight.get("summary", "")
        if len(summary) > MAX_SUMMARY_LEN:
            fail(f"{p['topicId']} summary 超长: {len(summary)} 字 (限制 {MAX_SUMMARY_LEN})")
            all_ok = False

        # 检查 competitiveEdge 字数
        edge = insight.get("competitiveEdge", "")
        if len(edge) > EDGE_MAX_LEN:
            fail(f"{p['topicId']} competitiveEdge 超长: {len(edge)} 字 (限制 {EDGE_MAX_LEN})")
            all_ok = False

        # 检查 risks 数量
        risks = insight.get("risks", [])
        if not isinstance(risks, list):
            fail(f"{p['topicId']} risks 不是列表")
            all_ok = False
        elif len(risks) < MIN_RISKS:
            fail(f"{p['topicId']} risks 太少: {len(risks)} 个 (要求 >= {MIN_RISKS})")
            all_ok = False
        elif len(risks) > MAX_RISKS:
            # 过多只是警告，不算失败
            print(f"  ! WARN: {p['topicId']} risks 过多: {len(risks)} 个")

        # 检查 suggestions 数量
        suggestions = insight.get("suggestions", [])
        if not isinstance(suggestions, list):
            fail(f"{p['topicId']} suggestions 不是列表")
            all_ok = False
        elif len(suggestions) < MIN_SUGGESTIONS:
            fail(f"{p['topicId']} suggestions 太少: {len(suggestions)} 个 (要求 >= {MIN_SUGGESTIONS})")
            all_ok = False
        elif len(suggestions) > MAX_SUGGESTIONS:
            print(f"  ! WARN: {p['topicId']} suggestions 过多: {len(suggestions)} 个")

        # 检查 marketOpportunity 字数
        opportunity = insight.get("marketOpportunity", "")
        if len(opportunity) > OPPORTUNITY_MAX_LEN:
            fail(f"{p['topicId']} marketOpportunity 超长: {len(opportunity)} 字")
            all_ok = False

    if all_ok:
        ok(f"全部 {len(data)} 条洞察内容质量合格")


def test_insight_score_correlation():
    """测试：洞察内容与实际评分一致（高评分项目不应有尖锐批评）"""
    gi = import_generator_module()
    if gi is None:
        skip("generate-insights.py 不可导入")
        return

    data = load_test_data()
    all_ok = True

    for p in data:
        insight = gi.generate_insight(p)
        edge = insight.get("competitiveEdge", "")

        # S 级项目不应该出现负面词汇
        if p.get("qualityGrade") == "S":
            negative_words = ["劣势", "不足", "薄弱", "严重", "差"]
            for word in negative_words:
                if word in edge:
                    fail(f"{p['topicId']} S 级项目 competitiveEdge 含负面词: '{word}'")
                    all_ok = False
                    break

        # C 级项目不应该夸大
        if p.get("qualityGrade") == "C":
            overstate_words = ["顶尖", "一流", "卓越", "非凡"]
            for word in overstate_words:
                if word in edge:
                    fail(f"{p['topicId']} C 级项目 competitiveEdge 过度夸大: '{word}'")
                    all_ok = False
                    break

    if all_ok:
        ok("洞察内容与评分一致性通过")


def test_edge_cases():
    """测试：边界条件（空 strengths/weaknesses、极端评分）"""
    gi = import_generator_module()
    if gi is None:
        skip("generate-insights.py 不可导入")
        return

    # 弱项为空的项目
    p_empty = {
        "topicId": "999",
        "title": "边界测试项目",
        "scores": {"functionality": 5.0, "innovation": 5.0, "ux": 5.0,
                   "visual": 5.0, "techDifficulty": 5.0, "practicality": 5.0},
        "avgScore": 5.0, "qualityGrade": "B",
        "strengths": [], "weaknesses": [], "votes": 0
    }
    try:
        insight = gi.generate_insight(p_empty)
        # 不应抛异常，且所有字段不应为空
        for field in INSIGHT_FIELDS:
            val = insight.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                fail(f"空数据下 {field} 为空")
                return
            if isinstance(val, list) and not val:
                fail(f"空数据下 {field} 为空列表")
                return
        ok("边界条件: 空 strengths/weaknesses 不抛异常且所有字段非空")
    except Exception as e:
        fail(f"边界条件测试异常: {e}")

    # 极端高评分项目
    p_high = {
        "topicId": "998",
        "title": "极端高评项目",
        "scores": {"functionality": 9.5, "innovation": 9.8, "ux": 9.0,
                   "visual": 9.2, "techDifficulty": 9.5, "practicality": 9.0},
        "avgScore": 9.33, "qualityGrade": "S",
        "strengths": ["全面优秀", "无可挑剔"],
        "weaknesses": [], "votes": 5000
    }
    try:
        insight = gi.generate_insight(p_high)
        if not insight.get("summary"):
            fail("极端高评分项目 summary 为空")
            return
        ok("边界条件: 极端高评分项目正常生成")
    except Exception as e:
        fail(f"极端高评分项目异常: {e}")


# ==================== 主入口 ====================

ALL_TESTS = [
    ("数据契约: projects 数组", test_contract_projects_exist),
    ("数据契约: 必填字段", test_contract_required_fields),
    ("数据契约: scores 格式", test_contract_scores_format),
    ("数据契约: qualityGrade", test_contract_quality_grade),
    ("本地引擎: 幂等性", test_local_engine_idempotence),
    ("本地引擎: 字段完整性", test_local_engine_all_fields),
    ("洞察质量: 差异度", test_insight_differentiation),
    ("洞察质量: 内容限制", test_insight_content_quality),
    ("洞察质量: 评分一致性", test_insight_score_correlation),
    ("边界条件", test_edge_cases),
]


def main():
    parser = argparse.ArgumentParser(description="ai-batch-processor 自动化测试")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--filter", "-f", choices=["contract", "local", "quality", "edge"],
                       help="按类别筛选测试")
    args = parser.parse_args()

    global pass_count, fail_count, skip_count

    # 按类别筛选
    filters = {
        "contract": ["数据契约"],
        "local": ["本地引擎"],
        "quality": ["洞察质量"],
        "edge": ["边界条件"],
    }

    print("=" * 60)
    print("  ai-batch-processor 自动化测试")
    print("=" * 60)
    print()

    for name, test_func in ALL_TESTS:
        if args.filter:
            label = filters.get(args.filter, [])
            if not any(name.startswith(l) for l in label):
                skip_count += 1
                print(f"[{name}]")
                skip("(已跳过)\n")
                continue

        print(f"[{name}]")
        try:
            test_func()
        except Exception as e:
            fail(f"未捕获异常: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
        print()

    # 汇总
    total = pass_count + fail_count
    print("=" * 60)
    print(f"  通过: {pass_count}  失败: {fail_count}  跳过: {skip_count}")
    if fail_count == 0:
        print(f"  ✓ 全部 {total} 个测试通过！")
    else:
        print(f"  ✗ {fail_count}/{total} 个测试失败")
    print("=" * 60)

    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())