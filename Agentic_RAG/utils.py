"""
工具函数模块

职责：提供可跨模块复用的纯函数工具，避免在具体模块间产生循环依赖。
对外接口：
  extract_key_entities(results) -> str   # 从检索结果提取关键实体文本（优先读结论）
  clean_table_text(table_text) -> str    # Markdown 表格转纯文本
  llm_classify_region(chunks, city) -> dict  # LLM 统一判断地理范围 + 费用分类
"""

import re


def extract_key_entities(results: list) -> str:
    """
    从检索结果中提取关键实体文本，用于下一步的查询词。

    优先级：
    1. is_conclusion=True 的结论 chunk（由 search_expense_reimbursement 的 LLM 推断产生）
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


def llm_classify_region(chunks: list, city: str) -> dict:
    """
    统一的地区分类函数：一次 LLM 调用同时完成地理范围判断和费用类别判断。

    LLM 读取检索到的分类规则 chunk，结合地理常识，输出完整分类结论。
    例如：深圳 → 境内A类，德国 → 境外A类，香港 → 境外C类

    Args:
        chunks:  检索到的分类规则 chunk 列表（含境内/境外分类规则）
        city:    单个城市或国家名称

    Returns:
        {“scope_label”: “境内”|”境外”, “category”: “A类”|”B类”|”C类”}
        无法推断时返回空 dict。
    """
    if not chunks or not city:
        return {}

    # 只取 top-3，控制 token 消耗
    context = """\n---\n""".join(c["text"] for c in chunks[:3])
    print(f"[llm_classify_region] 构造 LLM 上下文：\n{context}\n---")
    prompt = f"""\
根据以下分类规则，对指定地名完成两步判断：

第一步：判断地名属于哪个地理范围
- 境内：中国大陆的城市或省份（如深圳、揭阳、北京、四川）
- 境外：港澳台地区（香港、澳门、台湾）或外国（如美国、日本、德国）

第二步：根据分类规则确定费用类别（A类/B类/C类）
- 境内地名：按规则判断属于境内 A类/B类/C类
- 境外地名：按规则判断属于境外 A类/B类/C类（港澳台通常为境外C类）

推理说明：
- 如果地名在规则中被明确列出，直接使用对应类别
- 如果地名未被明确列出，使用排除法（如：境内不在A类和B类列表中的城市属于C类）
- 需要认真核对规则，避免常识误导

只输出一行结果，格式为”<地理范围><类别>”，例如：
- 境内A类
- 境外B类
- 境外C类

分类规则：
{context}

地名：{city}

分类结果："""

    from llm import call_llm
    result = call_llm(prompt).strip()
    print(f"[llm_classify_region] {city!r} → LLM 原始输出：{result!r}")

    return _parse_region_result(result)


def _parse_region_result(result: str) -> dict:
    """
    解析 LLM 输出的分类结果字符串。

    支持格式：”境内A类”、”境内 A类”、”境外B类” 等。
   """
    if not result or len(result) > 20:
        return {}

    # 提取”境内/境外”和”X类”
    scope_match = re.search(r"(境内|境外)", result)
    category_match = re.search(r"([ABC]类)", result)

    if not scope_match or not category_match:
        print(f"[llm_classify_region] ⚠️ 无法解析分类结果：{result!r}")
        return {}

    return {
        "scope_label": scope_match.group(1),
        "category": category_match.group(1),
    }
