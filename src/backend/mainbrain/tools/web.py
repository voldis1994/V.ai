from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

import httpx


async def web_search(query: str, *, max_results: int = 5) -> dict[str, Any]:
    """Meklē internetā (DuckDuckGo Instant Answer + HTML rezultāti)."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "Tukšs vaicājums", "results": []}

    results: list[dict[str, str]] = []
    abstract = ""
    headers = {
        "User-Agent": "MainBrainOS/1.0 (+local; full_access)",
        "Accept": "application/json,text/html",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
            # 1) Instant Answer API
            r = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": q, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            if r.status_code < 400:
                data = r.json()
                abstract = str(data.get("AbstractText") or "").strip()
                abs_url = str(data.get("AbstractURL") or "").strip()
                if abstract:
                    results.append(
                        {
                            "title": str(data.get("Heading") or q)[:120],
                            "url": abs_url or "https://duckduckgo.com/",
                            "snippet": abstract[:500],
                        }
                    )
                for topic in (data.get("RelatedTopics") or [])[:8]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append(
                            {
                                "title": str(topic.get("Text") or "")[:80],
                                "url": str(topic.get("FirstURL") or ""),
                                "snippet": str(topic.get("Text") or "")[:400],
                            }
                        )
                    elif isinstance(topic, dict) and topic.get("Topics"):
                        for sub in topic["Topics"][:3]:
                            if isinstance(sub, dict) and sub.get("Text"):
                                results.append(
                                    {
                                        "title": str(sub.get("Text") or "")[:80],
                                        "url": str(sub.get("FirstURL") or ""),
                                        "snippet": str(sub.get("Text") or "")[:400],
                                    }
                                )

            # 2) HTML fallback, ja Instant Answer tukšs
            if len(results) < 2:
                html = await client.get(
                    f"https://html.duckduckgo.com/html/?q={quote_plus(q)}",
                )
                if html.status_code < 400:
                    text = html.text
                    # vienkārši result bloki
                    for m in re.finditer(
                        r'uddg=([^&"]+).*?class="result__a"[^>]*>(.*?)</a>.*?'
                        r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)',
                        text,
                        re.I | re.S,
                    ):
                        from urllib.parse import unquote

                        url = unquote(m.group(1))
                        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                        snip = re.sub(r"<[^>]+>", "", m.group(3)).strip()
                        if url.startswith("http"):
                            results.append(
                                {"title": title[:120], "url": url, "snippet": snip[:400]}
                            )
                        if len(results) >= max_results:
                            break
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "results": [], "query": q}

    # dedupe by url
    seen: set[str] = set()
    uniq: list[dict[str, str]] = []
    for item in results:
        u = item.get("url") or ""
        if u in seen:
            continue
        seen.add(u)
        uniq.append(item)
        if len(uniq) >= max_results:
            break

    return {
        "ok": True,
        "query": q,
        "abstract": abstract,
        "results": uniq,
        "search_url": f"https://duckduckgo.com/?q={quote_plus(q)}",
    }


async def http_fetch(url: str, *, max_chars: int = 12000) -> dict[str, Any]:
    """Ielādē URL saturu (teksts/HTML → attīrīts teksts)."""
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return {"ok": False, "error": "URL jāsākas ar http:// vai https://"}
    headers = {"User-Agent": "MainBrainOS/1.0 (+local; full_access)"}
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(u)
            ctype = resp.headers.get("content-type", "")
            text = resp.text
            if "html" in ctype.lower():
                text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
                text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
                text = re.sub(r"(?s)<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
            return {
                "ok": resp.status_code < 400,
                "status": resp.status_code,
                "url": str(resp.url),
                "content_type": ctype,
                "text": text[:max_chars],
            }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "url": u}


def format_search_for_llm(payload: dict[str, Any]) -> str:
    if not payload.get("ok"):
        return f"Meklēšana neizdevās: {payload.get('error')}"
    lines = [f"Vaicājums: {payload.get('query')}"]
    if payload.get("abstract"):
        lines.append(f"Kopsavilkums: {payload['abstract']}")
    for i, r in enumerate(payload.get("results") or [], 1):
        lines.append(f"{i}. {r.get('title')}\n   {r.get('url')}\n   {r.get('snippet')}")
    if not payload.get("results") and not payload.get("abstract"):
        lines.append("Rezultātu nav.")
    return "\n".join(lines)
