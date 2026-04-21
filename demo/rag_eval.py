# -*- coding: utf-8 -*-
"""
RAG 三元组自动评估模块（LLM-as-Judge）

三个评估维度：
  ① Context Relevance  — 检索片段与问题的相关性
  ② Faithfulness       — 答案是否忠实于检索内容（有无幻觉）
  ③ Answer Relevance   — 答案是否真正回答了问题

每个维度输出 0~1 的分数，并附带简短的评估理由。
"""

import json
import re


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  工具函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_json(text: str) -> dict:
    """
    从 LLM 输出中提取 JSON。
    LLM 有时会在 JSON 前后加多余文字或代码块标记，这里做容错处理。
    """
    # 去掉 markdown 代码块标记
    text = re.sub(r"```(?:json)?", "", text).strip()
    # 提取第一个 { ... } 块
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _format_contexts(contexts: list) -> str:
    """将检索片段列表格式化为字符串，供 Prompt 使用。"""
    parts = []
    for i, ctx in enumerate(contexts, 1):
        parts.append(f"【片段{i} | 来源：{ctx['source']}】\n{ctx['text']}")
    return "\n\n".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ① Context Relevance（上下文相关性）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def evaluate_context_relevance(question: str, contexts: list, call_llm_func) -> dict:
    """
    评估检索到的片段与问题的相关性。

    【评估逻辑】
    让 LLM 逐一判断每个片段是否包含回答问题所需的信息，
    最终分数 = 有用片段数 / 总片段数。

    分数低 → 说明召回了太多无关内容，检索阶段需要优化。
    """
    context_text = _format_contexts(contexts)
    total = len(contexts)

    prompt = f"""你是一个 RAG 系统评估专家。请判断以下检索片段中，哪些片段对回答问题是有用的。

判断标准：
- 有用：片段包含与问题直接相关的信息
- 无用：片段与问题无关，或包含的信息对回答没有帮助

问题：{question}

检索片段：
{context_text}

请严格按以下 JSON 格式输出，不要输出其他内容：
{{"useful_count": <有用片段数量>, "total": {total}, "reason": "<简要说明哪些片段有用/无用>"}}"""

    raw = call_llm_func(prompt) or ""
    data = _parse_json(raw)

    useful = int(data.get("useful_count", 0))
    score = round(useful / total, 3) if total > 0 else 0.0

    return {
        "score": score,
        "useful_count": useful,
        "total": total,
        "reason": data.get("reason", raw[:200]),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ② Faithfulness（答案忠实性）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def evaluate_faithfulness(question: str, contexts: list, answer: str, call_llm_func) -> dict:
    """
    评估答案是否忠实于检索内容（检测幻觉）。

    【评估逻辑】
    让 LLM 把答案拆解成若干陈述句，再逐一判断每个陈述
    是否能从检索片段中找到支撑依据。
    分数 = 有依据的陈述数 / 总陈述数。

    分数低 → 说明 LLM 在编造检索内容之外的信息（幻觉）。
    """
    context_text = _format_contexts(contexts)

    prompt = f"""你是一个 RAG 系统评估专家。请判断答案中的每个陈述是否有检索片段作为依据。

步骤：
1. 将答案拆解为若干独立的陈述句
2. 对每个陈述，判断检索片段中是否有支撑该陈述的内容
3. 统计有依据的陈述数量

问题：{question}

检索片段：
{context_text}

答案：
{answer}

请严格按以下 JSON 格式输出，不要输出其他内容：
{{"supported": <有依据的陈述数>, "total": <总陈述数>, "reason": "<简要说明哪些陈述没有依据，或全部有依据>"}}"""

    raw = call_llm_func(prompt) or ""
    data = _parse_json(raw)

    supported = int(data.get("supported", 0))
    total     = int(data.get("total", 1))
    score = round(supported / total, 3) if total > 0 else 0.0

    return {
        "score": score,
        "supported": supported,
        "total": total,
        "reason": data.get("reason", raw[:200]),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ③ Answer Relevance（答案相关性）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def evaluate_answer_relevance(question: str, answer: str, call_llm_func) -> dict:
    """
    评估答案是否真正回答了用户的问题。

    【评估逻辑】
    直接让 LLM 判断答案对问题的覆盖程度：
    - 是否回答了问题的核心诉求
    - 是否存在答非所问的情况
    - 是否有重要信息遗漏

    分数低 → 说明答案偏题，或检索内容不足导致无法完整作答。
    """
    prompt = f"""你是一个 RAG 系统评估专家。请评估以下答案对问题的回答质量。

评分标准（0~1）：
- 1.0：完整、准确地回答了问题
- 0.7：基本回答了问题，但有少量信息遗漏
- 0.4：部分回答了问题，存在明显遗漏或偏题
- 0.1：几乎没有回答问题，或完全答非所问

问题：{question}

答案：
{answer}

请严格按以下 JSON 格式输出，不要输出其他内容：
{{"score": <0到1之间的小数>, "reason": "<简要说明评分理由，指出答案的优缺点>"}}"""

    raw = call_llm_func(prompt) or ""
    data = _parse_json(raw)

    try:
        score = round(float(data.get("score", 0.0)), 3)
        score = max(0.0, min(1.0, score))  # 限制在 0~1
    except (ValueError, TypeError):
        score = 0.0

    return {
        "score": score,
        "reason": data.get("reason", raw[:200]),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  汇总入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def evaluate_all(question: str, contexts: list, answer: str, call_llm_func) -> dict:
    """
    运行三项评估，返回汇总结果。

    返回格式：
    {
        "context_relevance": {"score": 0.8, "useful_count": 4, "total": 5, "reason": "..."},
        "faithfulness":      {"score": 0.95, "supported": 19, "total": 20, "reason": "..."},
        "answer_relevance":  {"score": 0.85, "reason": "..."},
        "overall":           0.87   # 三项均值
    }
    """
    if not answer or not contexts:
        return {}

    cr = evaluate_context_relevance(question, contexts, call_llm_func)
    fa = evaluate_faithfulness(question, contexts, answer, call_llm_func)
    ar = evaluate_answer_relevance(question, answer, call_llm_func)

    overall = round((cr["score"] + fa["score"] + ar["score"]) / 3, 3)

    return {
        "context_relevance": cr,
        "faithfulness":      fa,
        "answer_relevance":  ar,
        "overall":           overall,
    }
