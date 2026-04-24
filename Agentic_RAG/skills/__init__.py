"""
Skills 动态加载器

扫描当前目录下所有 search_*.py 文件，自动注册为可用 Skill。
每个 Skill 文件必须包含：
  - SKILL_META: dict   — Skill 的元数据（名称、描述、检索方式）
  - execute(query, retriever) -> list[dict]  — 执行检索的函数
"""

import importlib
import pkgutil
from pathlib import Path


def load_skills() -> dict:
    """
    扫描 skills/ 目录，动态加载所有 search_*.py 文件。

    返回：
        {
            "search_classification": {
                "meta": SKILL_META,
                "execute": execute_fn,
            },
            ...
        }
    """
    registry = {}
    skills_dir = Path(__file__).parent

    for finder, module_name, _ in pkgutil.iter_modules([str(skills_dir)]):
        if not module_name.startswith("search_"):
            continue
        if module_name == "search_example":
            continue  # 模板文件，跳过实际加载

        try:
            module = importlib.import_module(f".{module_name}", package=__name__)
        except Exception as e:
            print(f"[SkillLoader] 跳过 {module_name}.py，导入失败：{e}")
            continue

        # 校验必要属性
        if not hasattr(module, "SKILL_META"):
            print(f"[SkillLoader] 跳过 {module_name}.py，缺少 SKILL_META")
            continue
        if not hasattr(module, "execute"):
            print(f"[SkillLoader] 跳过 {module_name}.py，缺少 execute 函数")
            continue

        skill_name = module.SKILL_META.get("name", module_name)
        registry[skill_name] = {
            "meta": module.SKILL_META,
            "execute": module.execute,
        }
        print(f"[SkillLoader] 已加载 Skill: {skill_name}")

    return registry


# 模块级注册表，导入时自动加载
SKILL_REGISTRY: dict = {}


def get_registry() -> dict:
    """获取已加载的 Skill 注册表，懒加载（首次调用时加载）。"""
    global SKILL_REGISTRY
    if not SKILL_REGISTRY:
        SKILL_REGISTRY = load_skills()
    return SKILL_REGISTRY


def get_skill_descriptions() -> str:
    """
    返回所有 Skill 的描述文本，供 Planner 的 prompt 使用。

    示例输出：
        - search_classification: 查询某个实体属于哪个分类/等级
        - search_standards: 查询某个分类下的具体标准/金额/限额
    """
    registry = get_registry()
    lines = []
    for name, skill in registry.items():
        desc = skill["meta"].get("description", "（无描述）")
        lines.append(f"  - {name}: {desc}")
    return "\n".join(lines)
