"""
评价记录模块

职责：持久化用户满意度数据。
  - 满意：只记录次数
  - 不满意：记录完整查询过程（问题、解析、计划、检索结果、回答）
  - 默认（未评价）视为满意

数据文件：eval_records.json（与本模块同目录）
"""

import json
from datetime import datetime
from pathlib import Path

_EVAL_FILE = Path(__file__).parent / "eval_records.json"


def _load() -> dict:
    """加载评价记录文件，不存在时返回初始结构。"""
    if _EVAL_FILE.exists():
        try:
            return json.loads(_EVAL_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"satisfied_count": 0, "unsatisfied_count": 0, "unsatisfied_records": []}


def _save(data: dict) -> None:
    _EVAL_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_satisfied() -> None:
    """记录一次满意（或默认未评价）。"""
    data = _load()
    data["satisfied_count"] += 1
    _save(data)


def record_unsatisfied(result: dict) -> None:
    """
    记录一次不满意，保存完整查询过程。

    Args:
        result: agentic_rag.run() 返回的 RunResult dict
    """
    data = _load()
    data["unsatisfied_count"] += 1

    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question": result.get("question", ""),
        "answer": result.get("answer", ""),
        "query_structure": result.get("query_structure", {}),
        "plan": result.get("plan", {}),
        "executed_steps": [
            {
                "step_id": s.get("step_id"),
                "skill": s.get("skill"),
                "query": s.get("query"),
                # 只保留每步 top3 结果，避免文件过大
                "top_results": [
                    {"source": r.get("source"), "score": r.get("score"), "text": r.get("text", "")[:200]}
                    for r in s.get("results", [])[:3]
                ],
            }
            for s in result.get("executed_steps", [])
        ],
    }
    data["unsatisfied_records"].append(record)
    _save(data)


def get_stats() -> dict:
    """
    返回统计数据。

    Returns:
        {
            "satisfied_count": int,
            "unsatisfied_count": int,
            "total": int,
            "satisfaction_rate": float,   # 0.0 ~ 1.0，无记录时为 None
            "unsatisfied_records": list,
        }
    """
    data = _load()
    satisfied = data["satisfied_count"]
    unsatisfied = data["unsatisfied_count"]
    total = satisfied + unsatisfied
    return {
        "satisfied_count": satisfied,
        "unsatisfied_count": unsatisfied,
        "total": total,
        "satisfaction_rate": round(satisfied / total, 4) if total > 0 else None,
        "unsatisfied_records": data["unsatisfied_records"],
    }
