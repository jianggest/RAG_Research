"""
TDD: search_datasheet_v2 的 query 构造、主题 / 设备抽取、source 收窄、round-robin 合并

运行: pytest tests/test_search_datasheet_v2.py -v

测试范围覆盖 V2 的几个「query parsing 与拼装」卫生检查, 不依赖真实 retriever:
  - _detect_topic         主题别名归一 + token 边界 + entity 回退
  - _detect_device_tokens 设备型号抽取（DLPC3436 类）
  - _discover_relevant_datasheet_sources  device → source 收窄
  - _build_facet_query    facet query 三段拼装
  - _facet_round_robin_topk  跨切面保底 + 轮询 + 去重
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills import load_skills
from skills.search_datasheet_v2 import (
    _FACETS,
    _build_facet_query,
    _detect_device_tokens,
    _detect_topic,
    _discover_relevant_datasheet_sources,
    _facet_round_robin_topk,
)


# ── Skill registration ──────────────────────────────────────────────────────

def test_search_datasheet_v2_is_registered_and_v1_is_retained():
    registry = load_skills()

    assert "search_datasheet_v2" in registry
    assert "search_datasheet" in registry


# ── Topic detection ──────────────────────────────────────────────────────────

class TestTopicDetection:
    """主题归一: 命中 alias → 归一名; 否则 fallback 到 entity_tokens"""

    def test_i2c_alias(self):
        assert _detect_topic("DLPC3436 的 I2C 接口或 I2C 信号有哪些") == "I2C"

    def test_i_2_c_decomposed(self):
        """PDF 提取常见的 'I 2 C' 写法（normalize 后仍能命中）"""
        assert _detect_topic("DLPC3436 的 I 2 C 端口") == "I2C"

    def test_iic_alias(self):
        assert _detect_topic("IIC 接口配置") == "I2C"

    def test_oscillator_chinese_alias(self):
        assert _detect_topic("DLPC3436 振荡器要求") == "oscillator"

    def test_oscillator_english_alias(self):
        assert _detect_topic("System Oscillator Timing") == "oscillator"

    def test_esd_alias(self):
        assert _detect_topic("DLPC3436 ESD 设计要求") == "ESD"

    def test_spi_flash_takes_priority_over_spi(self):
        """多词别名 'SPI flash' 排在单词 'SPI' 前面, 应先命中"""
        assert _detect_topic("SPI flash 速度") == "SPI flash"

    def test_spi_alone(self):
        assert _detect_topic("SPI 总线带宽") == "SPI"

    def test_power_chinese_alias(self):
        assert _detect_topic("电源时序要求") == "power"

    def test_no_topic_returns_none(self):
        """没有主题词 → None, 调用方退化为原始 query 检索"""
        assert _detect_topic("DLPC3436 datasheet 概览") is None

    def test_device_model_alone_returns_none(self):
        """只有设备型号 → 不当作 topic"""
        assert _detect_topic("DLPC3436") is None

    # ── token 边界 ──────────────────────────────────────────────────────────

    def test_alias_requires_word_boundary_esd(self):
        """'esdfasdf' 不应被识别为 ESD（避免裸 substring 误判）"""
        assert _detect_topic("esdfasdf 是什么") is None

    def test_alias_requires_word_boundary_parking(self):
        """'asparking' 不应匹配 parking（避免裸 substring 误判）"""
        assert _detect_topic("asparking 现象") is None

    def test_alias_requires_word_boundary_i2c(self):
        """'I2Channel' 不应匹配 I2C（c 后不是边界）"""
        assert _detect_topic("I2Channel 是什么") is None

    def test_alias_requires_word_boundary_spi(self):
        """'aspirin' 不应匹配 SPI"""
        assert _detect_topic("aspirin 是药") is None

    def test_alias_requires_word_boundary_spi_flash(self):
        """'SPIflashx' 不应通过 fallback 被误判成 SPI"""
        assert _detect_topic("SPIflashx 是什么") is None

    def test_parking_real_match(self):
        """正确的 'parking' 表达应能命中"""
        assert _detect_topic("DMD parking 时序") == "parking"

    def test_specific_entity_token_fallback(self):
        """高置信实体 token 可作为 alias 未命中时的 fallback topic"""
        assert _detect_topic("PLL_REFCLK_I 的连接方式") == "PLL_REFCLK_I"

    def test_specific_gpio_token_fallback(self):
        """带编号的 GPIO 实体是具体信号, 可作为 fallback topic"""
        assert _detect_topic("GPIO_08 的电气特性") == "GPIO_08"


# ── Device token detection ──────────────────────────────────────────────────

class TestDeviceTokenDetection:

    def test_single_device(self):
        assert _detect_device_tokens("DLPC3436 的 I2C 接口") == ["DLPC3436"]

    def test_no_device(self):
        assert _detect_device_tokens("oscillator 要求") == []

    def test_multiple_devices(self):
        tokens = _detect_device_tokens("对比 DLPC3436 和 DLPC3437 的差异")
        assert "DLPC3436" in tokens
        assert "DLPC3437" in tokens

    def test_non_device_entity_not_returned(self):
        """PLL_REFCLK_I / I2C 等非设备 entity 不应进 device_tokens"""
        tokens = _detect_device_tokens("PLL_REFCLK_I 的连接方式")
        assert tokens == []


# ── Source 收窄 ──────────────────────────────────────────────────────────────

class TestSourceNarrowing:

    @pytest.fixture
    def chunks(self):
        return [
            {"source": "dlpc3436_clean.md", "is_datasheet": True, "text": ""},
            {"source": "dlpc3437_clean.md", "is_datasheet": True, "text": ""},
            {"source": "dvi_hdmi_spec.md", "is_datasheet": True, "text": ""},
            {"source": "hr_handbook.md", "is_datasheet": False, "text": ""},
        ]

    def test_narrow_to_dlpc3436_only(self, chunks):
        """query 含 DLPC3436 → 只保留 dlpc3436_*.md, 不串到 3437/dvi"""
        sources, aliases, canonical = _discover_relevant_datasheet_sources(chunks, ["DLPC3436"])
        assert sources == {"dlpc3436_clean.md"}
        assert aliases == {}  # 直接 substring 命中, 不产生 alias
        assert canonical == {"DLPC3436": "DLPC3436"}

    def test_unknown_device_returns_empty_sources(self, chunks):
        """库里没有 DLPC9999 → 返回空集合, 避免串台到 dlpc3436/3437/dvi 等无关 datasheet。
        execute() 据此早退并提示用户'未找到该型号资料', 而非把无关型号当兜底带进来。"""
        sources, aliases, canonical = _discover_relevant_datasheet_sources(chunks, ["DLPC9999"])
        assert sources == set()
        assert aliases == {}
        assert canonical == {}

    def test_no_device_returns_all_datasheet(self, chunks):
        sources, aliases, canonical = _discover_relevant_datasheet_sources(chunks, [])
        assert sources == {"dlpc3436_clean.md", "dlpc3437_clean.md", "dvi_hdmi_spec.md"}
        assert aliases == {}
        assert canonical == {}

    def test_empty_chunks_returns_empty(self):
        sources, aliases, canonical = _discover_relevant_datasheet_sources([], ["DLPC3436"])
        assert sources == set()
        assert aliases == {}
        assert canonical == {}


# ── 设备型号模糊命中 (字母前缀容错) ─────────────────────────────────────────────

class TestDeviceTokenFuzzyMatch:
    """裸前缀型号 (如 'DLP6540') 容错命中具体子族 (如 'dlpc6540')。

    规则: 字母前缀 + 数字, 允许 source 在前缀与数字之间插入 1+ 字母。
    已写明子族字母的 token (DLPC/DLPA) 不再扩展, 避免 DLPC ↔ DLPA 串台。
    """

    @pytest.fixture
    def chunks(self):
        return [
            {"source": "DLPC6540_Datasheet_2_clean.md", "is_datasheet": True, "text": ""},
            {"source": "dlpa3005_clean.md",             "is_datasheet": True, "text": ""},
            {"source": "tpsm5430_clean.md",             "is_datasheet": True, "text": ""},
            {"source": "hr_handbook.md",                "is_datasheet": False, "text": ""},
        ]

    def test_dlp_bare_prefix_hits_dlpc_subfamily(self, chunks):
        """DLP6540 → 命中 DLPC6540 (用户口语化型号容错)"""
        sources, aliases, canonical = _discover_relevant_datasheet_sources(chunks, ["DLP6540"])
        assert sources == {"DLPC6540_Datasheet_2_clean.md"}
        assert aliases == {"DLP6540": ["DLPC6540_Datasheet_2_clean.md"]}
        assert canonical == {"DLP6540": "DLPC6540"}

    def test_dlpa_explicit_does_not_overmatch_dlpc(self, chunks):
        """DLPA6540 (子族已明确) 不应误中 DLPC6540: 库里查无此型号 → 返回空集合,
        而非把 DLPC6540 / dlpa3005 等无关型号当兜底带进来。"""
        sources, aliases, canonical = _discover_relevant_datasheet_sources(chunks, ["DLPA6540"])
        assert sources == set()
        assert aliases == {}
        assert canonical == {}

    def test_dlpc_explicit_direct_substring(self, chunks):
        """DLPC6540 (子族已明确) → 直接 substring 命中, 无 alias"""
        sources, aliases, canonical = _discover_relevant_datasheet_sources(chunks, ["DLPC6540"])
        assert sources == {"DLPC6540_Datasheet_2_clean.md"}
        assert aliases == {}
        assert canonical == {"DLPC6540": "DLPC6540"}

    def test_general_letter_prefix_works_for_tps_family(self, chunks):
        """规则通用: TPS5430 容错命中 tpsm5430 (不依赖 DLP)"""
        sources, aliases, canonical = _discover_relevant_datasheet_sources(chunks, ["TPS5430"])
        assert sources == {"tpsm5430_clean.md"}
        assert aliases == {"TPS5430": ["tpsm5430_clean.md"]}
        assert canonical == {"TPS5430": "TPSM5430"}

    def test_token_matches_source_helper(self):
        """直接验证 _device_token_matches_source 的边界"""
        from skills.search_datasheet_v2 import _device_token_matches_source as match
        assert match("DLP6540", "dlpc6540_datasheet_2_clean.md") is True
        assert match("DLPC6540", "dlpc6540_datasheet_2_clean.md") is True
        assert match("DLPA6540", "dlpc6540_datasheet_2_clean.md") is False
        assert match("DLP9999", "dlpc6540_datasheet_2_clean.md") is False
        assert match("TPS5430", "tpsm5430_clean.md") is True


# ── Facet query 构造 ────────────────────────────────────────────────────────

class TestFacetQueryBuild:
    """{device} {topic_or_query} {facet_keywords} 三段拼装"""

    def test_with_device_and_topic(self):
        q = _build_facet_query("pin ball signal", "DLPC3436", "I2C")
        assert q == "DLPC3436 I2C pin ball signal"

    def test_without_device(self):
        q = _build_facet_query("pin ball signal", "", "I2C")
        assert q == "I2C pin ball signal"

    def test_no_topic_uses_original_query(self):
        """topic=None 时, 用原始 query 而不是空串 — 避免丢失约束"""
        q = _build_facet_query("pin ball signal", "DLPC3436", "DLPC3436 的接口或信号有哪些")
        assert "DLPC3436" in q
        assert "接口或信号有哪些" in q
        assert "pin ball signal" in q

    def test_whitespace_folded(self):
        q = _build_facet_query("pin  ball", "  DLPC3436 ", " I2C ")
        assert q == "DLPC3436 I2C pin ball"

    def test_only_facet_keywords(self):
        """device 和 topic 都为空时, 至少保留 facet keywords"""
        q = _build_facet_query("pin ball signal", "", "")
        assert q == "pin ball signal"


# ── Round-robin 合并 ────────────────────────────────────────────────────────

class TestRoundRobin:

    def test_basic_round_robin(self):
        """保底阶段每切面拿 2 条, 然后轮询补"""
        facet_results = {
            "f1": [{"text": "A0"}, {"text": "A1"}, {"text": "A2"}],
            "f2": [{"text": "B0"}, {"text": "B1"}],
        }
        out = _facet_round_robin_topk(facet_results, total=10, min_per_facet=2)
        assert [r["text"] for r in out] == ["A0", "A1", "B0", "B1", "A2"]

    def test_dedup_across_facets(self):
        """同一文本被多切面召回, 只保留一次"""
        facet_results = {
            "f1": [{"text": "X"}, {"text": "Y"}],
            "f2": [{"text": "X"}, {"text": "Z"}],
        }
        out = _facet_round_robin_topk(facet_results, total=10, min_per_facet=2)
        texts = [r["text"] for r in out]
        assert texts.count("X") == 1
        assert set(texts) == {"X", "Y", "Z"}

    def test_empty_facet_skipped(self):
        facet_results = {
            "f1": [{"text": "A"}],
            "f2": [],
            "f3": [{"text": "B"}],
        }
        out = _facet_round_robin_topk(facet_results, total=10, min_per_facet=2)
        assert [r["text"] for r in out] == ["A", "B"]

    def test_respects_total_cap(self):
        """候选很多时, 总数被 cap 在 total"""
        facet_results = {
            "f1": [{"text": f"x{i}"} for i in range(50)],
            "f2": [{"text": f"y{i}"} for i in range(50)],
        }
        out = _facet_round_robin_topk(facet_results, total=20, min_per_facet=2)
        assert len(out) == 20

    def test_all_six_facets_each_keeps_minimum(self):
        """6 切面齐全 + 充足候选: 总额 20, 每切面 ≥ 保底 2"""
        from collections import Counter
        facet_results = {
            facet: [{"text": f"{facet}_{i}"} for i in range(5)]
            for facet in _FACETS
        }
        out = _facet_round_robin_topk(facet_results, total=20, min_per_facet=2)
        assert len(out) == 20
        counts = Counter(r["text"].rsplit("_", 1)[0] for r in out)
        for facet in _FACETS:
            assert counts[facet] >= 2, f"facet {facet} 不到保底 2 条, 实际 {counts[facet]}"

    def test_empty_input(self):
        assert _facet_round_robin_topk({}, total=20, min_per_facet=2) == []


# ── 中文混排 query: token 与 topic 抽取 ─────────────────────────────────────
# 历史问题: \b 在 Python3 Unicode 模式下把汉字也当 \w, 导致 "DLPC3436支" 之间
# 没有边界, 中文混排 query 抽不到设备/主题。改用 ASCII 边界后两者都应命中。

class TestChineseMixedQuery:

    def test_device_token_extracted_from_chinese_query(self):
        assert _detect_device_tokens("DLPC3436支持的I2C有哪些？") == ["DLPC3436"]

    def test_bare_prefix_device_token_extracted_from_chinese_query(self):
        assert _detect_device_tokens("DLP3436支持的I2C有哪些？") == ["DLP3436"]

    def test_topic_extracted_from_chinese_query(self):
        assert _detect_topic("DLPC3436支持的I2C有哪些？") == "I2C"

    def test_topic_extracted_from_bare_prefix_chinese_query(self):
        assert _detect_topic("DLP3436支持的I2C有哪些？") == "I2C"

    def test_canonical_unifies_dlp_and_dlpc_for_same_source(self):
        """DLP3436 与 DLPC3436 命中同一 source 时, canonical 都归一到 DLPC3436,
        让后续 facet query 在向量/BM25 通道的字面 query 真正一致。"""
        chunks = [
            {"source": "dlpc3436_clean.md", "is_datasheet": True, "text": ""},
            {"source": "dlpc3420_clean.md", "is_datasheet": True, "text": ""},
        ]
        _, _, can_dlpc = _discover_relevant_datasheet_sources(chunks, ["DLPC3436"])
        _, _, can_dlp = _discover_relevant_datasheet_sources(chunks, ["DLP3436"])
        assert can_dlpc["DLPC3436"] == "DLPC3436"
        assert can_dlp["DLP3436"] == "DLPC3436"
