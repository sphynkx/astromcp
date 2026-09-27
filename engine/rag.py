"""
Query-time RAG retrieval: FAISS + sentence-transformers, one index shard
per rag_data/<topic> corpus (built by build_index.py at the project root).

Ported from github.com/sphynkx/ycplt's utils/rag.py design (same per-corpus
sharding, same always-include/methodology-document mechanism) with one
deliberate difference: ycplt uses retrieved chunks to build a PROMPT for
its own local LLM to generate an answer from (see its build_prompt). This
module has no local model to prompt - rag_search (engine/tools.py, wired
up as an MCP tool in app.py) just returns the retrieved chunks themselves;
Claude, receiving them as a tool result, does its own reasoning over them.
There is accordingly no build_prompt-equivalent here.

If the libraries aren't installed or no index has been built yet, load()
simply returns False and rag_search reports that plainly - never a hard
failure for the rest of the service, exactly like every optional
subsystem elsewhere in this project (PDF export, photo embedding, ...).
"""

import itertools
import os
import pickle
from typing import Any, Dict, List, Optional, Tuple

from . import config

_embed_model = None
# One (faiss_index, meta_list) pair per corpus shard.
_shards: List[Tuple[Any, list]] = []
_load_error: Optional[str] = None


def _discover_index_shards() -> List[Tuple[str, str]]:
    """Every (index_path, meta_path) pair to load:
    config.RAG_INDEX_DIR/<topic-or-"_root">/faiss_index.bin + meta.pkl -
    one pair per corpus, built independently by build_index.py."""
    shards: List[Tuple[str, str]] = []
    if os.path.isdir(config.RAG_INDEX_DIR):
        for name in sorted(os.listdir(config.RAG_INDEX_DIR)):
            corpus_dir = os.path.join(config.RAG_INDEX_DIR, name)
            index_path = os.path.join(corpus_dir, "faiss_index.bin")
            meta_path = os.path.join(corpus_dir, "meta.pkl")
            if os.path.isfile(index_path) and os.path.isfile(meta_path):
                shards.append((index_path, meta_path))
    return shards


def load(force: bool = False) -> bool:
    """Loads every corpus shard found under config.RAG_INDEX_DIR, plus the
    embedding model. Lazy + cached: a no-op returning the cached result on
    every call after the first successful (or failed) one, unless
    force=True. Never raises - failures are recorded in _load_error and
    surfaced by rag_search as a plain {"available": False, "reason": ...}
    result, not an exception."""
    global _embed_model, _shards, _load_error

    if _shards and not force:
        return True
    if _load_error is not None and not force:
        return False

    shard_paths = _discover_index_shards()
    if not shard_paths:
        _load_error = (
            f"No RAG index found under {config.RAG_INDEX_DIR!r} - build one "
            f"with build_index.py first (see README.md's RAG section)."
        )
        return False

    try:
        import faiss
        from sentence_transformers import SentenceTransformer

        _embed_model = SentenceTransformer(config.RAG_EMBED_MODEL)
        loaded: List[Tuple[Any, list]] = []
        for index_path, meta_path in shard_paths:
            idx = faiss.read_index(index_path)
            with open(meta_path, "rb") as f:
                meta = pickle.load(f)
            loaded.append((idx, meta))
        _shards = loaded
        _load_error = None
        return True
    except Exception as e:
        _embed_model = None
        _shards = []
        _load_error = f"RAG unavailable: {e}"
        return False


def is_available() -> bool:
    return bool(_shards) and _embed_model is not None


def load_error() -> Optional[str]:
    return _load_error


def list_topics() -> List[str]:
    """Every topic name currently loaded (for rag_search's own error
    messages and for a caller who wants to know what's actually indexed
    before picking a topic filter)."""
    topics = set()
    for _, meta in _shards:
        for chunk in meta:
            if chunk.get("topic"):
                topics.add(chunk["topic"])
    return sorted(topics)


def _similarity_search(query: str, top_k: int, topic: Optional[str] = None) -> List[Dict[str, Any]]:
    """Plain top-k similarity lookup: embed the query, search every corpus
    shard separately, merge by score, return the global top-k. If topic is
    given, only chunks from that topic are considered - a narrower,
    explicit scope rather than the always-include expansion's broader
    "any topic touched by the top-k" logic in retrieve() below."""
    import faiss

    q_emb = _embed_model.encode([query], convert_to_numpy=True)
    faiss.normalize_L2(q_emb)

    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for idx, meta in _shards:
        if idx.ntotal == 0:
            continue
        k = min(max(top_k * 4, top_k), idx.ntotal) if topic else min(top_k, idx.ntotal)
        d, indices = idx.search(q_emb, k)
        for score, pos in zip(d[0], indices[0]):
            if 0 <= pos < len(meta):
                chunk = meta[pos]
                if topic and chunk.get("topic") != topic:
                    continue
                candidates.append((float(score), chunk))

    # Inner product on L2-normalized vectors = cosine similarity - higher is more similar.
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in candidates[:top_k]]


def retrieve(
    query: str,
    top_k: Optional[int] = None,
    topic: Optional[str] = None,
    include_methodology: bool = True,
) -> List[Dict[str, Any]]:
    """Returns a list of chunk dicts ({id, text, topic, always_include}).

    Same two-pass design as ycplt's retrieve_context: ordinary top-k
    similarity search, then - for every topic represented among those
    hits (or just `topic`, if given and include_methodology is true) -
    pull in that topic's "always_include" (methodology-suffixed document,
    see build_index.py) chunks that didn't already make the top-k cut, up
    to config.RAG_ALWAYS_INCLUDE_MAX_CHARS. A methodology document
    describes HOW to reason over facts rather than being a fact itself,
    so it often won't resemble a specific query closely enough to rank in
    plain similarity search on its own - this guarantees it surfaces
    anyway whenever its topic is relevant, the same real problem ycplt's
    own docstring documents hitting in production.
    """
    if not is_available():
        return []

    top_k = top_k or config.RAG_TOP_K
    results = _similarity_search(query, top_k, topic=topic)
    seen_ids = {chunk.get("id") for chunk in results}
    topics_hit = {chunk["topic"] for chunk in results if chunk.get("topic")}
    if topic:
        topics_hit.add(topic)

    if include_methodology and topics_hit:
        always_include_chars = 0
        for chunk in itertools.chain.from_iterable(meta for _, meta in _shards):
            if (
                chunk.get("always_include")
                and chunk.get("topic") in topics_hit
                and chunk.get("id") not in seen_ids
            ):
                if always_include_chars >= config.RAG_ALWAYS_INCLUDE_MAX_CHARS:
                    break
                results.append(chunk)
                seen_ids.add(chunk.get("id"))
                always_include_chars += len(chunk.get("text", ""))

    return results
