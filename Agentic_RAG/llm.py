"""
LLM 调用模块

职责：封装对 LLM 的调用，对上层屏蔽具体实现（Ollama / OpenAI / None）。
对外接口：call_llm(prompt) -> str
"""

from config import (
    LLM_BACKEND,
    OLLAMA_MODEL,
    OLLAMA_OPTIONS,
    OPENAI_BASE_URL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_OPTIONS,
)


def call_llm(prompt: str) -> str:
    """
    调用 LLM，返回文本响应。
    LLM 不可用或 backend 为 none 时返回空字符串。
    """
    if LLM_BACKEND == "none":
        return ""
    if LLM_BACKEND == "ollama":
        return _call_ollama(prompt)
    if LLM_BACKEND == "openai":
        return _call_openai(prompt)
    return ""


def _call_ollama(prompt: str) -> str:
    try:
        import ollama
        print(f"[LLM] 调用 Ollama model={OLLAMA_MODEL} ...")
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options=OLLAMA_OPTIONS,
            think=False           # 关闭 Thinking 模式，RAG 场景不需要深度推理

        )
        print("[LLM] Ollama 响应完成")
        return response["message"]["content"].strip()
    except ImportError:
        print("[LLM] ❌ 未安装 ollama 库，运行：pip install ollama")
        return ""
    except Exception as e:
        print(f"[LLM] ❌ Ollama 调用失败: {e}")
        return ""


def _call_openai(prompt: str) -> str:
    try:
        from openai import OpenAI
        print(f"[LLM] 调用 OpenAI model={OPENAI_MODEL} base_url={OPENAI_BASE_URL} ...")
        client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            **OPENAI_OPTIONS,
        )
        print("[LLM] OpenAI 响应完成")
        return (response.choices[0].message.content or "").strip()
    except ImportError:
        print("[LLM] ❌ 未安装 openai 库，运行：pip install openai")
        return ""
    except Exception as e:
        print(f"[LLM] ❌ OpenAI 调用失败: {e}")
        return ""
