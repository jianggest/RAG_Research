"""
llm_classify_region 推理能力集成测试

目的：验证配置未覆盖时，LLM 兜底分类能否根据规则文本推断地理范围和费用分类。
     生产路径会先用 config/region_classification.json 做确定性分类；
     这些测试只覆盖 LLM fallback 的提示词和推理能力。

运行条件：
  - Ollama 已启动，且已拉取 config.py 中配置的模型
  - 运行命令：pytest tests/integration/ -v -m integration

标记说明：
  - @pytest.mark.integration  不纳入常规 CI，按需手动运行
  - @pytest.mark.slow         调用真实 LLM，耗时较长

分类规则（模拟生产代码从 config/region_classification.json 转换出的 LLM fallback 上下文）：
  境内A类：北京、上海、广州、深圳
  境内B类：计划单列市、沿海开放城市、除A类外的省会城市等
  境内C类：其他
  境外A类：新加坡、欧洲、美国、日本
  境外B类：其他国家
  境外C类：港澳台
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from skills.search_expense_reimbursement import _build_static_rule_chunks
from utils import llm_classify_region

# ── 使用生产配置生成的 fallback 规则上下文 ──────────────────────────────────────

CLASSIFICATION_CHUNKS = _build_static_rule_chunks()


# ── 境内兜底分类 ──────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("city,expected_category", [
    ("北京", "A类"),
    ("天津", "B类"),
    ("揭阳", "C类"),
])
def test_mainland_fallback_classification(city, expected_category):
    """LLM fallback 应能按境内规则输出 A/B/C 类。"""
    result = llm_classify_region(CLASSIFICATION_CHUNKS, city)
    assert result == {"scope_label": "境内", "category": expected_category}


# ── 境外兜底分类 ──────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("place", ["美国", "日本", "新加坡"])
def test_overseas_a_class_explicit_places(place):
    """美国/日本/新加坡在制度规则中明确列为境外 A 类。"""
    result = llm_classify_region(CLASSIFICATION_CHUNKS, place)
    assert result == {"scope_label": "境外", "category": "A类"}


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("place", ["爱沙尼亚", "拉脱维亚", "立陶宛"])
def test_overseas_a_class_europe_fallback_places(place):
    """欧洲国家在配置规则上下文中显式列出时，LLM fallback 应按境外 A 类判断。"""
    result = llm_classify_region(CLASSIFICATION_CHUNKS, place)
    assert result == {"scope_label": "境外", "category": "A类"}


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("place,expected_category", [
    ("越南", "B类"),
    ("香港", "C类"),
])
def test_overseas_b_and_c_fallback_places(place, expected_category):
    result = llm_classify_region(CLASSIFICATION_CHUNKS, place)
    assert result == {"scope_label": "境外", "category": expected_category}


# ── 边界：直辖市不重复计入省会 ────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.slow
def test_beijing_is_a_not_b():
    """北京是直辖市也是政治中心，但已在 A类显式列出，不应因'省会'逻辑归入 B类"""
    result = llm_classify_region(CLASSIFICATION_CHUNKS, "北京")
    assert result == {"scope_label": "境内", "category": "A类"}
