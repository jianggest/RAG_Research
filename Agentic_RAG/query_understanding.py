"""
查询理解模块 — 业务语义补全与结构化拆解

职责：在检索前对用户查询进行深度语义解析：
  1. 完整性检测：识别 Who/Where/What 维度，标记缺失项
  2. 约束条件识别：时间约束、场景约束、条件约束
  3. 查询扩展：补全缺失维度的默认假设，生成完整语义
  4. 意图颗粒度：判断用户期望总结性回答还是精确事实
  5. 冲突检测：识别逻辑相悖的实体组合
  6. 歧义处理：关键维度（Where）缺失且影响答案时标记需要追问

对外接口：
  parse_query(question: str) -> QueryStructure
  build_clarification_question(query_structure: QueryStructure) -> str
"""

import json
from typing import TypedDict

from llm import call_llm


# ── 数据结构 ──────────────────────────────────────────────────────────────────

class QueryStructure(TypedDict):
    original: str
    expanded: str
    dimensions: dict        # {"who": {"value":..., "inferred":...}, "where":..., "what":...}
    entities: list          # [{"text":..., "type":..., "role":...}]
    constraints: list       # [{"type":..., "value":..., "source":...}]
    intent_granularity: str # "总结性" | "精确事实"
    missing: list           # 缺失的关键维度名称
    conflicts: list         # 检测到的冲突描述
    needs_clarification: bool


# ── Prompt ────────────────────────────────────────────────────────────────────

_PARSE_PROMPT = """\
你是一个企业内部知识库的查询分析助手，负责对用户查询做结构化语义解析。

【维度说明】
- Who（询问主体）：查询适用于谁，如职级/身份/部门
- Where（地点/范围）：涉及的地区或城市
- What（事项）：具体想查询的内容，如费用项、流程、政策

【intent_granularity 判断规则】
- "总结性"：用户想概括了解，如"简单说说出差流程"、"介绍一下报销政策"
- "精确事实"：用户想要具体数字或明确规定，如"住宿费是多少"、"第二联贴在哪"

【缺失维度处理规则】
- Who 缺失：默认补全为"其他员工"，inferred=true，missing 加入"who"，但 needs_clarification 保持 false（用默认值继续）
- Where 缺失且问题涉及地区性标准（出差、差旅等）：needs_clarification=true，missing 加入"where"
- Where 缺失但问题与地区无关（如请假流程）：不标记缺失

【冲突检测规则】
- 同一问题中出现逻辑相悖的实体组合时，在 conflicts 中描述冲突
- 例：P10职级（高管）+ 实习生（基层）= 冲突

只输出 JSON，不要有其他文字：
{{
  "original": "{question}",
  "expanded": "补全缺失维度后的完整语义描述",
  "dimensions": {{
    "who":   {{"value": "识别值或null", "inferred": false}},
    "where": {{"value": "识别值或null", "inferred": false}},
    "what":  {{"value": "识别值或null", "inferred": false}}
  }},
  "entities": [
    {{"text": "实体文本", "type": "地区名|职级名|费用项|部门名|金额数值|员工状态", "role": "查询对象|目标属性"}}
  ],
  "constraints": [
    {{"type": "时间约束|场景约束|条件约束", "value": "约束内容", "source": "显式|推断"}}
  ],
  "intent_granularity": "总结性|精确事实",
  "missing": [],
  "conflicts": [],
  "needs_clarification": false
}}

用户查询：{question}"""


# ── 对外接口 ──────────────────────────────────────────────────────────────────

def parse_query(question: str) -> QueryStructure:
    """
    对用户查询做结构化语义解析。

    LLM 调用失败或返回非法 JSON 时，降级返回最小结构，确保主流程不中断。
    """
    if not question.strip():
        return _fallback_structure(question)

    prompt = _PARSE_PROMPT.format(question=question)
    raw = call_llm(prompt)

    structure = _parse_llm_response(raw, question)
    print(f"[QueryUnderstanding] 维度: who={structure['dimensions']['who']['value']} "
          f"where={structure['dimensions']['where']['value']} "
          f"what={structure['dimensions']['what']['value']}")
    if structure["missing"]:
        print(f"[QueryUnderstanding] 缺失维度: {structure['missing']}")
    if structure["conflicts"]:
        print(f"[QueryUnderstanding] 冲突检测: {structure['conflicts']}")
    if structure["needs_clarification"]:
        print(f"[QueryUnderstanding] 需要追问用户")

    return structure


def build_clarification_question(query_structure: QueryStructure) -> str:
    """
    根据缺失维度生成追问文案。
    needs_clarification=True 时由主流程调用。
    """
    missing = query_structure.get("missing", [])
    parts = []
    if "where" in missing:
        parts.append("您要查询的是哪个城市/地区的标准？")
    if "who" in missing:
        parts.append("您的职级或身份是？（如：普通员工、经理、副总裁等）")
    if not parts:
        return "您的问题缺少一些关键信息，请补充后重新提问。"
    return "为了给您准确的答案，请问：" + "；".join(parts)


# ── 内部工具函数 ──────────────────────────────────────────────────────────────

def _parse_llm_response(raw: str, original_question: str) -> QueryStructure:
    """从 LLM 原始输出中提取并验证 JSON，失败时降级。"""
    if not raw.strip():
        return _fallback_structure(original_question)

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        print(f"[QueryUnderstanding] ⚠️ LLM 返回非 JSON 内容，降级处理")
        return _fallback_structure(original_question)

    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as e:
        print(f"[QueryUnderstanding] ⚠️ JSON 解析失败: {e}，降级处理")
        return _fallback_structure(original_question)

    return _normalize(data, original_question)


def _normalize(data: dict, original_question: str) -> QueryStructure:
    """确保所有字段存在且类型正确，填充缺省值。"""
    default_dim = {"value": None, "inferred": False}
    dimensions = data.get("dimensions", {})

    return QueryStructure(
        original=data.get("original", original_question),
        expanded=data.get("expanded", original_question),
        dimensions={
            "who":   dimensions.get("who",   default_dim),
            "where": dimensions.get("where", default_dim),
            "what":  dimensions.get("what",  default_dim),
        },
        entities=data.get("entities", []),
        constraints=data.get("constraints", []),
        intent_granularity=data.get("intent_granularity", "精确事实"),
        missing=data.get("missing", []),
        conflicts=data.get("conflicts", []),
        needs_clarification=bool(data.get("needs_clarification", False)),
    )


def _fallback_structure(question: str) -> QueryStructure:
    """LLM 不可用或解析失败时的降级结构，确保主流程不中断。"""
    return QueryStructure(
        original=question,
        expanded=question,
        dimensions={
            "who":   {"value": None, "inferred": False},
            "where": {"value": None, "inferred": False},
            "what":  {"value": None, "inferred": False},
        },
        entities=[],
        constraints=[],
        intent_granularity="精确事实",
        missing=[],
        conflicts=[],
        needs_clarification=False,
    )
