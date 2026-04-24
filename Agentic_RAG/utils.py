"""
工具函数模块

职责：提供可跨模块复用的纯函数工具，避免在具体模块间产生循环依赖。
对外接口：
  extract_key_entities(results) -> str   # 从检索结果提取关键实体文本（优先读结论）
  clean_table_text(table_text) -> str    # Markdown 表格转纯文本
  llm_classify(chunks, entity_query) -> str  # LLM 从检索结果推断实体所属分类
"""

import re


def extract_key_entities(results: list) -> str:
    """
    从检索结果中提取关键实体文本，用于下一步的查询词。

    优先级：
    1. is_conclusion=True 的结论 chunk（由 search_classification 的 LLM 推断产生）
       直接返回 category 字段，格式干净，如"C类"
    2. 含 Markdown 表格的文本 → 清洗为纯文本单元格
    3. 普通文本 → 截取前 200 字
    """
    if not results:
        return "（未找到相关内容）"

    # 优先：LLM 推断结论（is_conclusion=True，且 category 非空）
    for r in results:
        if r.get("is_conclusion") and r.get("category"):
            return r["category"]

    # 结论 chunk 无效时，跳过所有结论 chunk，取第一个正常内容 chunk
    non_conclusion = [r for r in results if not r.get("is_conclusion")]
    if not non_conclusion:
        return "（未找到相关内容）"

    top_text = non_conclusion[0]["text"]

    # 含表格时清洗 Markdown 格式符号
    if "|" in top_text:
        return clean_table_text(top_text)

    return top_text[:200]


def clean_table_text(table_text: str) -> str:
    """
    将 Markdown 表格转换为纯文本关键实体。

    输入示例：
        | 城市类别 | 包含城市 |
        |---------|---------|
        | A类城市 | 北京、上海、广州、深圳 |

    输出示例：
        城市类别 包含城市 A类城市 北京、上海、广州、深圳
    """
    cells = []
    for line in table_text.splitlines():
        stripped = line.strip()
        if re.match(r"^[\|\s\-:]+$", stripped):
            continue
        if stripped.startswith("|"):
            row_cells = [c.strip() for c in stripped.strip("|").split("|")]
            cells.extend(c for c in row_cells if c)

    return " ".join(cells)[:300]


def llm_classify_overseas(entity_query: str) -> str:
    """
    判断境外实体属于哪个境外费用类别。

    境外分类规则（固定，无需检索）：
      A类：欧洲/美国/日本/新加坡
      B类：其他国家/地区
      C类：港澳台（由 scope=china 直接确定，不走此函数）

    Returns:
        "A类" | "B类"；无法判断时返回空字符串
    """
    prompt = f"""\
根据以下境外出差费用分类规则，判断问题中涉及的国家/地区属于哪个类别。
只输出类别名称本身（如"A类"、"B类"），不要其他解释。

境外分类规则：
- A类：欧洲各国、美国、日本、新加坡
- B类：其他国家/地区

注意：如果无法判断，输出"B类"作为保守默认值。

问题：{entity_query}

该国家/地区的境外类别是："""

    from llm import call_llm
    result = call_llm(prompt).strip()

    if not result or len(result) > 20:
        return "B类"  # 境外未知国家默认B类

    return result


def llm_classify(chunks: list, entity_query: str) -> str:
    """
    调用 LLM 从检索结果中推断实体所属分类。

    这是分类 Skill 的核心推断步骤：
    - 深圳：BM25 命中分类规则 → LLM 读规则 → 直接得出"A类"
    - 揭阳：BM25 未命中 → chunks 为空 → 返回""
      （揭阳的兜底推断交由 Generator 完成，它能读到完整分类规则后推断"C类：其他"）

    Args:
        chunks:       检索到的分类规则 chunk 列表
        entity_query: 用户原始查询词（含实体名，如"深圳出差住宿费"）

    Returns:
        分类结论字符串（如"A类"）；无法推断时返回空字符串
    """
    if not chunks:
        return ""

    # 只取 top-3，控制 token 消耗
    context = "\n---\n".join(c["text"] for c in chunks[:3])

    prompt = f"""\
根据以下分类规则，判断问题中涉及的实体属于哪个类别。
只输出类别名称本身（如"A类"、"B类"、"C类"），不要其他解释。

推理说明：
- 如果实体在规则中被明确列出，直接使用对应类别。
- 如果实体未被明确列出，请结合地理常识进行推理：
  例如"B类：除A类外其他省会城市"，需要你判断该城市是否为省会城市。
- 只有确实无法判断时，才输出"未知"。

分类规则：
{context}

问题：{entity_query}

该实体的类别是："""

    from llm import call_llm  # 延迟导入，避免循环依赖
    result = call_llm(prompt).strip()

    # 过滤无效回答
    if not result or result == "未知" or len(result) > 20:
        return ""

    return result
