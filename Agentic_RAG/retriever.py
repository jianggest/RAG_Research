"""
Retriever 模块

职责：管理向量索引，提供检索接口供 Skill 调用。
对外接口：Retriever 类，三种检索策略（Strategy 模式）：
  - vector_search(query, top_k)   向量检索（当前实现）
  - bm25_search(query, top_k)     BM25 关键词检索（Phase 2 实现）
  - hybrid_search(query, top_k)   混合检索（Phase 2 实现）
"""

from typing import TypedDict

from config import AUGMENT_QUESTIONS, EMBEDDING_MODEL, TOP_K


class SearchResult(TypedDict):
    text: str
    source: str
    score: float
    is_table: bool


class Retriever:
    """
    向量检索器，基于 ChromaDB 实现。

    使用方式：
        retriever = Retriever(chunks)
        retriever.build_index()
        results = retriever.vector_search("A类城市住宿费", top_k=5)
    """

    def __init__(self, chunks: list) -> None:
        self._chunks = chunks
        self._collection = None

    def build_index(self) -> None:
        """建立 ChromaDB 内存向量索引。"""
        import chromadb

        # 兼容 chromadb 新旧版本：0.4+ 推荐 EphemeralClient，旧版用 Client()
        try:
            client = chromadb.EphemeralClient()
        except AttributeError:
            client = chromadb.Client()

        # 开发阶段每次重建，确保索引与文档同步
        try:
            client.delete_collection("agentic_rag")
        except Exception:
            pass

        embedding_fn = _build_embedding_fn()
        kwargs = {"name": "agentic_rag"}
        if embedding_fn:
            kwargs["embedding_function"] = embedding_fn
        self._collection = client.create_collection(**kwargs)

        if not self._chunks:
            print("[Retriever] ⚠️ 知识库为空，索引未建立")
            return

        self._collection.add(
            documents=[c["text"] for c in self._chunks],
            ids=[f"chunk_{i}" for i in range(len(self._chunks))],
            metadatas=[
                {"source": c["source"], "chunk_index": c["chunk_index"], "is_table": c["is_table"], "is_augmented": False}
                for c in self._chunks
            ],
        )
        print(f"[Retriever] 原始索引建立完成，共 {len(self._chunks)} 条")

        # 文档增强索引：为每个 chunk 生成问题，扩充同义词/近义词召回覆盖面
        if AUGMENT_QUESTIONS:
            from index_augmenter import generate_augmented_entries
            entries = generate_augmented_entries(self._chunks)
            if entries:
                self._collection.add(
                    documents=[e["document"] for e in entries],
                    ids=[f"aug_{e['chunk_hash']}_{i}" for i, e in enumerate(entries)],
                    metadatas=[{
                        "source":        e["source"],
                        "chunk_index":   e["chunk_index"],
                        "is_table":      e["is_table"],
                        "is_augmented":  True,
                        "original_text": e["original_text"],
                    } for e in entries],
                )
                print(f"[Retriever] 增强问题索引：{len(entries)} 条")

    def vector_search(
        self,
        query: str,
        top_k: int = TOP_K,
        where: dict = None,
    ) -> list[SearchResult]:
        """
        向量语义检索。
        返回按相关度降序排列的结果列表。

        Args:
            where: ChromaDB metadata 过滤条件，如 {"is_table": True}
        """
        if not self._collection or not query.strip():
            return []

        n = min(top_k, len(self._chunks))
        if n == 0:
            return []

        # 增强索引会产生多条指向同一 chunk 的条目，多取 3 倍再去重，保证去重后仍有足够结果
        n_fetch = min(n * 3, self._collection.count()) if AUGMENT_QUESTIONS else n
        kwargs = {"query_texts": [query], "n_results": n_fetch}
        if where:
            kwargs["where"] = where

        raw = self._collection.query(**kwargs)

        # 增强条目：document 是问题文本，真正的 chunk 内容在 metadata["original_text"]
        # 按 text 去重，保留每个 chunk 得分最高的那条（原始条目或增强条目均可）
        seen: dict[str, SearchResult] = {}
        for doc, meta, dist in zip(
            raw["documents"][0],
            raw["metadatas"][0],
            raw["distances"][0],
        ):
            is_augmented = meta.get("is_augmented", False)
            text = meta.get("original_text", doc) if is_augmented else doc
            score = round(max(0.0, 1 - dist), 4)
            key = text[:100]

            # 增强索引命中时打印：可以看到是哪个生成问题触发了这次匹配
            if is_augmented:
                print(f"[Retriever] 🔗 增强命中 score={score:.4f} | 问题：'{doc[:50]}' → {meta.get('source','')}")

            if key not in seen or score > seen[key]["score"]:
                seen[key] = SearchResult(
                    text=text,
                    source=meta.get("source", ""),
                    score=score,
                    is_table=bool(meta.get("is_table", False)),
                )

        results = sorted(seen.values(), key=lambda r: r["score"], reverse=True)[:top_k]
        print(f"[Retriever] vector_search top{len(results)} 分数: {[r['score'] for r in results]}")
        return results

    def bm25_search(self, query: str, top_k: int = TOP_K) -> list[SearchResult]:
        """
        BM25 关键词检索。

        适用场景：精确实体查找（城市名、职级名等），比向量检索更能命中含有该关键词的 chunk。
        依赖：pip install rank-bm25
        """
        if not self._chunks or not query.strip():
            return []

        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            print("[Retriever] ❌ 未安装 rank-bm25，运行：pip install rank-bm25")
            return []

        # jieba 词级分词；未安装时降级为字符级分词
        tokenized_corpus = [_tokenize(c["text"]) for c in self._chunks]
        tokenized_query = _tokenize(query)

        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(tokenized_query)

        # 取 top_k 个得分最高的 chunk，过滤掉得分为 0 的（完全无关）
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        return [
            SearchResult(
                text=self._chunks[i]["text"],
                source=self._chunks[i]["source"],
                score=round(float(scores[i]), 4),
            )
            for i in top_indices
            if scores[i] > 0
        ]

    def hybrid_search(self, query: str, top_k: int = TOP_K, where: dict = None) -> list[SearchResult]:
        """
        混合检索：BM25 + 向量，用 RRF（倒数排名融合）合并两路结果。

        RRF 公式：score = Σ 1 / (k + rank_i)，k=60
        两路都无结果时降级为纯向量检索。
        where: metadata 过滤条件，传给 vector_search 限定来源域，防止增强索引跨域污染。
        """
        vector_results = self.vector_search(query, top_k=top_k * 2, where=where)
        bm25_results = self.bm25_search(query, top_k=top_k * 2)

        if not bm25_results:
            return vector_results[:top_k]
        if not vector_results:
            return bm25_results[:top_k]

        return _rrf_merge(vector_results, bm25_results, top_k=top_k)

    def search(
        self,
        query: str,
        method: str,
        top_k: int = TOP_K,
        where: dict = None,
    ) -> list[SearchResult]:
        """
        统一检索入口，根据 method 分派到对应策略（策略模式）。

        Args:
            method: "vector" | "bm25" | "hybrid"
            where:  metadata 过滤条件（仅 vector 支持），如 {"is_table": True}
        """
        if method == "bm25":
            return self.bm25_search(query, top_k)
        if method == "hybrid":
            return self.hybrid_search(query, top_k, where=where)
        return self.vector_search(query, top_k, where=where)

    @property
    def chunks(self) -> list:
        """只读访问 chunk 列表，供 UI 展示调试信息。"""
        return self._chunks


# ── RRF 融合 ──────────────────────────────────────────────────────────────────

def _rrf_merge(
    results_a: list[SearchResult],
    results_b: list[SearchResult],
    top_k: int,
    k: int = 60,
) -> list[SearchResult]:
    """
    倒数排名融合（Reciprocal Rank Fusion）。

    用 text 内容作为去重键，两路分别计算排名得分后求和，取 top_k 返回。
    最终 score 字段存储 RRF 分数（值越大越相关）。
    """
    rrf_scores: dict[str, float] = {}
    text_to_result: dict[str, SearchResult] = {}

    for results in (results_a, results_b):
        for rank, result in enumerate(results):
            key = result["text"]
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            text_to_result[key] = result

    sorted_keys = sorted(rrf_scores, key=lambda k: rrf_scores[k], reverse=True)[:top_k]

    return [
        SearchResult(
            text=text_to_result[key]["text"],
            source=text_to_result[key]["source"],
            score=round(rrf_scores[key], 6),
            is_table=bool(text_to_result[key].get("is_table", False)),
        )
        for key in sorted_keys
    ]


# ── Embedding 工厂 ─────────────────────────────────────────────────────────────

def _build_embedding_fn():
    """
    根据 config.EMBEDDING_MODEL 构建 ChromaDB embedding function。

    - "default"：返回 None，ChromaDB 使用内置 all-MiniLM-L6-v2
    - 其他字符串：用 SentenceTransformer 加载对应模型（如 BAAI/bge-m3）
      依赖：pip install sentence-transformers
    """
    if EMBEDDING_MODEL == "default":
        return None

    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        print(f"[Retriever] 加载 Embedding 模型：{EMBEDDING_MODEL}")
        ef = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        print(f"[Retriever] Embedding 模型加载完成")
        return ef
    except ImportError:
        print("[Retriever] ❌ 未安装 sentence-transformers，回退到默认模型。运行：pip install sentence-transformers")
        return None


# ── 分词工具 ───────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """
    中文词级分词，供 BM25 使用。

    优先使用 jieba 词级分词（"生日福利" → ["生日", "福利"]），
    jieba 未安装时降级为字符级分词（["生", "日", "福", "利"]）。

    词级分词的优势：复合词（生日福利/年假/加班费）作为整体 token，
    IDF 值更高，BM25 能精确区分"生日福利"与其他含"福利"的 chunk。

    安装：pip install jieba
    """
    try:
        import jieba
        return list(jieba.cut(text))
    except ImportError:
        return list(text)
