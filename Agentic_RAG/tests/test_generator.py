"""
generator 模块测试

覆盖范围：
  - _build_entity_note：分类结论注入 Generator prompt 的提示语
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from generator import _build_entity_note, _is_technical_datasheet_answer, generate


def make_query_structure(where: str = "深圳，德国") -> dict:
    return {
        "dimensions": {
            "who": {"value": "其他员工", "inferred": True},
            "where": {"value": where, "inferred": False},
            "what": {"value": "住宿费", "inferred": False},
        }
    }


class TestBuildEntityNote:

    def test_single_conclusion_note_mentions_entity_and_full_category(self):
        executed_steps = [
            {
                "results": [
                    {
                        "is_conclusion": True,
                        "entity": "深圳",
                        "category": "A类",
                        "full_category": "境内A类",
                    }
                ]
            }
        ]

        note = _build_entity_note(make_query_structure("深圳"), executed_steps)

        assert "深圳" in note
        assert "境内A类" in note
        assert "深圳属于境内A类" in note

    def test_multi_conclusion_note_includes_all_entity_category_mappings(self):
        executed_steps = [
            {
                "results": [
                    {
                        "is_conclusion": True,
                        "entity": "深圳",
                        "category": "A类",
                        "full_category": "境内A类",
                    },
                    {
                        "is_conclusion": True,
                        "entity": "德国",
                        "category": "A类",
                        "full_category": "境外A类",
                    },
                ]
            }
        ]

        note = _build_entity_note(make_query_structure(), executed_steps)

        assert "多个地区分类结论" in note
        assert "深圳属于境内A类" in note
        assert "德国属于境外A类" in note
        assert "不得只使用第一个地区" in note

    def test_legacy_conclusion_without_entity_falls_back_to_query_structure(self):
        executed_steps = [
            {
                "results": [
                    {
                        "is_conclusion": True,
                        "category": "A类",
                    }
                ]
            }
        ]

        note = _build_entity_note(make_query_structure("深圳"), executed_steps)

        assert "深圳属于A类" in note


class TestTechnicalDatasheetGenerator:
    def test_search_datasheet_step_uses_technical_prompt(self):
        executed_steps = [
            {
                "skill": "search_datasheet",
                "results": [
                    {
                        "source": "dlpc3470_clean.md",
                        "text": "## System Oscillator Timing Requirements\n| Clock frequency, MOSC | f clk | 23.998 | 24.000 | 24.002 | MHz |\nThe MOSC input does not support spread spectrum clock spreading.",
                    }
                ],
            }
        ]

        with patch("generator.call_llm", return_value="ok") as mock_call:
            answer = generate("系统 Oscillator Timing 要求？", executed_steps, {"domain": "technical_datasheet"})

        prompt = mock_call.call_args.args[0]
        assert answer == "ok"
        assert "技术 datasheet" in prompt
        assert "不得用常识补齐" in prompt
        assert "必须用中文回答" in prompt
        assert "参数名称必须翻译为中文" in prompt
        assert "补充说明必须翻译成中文" in prompt
        assert "spread spectrum" in prompt
        assert "DLPC3436" not in prompt.split("用户问题：")[0]

    def test_detects_datasheet_answer_from_step_or_domain(self):
        assert _is_technical_datasheet_answer([{"skill": "search_datasheet", "results": []}], None) is True
        assert _is_technical_datasheet_answer([], {"domain": "technical_datasheet"}) is True
        assert _is_technical_datasheet_answer([{"skill": "search_expense_reimbursement", "results": []}], {}) is False
