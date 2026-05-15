"""
Planner 模块

职责：接收用户问题，调用 LLM 生成结构化的 Skill 调用计划（JSON）。
对外接口：
  plan(question, skill_descriptions, query_structure=None) -> dict
  parse_plan_json(raw) -> dict           # 供测试直接调用
"""

import json
from typing import Optional

from llm import call_llm


_PLAN_PROMPT_TEMPLATE = """\
你是一个智能检索规划器，将用户问题拆解为一组有序的检索步骤。

可用的检索技能（Skill）：
{skill_descriptions}

规则：
1. 只能使用上方列出的 Skill，不得使用任何其他 Skill（如 web_search、google 等）
2. 这是企业内部知识库检索，查询词应面向内部文档关键词，不要生成互联网搜索词
3. 根据问题的信息依赖关系决定步骤数量（可以是1个或多个）
4. 若后续步骤需要依赖前步骤的结果，在 query 中用 <step_N_result> 作为占位符（N 为依赖的 step_id）
5. depends_on 填写依赖的 step_id，无依赖填 null
6. 【重要】选择 Skill 时以实体类型为依据，而非具体实体值。例：看到【地区名】应想到需要查地区分类规则，而不是直接搜城市名
7. 【重要】若存在约束条件（时间/场景），必须将约束词带入每个检索步骤的 query 中
8. 【重要·系统名 vs 业务动作】当 query 同时包含『系统名』（如 OA / HR系统 / ERP / PLM / JIRA / CRM / FIS）
   和『业务动作』（如 出差申请 / 报销审批 / 请假 / 考勤打卡 / 物料申请 / 合同审批 等），
   必须按【业务动作】选 Skill，而不是按【系统名】。
   系统名只表示"在哪个系统里操作"，业务知识在对应业务域 Skill；IT 指引 Skill 只覆盖账号/登录/密码/网络等基础设施层。
   反例：『OA系统出差申请流程』——业务动作是"出差申请"，应选报销/差旅 Skill，而不是因为出现"OA"就选 IT 指引 Skill。
9. 【重要·datasheet/芯片手册】当问题包含 DLPC、datasheet、芯片型号、oscillator、clock、PLL、timing、electrical characteristics、MHz/ns/ppm/V/mA 等硬件规格词时，优先选择 search_datasheet_v2；仅当 search_datasheet_v2 不在可用 Skill 列表中时，才退回 search_datasheet；不要把 DLPC 文档按企业制度 Skill 处理。
10. 只输出 JSON，不要有任何其他文字
{query_context}
输出格式：
{{
  "reasoning": "分析问题的推理过程",
  "steps": [
    {{"step_id": 1, "skill": "skill名称", "query": "检索关键词", "depends_on": null}},
    {{"step_id": 2, "skill": "skill名称", "query": "<step_1_result> 相关查询", "depends_on": 1}}
  ]
}}

用户问题：{question}\
"""


def parse_plan_json(raw: str) -> dict:
    """
    从 LLM 原始输出中提取并解析 JSON 计划。
    返回解析后的 dict；失败时返回含 "error" 字段的 dict。
    """
    if not raw.strip():
        return {"error": "LLM 返回空响应"}

    # LLM 有时在 JSON 前后附加说明文字
    # 取第一个 { 到最后一个 } 之间的内容，避免贪心匹配问题
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {"error": f"未找到 JSON 内容，原始响应：{raw[:200]}"}

    json_str = raw[start : end + 1]
    try:
        result = json.loads(json_str)
    except json.JSONDecodeError as e:
        return {"error": f"JSON 解析失败: {e}，原始内容：{json_str[:200]}"}

    if "steps" not in result:
        return {"error": "JSON 缺少 steps 字段"}

    if not isinstance(result["steps"], list):
        return {"error": f"steps 应为列表，实际类型：{type(result['steps']).__name__}"}

    return result


def plan(question: str, skill_descriptions: str, query_structure: Optional[dict] = None) -> dict:
    """
    调用 LLM，将用户问题转化为结构化 Skill 调用计划。

    Args:
        question:         用户提问
        skill_descriptions: 可用 Skill 的描述文本
        query_structure:  QueryUnderstanding 输出的结构化语义（可选）

    Returns:
        解析后的计划 dict，含 reasoning 和 steps；
        失败时返回含 "error" 字段的 dict。
    """
    query_context = _build_query_context(query_structure)
    prompt = (
        _PLAN_PROMPT_TEMPLATE
        .replace("{skill_descriptions}", skill_descriptions)
        .replace("{question}", question)
        .replace("{query_context}", query_context)
    )
    raw_response = call_llm(prompt)
    return parse_plan_json(raw_response)


def _build_query_context(query_structure: Optional[dict]) -> str:
    """将 QueryStructure 转为 Planner prompt 中的上下文段落。"""
    if not query_structure:
        return ""

    lines = ["\n【查询语义分析结果（请据此制定检索计划）】"]

    # 实体类型（引导 Skill 选择）
    entities = query_structure.get("entities", [])
    if entities:
        entity_desc = "、".join(f"{e['text']}（{e['type']}）" for e in entities)
        lines.append(f"识别到的实体类型：{entity_desc}")

    # 维度信息（含推断标记）
    dims = query_structure.get("dimensions", {})
    dim_parts = []
    for name, label in [("who", "Who"), ("where", "Where"), ("what", "What")]:
        dim = dims.get(name, {})
        if dim.get("value"):
            tag = "（推断默认值）" if dim.get("inferred") else ""
            dim_parts.append(f"{label}={dim['value']}{tag}")
    if dim_parts:
        lines.append(f"问题维度：{'，'.join(dim_parts)}")

    # 约束条件（必须带入检索）
    constraints = query_structure.get("constraints", [])
    if constraints:
        c_desc = "、".join(f"{c['type']}:{c['value']}" for c in constraints)
        lines.append(f"约束条件（必须带入每步检索 query）：{c_desc}")

    # 缺失维度
    missing = query_structure.get("missing", [])
    if missing:
        lines.append(f"缺失维度（已用默认值补全）：{', '.join(missing)}")

    return "\n".join(lines) + "\n"
