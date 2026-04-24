"""
Skill 编写模板 — search_example.py

【使用说明】
  1. 复制本文件，重命名为 search_<你的skill名>.py（例如 search_standards.py）
  2. 修改 SKILL_META 中的三个字段
  3. 实现 execute() 函数的检索逻辑
  4. 放入 skills/ 目录，系统启动时自动加载，无需修改其他代码

【文件命名规则】
  - 必须以 search_ 开头
  - search_example.py 本身不会被加载（已在加载器中排除）

【接口约定】
  - SKILL_META: dict         必填，Skill 元数据
  - execute(query, retriever) 必填，执行检索逻辑
  - 返回值格式固定，见下方 execute() 的 Returns 说明
"""

# ── 1. Skill 元数据（必填，三个字段均不可省略）──────────────────────────────

SKILL_META = {
    # Skill 的唯一标识名，与文件名保持一致（去掉 .py）
    "name": "search_example",

    # 描述这个 Skill 的用途，Planner 会读取这段文字来决定是否调用它
    # 写得越准确，Planner 的选择越精准
    "description": "（在此填写：这个 Skill 能查什么，适合什么类型的问题）",

    # 推荐的检索方式，Executor 可据此选择检索策略
    # 可选值："vector"（语义检索）/ "bm25"（关键词检索）/ "hybrid"（混合）
    "retrieval_method": "vector",
}


# ── 2. 执行函数（必填）────────────────────────────────────────────────────────

def execute(query: str, retriever) -> list[dict]:
    """
    执行检索，返回相关文本块列表。

    Args:
        query (str):
            检索关键词或语句。
            注意：占位符（如 {{step_1_result}}）在传入前已由 Executor 替换完毕。

        retriever:
            检索器对象，提供以下三个方法（选其一调用）：
              - retriever.vector_search(query, top_k)  → list[dict]
              - retriever.bm25_search(query, top_k)    → list[dict]
              - retriever.hybrid_search(query, top_k)  → list[dict]

    Returns:
        list[dict]，每个元素格式固定如下：
        [
            {
                "text":   str,   # chunk 的原始文本内容（必填）
                "source": str,   # 来源文件名，例如 "02_员工手册.txt"（必填）
                "score":  float, # 相关性得分，越高越相关（必填，不确定时填 0.0）
            },
            ...
        ]
        若无结果，返回空列表 []。
    """

    # ── 在此实现你的检索逻辑 ──────────────────────────────────────────────────

    # 示例：直接调用向量检索
    results = retriever.vector_search(query, top_k=5)

    # 示例：调用 BM25 关键词检索
    # results = retriever.bm25_search(query, top_k=5)

    # 示例：调用混合检索
    # results = retriever.hybrid_search(query, top_k=5)

    # 示例：在结果基础上做额外过滤（可选）
    # results = [r for r in results if r["score"] > 0.5]

    return results
