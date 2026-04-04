"""Ollama HTTP client (LLM feature)."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Optional

from pbsbot import state

log = logging.getLogger("pbs_bot")


def generate(prompt: str) -> Optional[str]:
    """POST to Ollama /api/generate (non-streaming)."""
    s = state.settings
    assert s is not None
    if not s.ollama_base_url:
        return None
    url = f"{s.ollama_base_url}/api/generate"
    payload = json.dumps(
        {"model": s.ollama_model, "prompt": prompt, "stream": False}
    ).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=s.ollama_timeout) as resp:
            result = json.loads(resp.read().decode())
        out = (result.get("response") or "").strip()
        return out or None
    except urllib.error.URLError as e:
        log.warning("Ollama request failed (%s): %s", url, e)
        return None
    except Exception as e:
        log.warning("Ollama request error: %s", e)
        return None


def _extract_json_object(text: str) -> Optional[dict]:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def clarify_query_with_llm(user_query: str) -> dict:
    s = state.settings
    assert s is not None
    fallback = {
        "clarified_for_user": user_query,
        "query_for_search": user_query,
    }
    if not s.ollama_base_url:
        log.info("clarify_query_with_llm: OLLAMA_BASE_URL empty, using fallback")
        return fallback

    prompt = (
        "You rewrite user questions before retrieval. Reply with ONLY a JSON object (no markdown fences), "
        'with exactly these keys: "clarified_for_user", "query_for_search". Use English only. '
        "clarified_for_user: a polite confirmation sentence. "
        "query_for_search: concise keywords for vector search; include specific project or show titles "
        "from the user message verbatim when present.\n\n"
        f"Original user question:\n{user_query}"
    )

    t0 = time.perf_counter()
    log.info("clarify_query_with_llm: calling Ollama model=%s", s.ollama_model)
    content = generate(prompt)
    parsed = _extract_json_object(content or "") if content else None
    if not parsed:
        log.warning("clarify_query_with_llm: bad or empty JSON from Ollama, using fallback")
        return fallback

    clarified_for_user = str(parsed.get("clarified_for_user", user_query) or user_query).strip()
    query_for_search = str(parsed.get("query_for_search", user_query) or user_query).strip()
    if not clarified_for_user:
        clarified_for_user = user_query
    if not query_for_search:
        query_for_search = user_query

    log.info("clarify_query_with_llm: OK in %.2fs", time.perf_counter() - t0)
    return {
        "clarified_for_user": clarified_for_user,
        "query_for_search": query_for_search,
    }


def synthesize_answer_with_llm(
    original_question: str,
    clarified_interpretation: str,
    context_chunks: list[str],
) -> str:
    s = state.settings
    assert s is not None
    if not context_chunks:
        return (
            "I could not find relevant information in the knowledge base for that question."
        )

    log.info(
        "synthesize_answer_with_llm: chunks=%s ollama_base=%s",
        len(context_chunks),
        bool(s.ollama_base_url),
    )

    context = "\n\n---\n\n".join(
        f"[Chunk {i + 1}]\n{chunk}" for i, chunk in enumerate(context_chunks)
    )

    prompt = (
        "You are a helpful assistant for PBS Wisconsin internal project data. "
        "Answer the user's question using ONLY the provided context chunks below. "
        "If the context is insufficient, say so clearly and suggest what might be missing. "
        "Be concise and accurate. Use English only.\n\n"
        f"Original user question:\n{original_question}\n\n"
        f"Clarified interpretation (used for retrieval):\n{clarified_interpretation}\n\n"
        f"Context from knowledge base:\n{context}"
    )

    t0 = time.perf_counter()
    text = generate(prompt)
    if text:
        log.info(
            "synthesize_answer_with_llm: Ollama OK in %.2fs, out_len=%s",
            time.perf_counter() - t0,
            len(text),
        )
        return text

    joined = "\n\n---\n\n".join(
        f"[Source {i + 1}]\n{chunk}" for i, chunk in enumerate(context_chunks)
    )
    return (
        "Here is what I found in the knowledge base (Ollama unreachable — showing raw chunks). "
        "Start your VPN/SSH tunnel to localhost:11434 if you expect a summarized answer:\n\n"
        + joined
    )
