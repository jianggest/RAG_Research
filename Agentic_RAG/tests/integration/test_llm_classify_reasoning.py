"""
llm_classify 推理能力集成测试

目的：验证 LLM 能否真实推断出城市分类，而非 Mock 返回固定结果。
     这是单元测试无法覆盖的层次——prompt 引导是否有效、LLM 地理知识是否充分。

运行条件：
  - Ollama 已启动，且已拉取 config.py 中配置的模型
  - 运行命令：pytest tests/integration/ -v -m integration

标记说明：
  - @pytest.mark.integration  不纳入常规 CI，按需手动运行
  - @pytest.mark.slow         调用真实 LLM，耗时较长

分类规则（与知识库文档对齐）：
  A类：北京、上海、广州、深圳（显式列出）
  B类：珠海、汕头、厦门、大连、秦皇岛、天津、烟台、青岛、连云港、南通、
       宁波、温州、福州、湛江、北海 + 除A类外其他省会城市
  C类：其他
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from utils import llm_classify

# ── 与知识库对齐的分类规则文本 ─────────────────────────────────────────────────

CLASSIFICATION_RULE_TEXT = (
    "A 类地区：北京、上海、广州、深圳；\n"
    "B 类地区：珠海、汕头、厦门、大连、秦皇岛、天津、烟台、青岛、连云港、南通、"
    "宁波、温州、福州、湛江、北海和除A类地区外其他省会城市；\n"
    "C 类地区：其他。"
)

CLASSIFICATION_CHUNKS = [
    {"text": CLASSIFICATION_RULE_TEXT, "source": "差旅管理制度.md", "score": 0.9}
]


# ── A类：显式列出，直接命中 ────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("city", ["北京", "上海", "广州", "深圳"])
def test_a_class_explicit_cities(city):
    """A类城市在规则中被明确列出，LLM 应直接识别"""
    result = llm_classify(CLASSIFICATION_CHUNKS, f"{city}出差住宿费")
    assert "A类" in result, f"{city} 期望 A类，实际得到：{result!r}"


# ── B类：显式列出 ──────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("city", ["天津", "厦门", "珠海", "青岛"])
def test_b_class_explicit_cities(city):
    """B类城市在规则中被明确列出，LLM 应直接识别"""
    result = llm_classify(CLASSIFICATION_CHUNKS, f"{city}出差住宿费")
    assert "B类" in result, f"{city} 期望 B类，实际得到：{result!r}"


# ── B类：省会推理（核心验证点）────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("city", ["成都", "杭州", "武汉", "西安", "南京"])
def test_b_class_provincial_capitals_by_reasoning(city):
    """B类省会城市未在列表中显式列出，LLM 须通过地理知识推断。
    验证 prompt 中'省会城市'引导是否真实有效。"""
    result = llm_classify(CLASSIFICATION_CHUNKS, f"{city}出差住宿费")
    assert "B类" in result, (
        f"{city} 是省会城市，应推断为 B类，实际得到：{result!r}\n"
        f"可能原因：prompt 省会引导无效，或模型地理知识不足"
    )


# ── C类：非省会非显式列出 ──────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("city", ["揭阳", "广水", "汕尾", "韶关"])
def test_c_class_other_cities(city):
    """C类城市不在任何显式列表，也不是省会，LLM 应推断为 C类"""
    result = llm_classify(CLASSIFICATION_CHUNKS, f"{city}出差住宿费")
    assert "C类" in result, f"{city} 期望 C类，实际得到：{result!r}"


# ── 边界：直辖市不重复计入省会 ────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.slow
def test_beijing_is_a_not_b():
    """北京是直辖市也是政治中心，但已在 A类显式列出，不应因'省会'逻辑归入 B类"""
    result = llm_classify(CLASSIFICATION_CHUNKS, "北京出差住宿费")
    assert "A类" in result, f"北京应为 A类，实际得到：{result!r}"
