from __future__ import annotations

import html as html_lib
import re
from typing import Any
from urllib.parse import quote_plus, unquote

import httpx


def _browser_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "lv,en-US;q=0.8,en;q=0.7",
    }


async def _search_google_html(client: httpx.AsyncClient, q: str, *, limit: int = 6) -> list[dict[str, str]]:
    """Google HTML rezultāti (bez API atslēgas)."""
    out: list[dict[str, str]] = []
    try:
        r = await client.get(
            "https://www.google.com/search",
            params={"q": q, "hl": "lv", "num": str(max(limit, 5))},
        )
        if r.status_code >= 400:
            return out
        text = r.text
        # Klasiskie rezultātu bloki
        for m in re.finditer(
            r'<a[^>]+href="/(?:url\?q=|url\?.*?q=)(https?://[^"&]+)[^"]*"[^>]*>.*?'
            r'(?:<h3[^>]*>(.*?)</h3>|<div[^>]*role="heading"[^>]*>(.*?)</div>)',
            text,
            re.I | re.S,
        ):
            url = unquote(m.group(1))
            title = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(2) or m.group(3) or "")).strip()
            if not url.startswith("http") or "google." in url.lower():
                continue
            out.append({"title": (title or url)[:120], "url": url, "snippet": (title or "")[:400], "engine": "google"})
            if len(out) >= limit:
                break
        # Fallback: vienkārši /url?q=
        if len(out) < 2:
            for m in re.finditer(r'/url\?q=(https?://[^&"]+)&', text):
                url = unquote(m.group(1))
                if "google." in url.lower() or "webcache" in url.lower():
                    continue
                if any(x["url"] == url for x in out):
                    continue
                out.append({"title": url.split("/")[2][:80], "url": url, "snippet": "", "engine": "google"})
                if len(out) >= limit:
                    break
    except Exception:  # noqa: BLE001
        return out
    return out


async def _search_bing_html(client: httpx.AsyncClient, q: str, *, limit: int = 5) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        r = await client.get("https://www.bing.com/search", params={"q": q, "setlang": "lv"})
        if r.status_code >= 400:
            return out
        text = r.text
        for m in re.finditer(
            r'<li class="b_algo".*?<h2[^>]*>\s*<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>.*?'
            r'(?:<p>|class="b_caption".*?<p[^>]*>)(.*?)</p>',
            text,
            re.I | re.S,
        ):
            url = html_lib.unescape(m.group(1)).strip()
            title = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
            snip = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()
            if url.startswith("http"):
                out.append({"title": title[:120], "url": url, "snippet": snip[:400], "engine": "bing"})
            if len(out) >= limit:
                break
    except Exception:  # noqa: BLE001
        return out
    return out


async def web_search(query: str, *, max_results: int = 5) -> dict[str, Any]:
    """Meklē internetā: Google + Bing + DuckDuckGo (ne tikai DDG)."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "Tukšs vaicājums", "results": []}

    results: list[dict[str, str]] = []
    abstract = ""
    engines_used: list[str] = []
    headers = _browser_headers()

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
            # 1) Google (lietotāja prasība)
            g = await _search_google_html(client, q, limit=max_results)
            if g:
                engines_used.append("google")
                results.extend(g)

            # 2) Bing, ja Google maz rezultātu
            if len(results) < 3:
                b = await _search_bing_html(client, q, limit=max_results)
                if b:
                    engines_used.append("bing")
                    results.extend(b)

            # 3) DuckDuckGo Instant Answer + HTML (papildu fakti)
            r = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": q, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            if r.status_code < 400:
                data = r.json()
                abstract = str(data.get("AbstractText") or "").strip()
                abs_url = str(data.get("AbstractURL") or "").strip()
                if abstract:
                    engines_used.append("duckduckgo")
                    results.append(
                        {
                            "title": str(data.get("Heading") or q)[:120],
                            "url": abs_url or "https://duckduckgo.com/",
                            "snippet": abstract[:500],
                            "engine": "duckduckgo",
                        }
                    )
                for topic in (data.get("RelatedTopics") or [])[:5]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append(
                            {
                                "title": str(topic.get("Text") or "")[:80],
                                "url": str(topic.get("FirstURL") or ""),
                                "snippet": str(topic.get("Text") or "")[:400],
                                "engine": "duckduckgo",
                            }
                        )

            if len([x for x in results if "duckduckgo.com" not in (x.get("url") or "")]) < 2:
                html = await client.get(f"https://html.duckduckgo.com/html/?q={quote_plus(q)}")
                if html.status_code < 400:
                    engines_used.append("duckduckgo-html")
                    text = html.text
                    for m in re.finditer(
                        r'uddg=([^&"]+).*?class="result__a"[^>]*>(.*?)</a>.*?'
                        r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)',
                        text,
                        re.I | re.S,
                    ):
                        url = unquote(m.group(1))
                        title = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
                        snip = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()
                        if url.startswith("http") and "duckduckgo.com" not in url.lower():
                            results.append(
                                {
                                    "title": title[:120],
                                    "url": url,
                                    "snippet": snip[:400],
                                    "engine": "duckduckgo",
                                }
                            )
                        if len(results) >= max_results + 6:
                            break
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "results": [], "query": q}

    # dedupe by url — prioritāte īstiem avotiem (ne DDG stub)
    seen: set[str] = set()
    primary: list[dict[str, str]] = []
    stubs: list[dict[str, str]] = []
    for item in results:
        u = item.get("url") or ""
        if not u or u in seen:
            continue
        seen.add(u)
        if "duckduckgo.com" in u.lower():
            stubs.append(item)
        else:
            primary.append(item)
    uniq = (primary + stubs)[:max_results]

    return {
        "ok": True,
        "query": q,
        "abstract": abstract,
        "results": uniq,
        "engines": engines_used or ["google"],
        "search_url": f"https://www.google.com/search?q={quote_plus(q)}",
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
                text = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", text)
                text = re.sub(r"(?s)<[^>]+>", " ", text)
                text = html_lib.unescape(text)
                text = re.sub(r"\s+", " ", text).strip()
            else:
                text = html_lib.unescape(text)
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


def _query_tokens(query: str) -> set[str]:
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "kas", "ir", "par",
        "kā", "vai", "no", "uz", "ar", "un", "to", "tie", "tā", "šie", "www",
        "com", "org", "http", "https", "html", "sameklē", "iemācies", "izskaidro",
    }
    toks = re.findall(r"[a-zA-ZāčēģīķļņšūžĀČĒĢĪĶĻŅŠŪŽ0-9]{3,}", (query or "").lower())
    return {t for t in toks if t not in stop}


def _score_text_vs_query(text: str, tokens: set[str]) -> float:
    """Punktē pēc satura vārdiem — ne tikai pēc nosaukuma atkārtošanas."""
    if not text or not tokens:
        return 0.0
    low = text.lower()
    words = re.findall(r"[a-zA-ZāčēģīķļņšūžĀČĒĢĪĶĻŅŠŪŽ0-9]{3,}", low)
    if not words:
        return 0.0
    hits = sum(1 for t in tokens if t in low)
    # Bonus, ja teikumā ir skaidrojoši vārdi (saturs, ne tikai vārds+uzvārds)
    explain = (
        " ir ", " was ", " were ", " born ", " dzimis", " strādā", " known",
        " company", " uzņēmum", " developer", " programm", " founded", " works",
        " living", " latvia", " latvij", " linkedin", " wikipedia",
    )
    explain_bonus = 0.35 if any(e in low for e in explain) else 0.0
    # Sodīt ļoti īsus «tikai nosaukums» gabalus
    length_factor = min(1.0, len(words) / 12.0)
    coverage = hits / max(1, len(tokens))
    return coverage * 2.0 + explain_bonus + length_factor * 0.5


def extract_relevant_passages(
    text: str,
    query: str,
    *,
    max_passages: int = 4,
    max_chars: int = 420,
) -> list[str]:
    """Izvelk no lapas teksta teikumus pēc satura, nevis pēc virsraksta."""
    raw = (text or "")
    # Wiki / HTML atkritumi
    raw = re.sub(r"\[\s*edit\s*\]", " ", raw, flags=re.I)
    raw = re.sub(r"\[\s*\d+\s*\]", " ", raw)
    raw = re.sub(r"\\n|\n+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if len(raw) < 40:
        return []
    tokens = _query_tokens(query)
    # Sadalām teikumos / rindās
    parts = re.split(r"(?<=[.!?])\s+|\n+", raw)
    scored: list[tuple[float, str]] = []
    seen_norm: set[str] = set()
    for part in parts:
        sent = part.strip(" •-|\"'")
        if len(sent) < 40 or len(sent) > 600:
            continue
        # Izlaiž navigācijas / cookie / wiki chrome muļķības
        low = sent.lower()
        if any(
            b in low
            for b in (
                "cookie", "privacy policy", "subscribe", "sign in", "log in",
                "javascript", "enable cookies", "all rights reserved",
                "click here", "buy now", "download now", "might also work",
                "too minor to mention", "advertisement", "related searches",
                "life and education", "see also", "external links",
                "references", "prevented to work", "might be a bit wrong",
            )
        ):
            continue
        # Atmet vājus / meta teikumos bez īsta satura
        if len(re.findall(r"[a-zA-Zāčēģīķļņšūž]{3,}", low)) < 8:
            continue
        score = _score_text_vs_query(sent, tokens)
        if score < 0.7:
            continue
        norm = re.sub(r"\W+", "", sent.lower())[:80]
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        if len(sent) > max_chars:
            sent = sent[:max_chars].rsplit(" ", 1)[0] + "…"
        scored.append((score, sent))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:max_passages]]


def _rank_search_results(results: list[dict[str, str]], query: str) -> list[dict[str, str]]:
    """Prioritizē rezultātus pēc snippet/satura, ne tikai nosaukuma līdzības."""
    tokens = _query_tokens(query)
    ranked: list[tuple[float, dict[str, str]]] = []
    for item in results:
        title = str(item.get("title") or "")
        snip = str(item.get("snippet") or "")
        url = str(item.get("url") or "")
        # Nosaukums vien pats — zems svars; snippet/saturs — augsts
        title_score = _score_text_vs_query(title, tokens) * 0.35
        snip_score = _score_text_vs_query(snip, tokens) * 1.4
        # Preferē īstus avotus; sodīt DDG stub / category URL
        host_bonus = 0.0
        low_url = url.lower()
        if "wikipedia.org" in low_url:
            host_bonus += 0.8
        elif any(h in low_url for h in ("linkedin.com", "github.com", "britannica", ".edu", ".gov")):
            host_bonus += 0.45
        elif "duckduckgo.com" in low_url:
            host_bonus -= 1.2  # stub / related-topic, ne īsta lapa
        # Sodīt, ja snippet gandrīz = title (tukšs saturs)
        if snip and title and snip.lower()[:40] == title.lower()[:40]:
            snip_score *= 0.4
        ranked.append((title_score + snip_score + host_bonus, item))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in ranked]


async def deep_research(
    query: str,
    *,
    max_results: int = 5,
    max_pages: int = 3,
    max_chars_per_page: int = 8000,
) -> dict[str, Any]:
    """
    Dziļāka meklēšana: DDG + lapu saturs (ne tikai nosaukumi).
    Atgriež faktus no avotu teksta, sakārtotus pēc satura atbilstības.
    """
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "Tukšs vaicājums", "facts": [], "results": [], "pages": []}

    search = await web_search(q, max_results=max_results)
    results = list(search.get("results") or [])
    ranked = _rank_search_results(results, q)

    facts: list[str] = []
    pages: list[dict[str, Any]] = []
    abstract = str(search.get("abstract") or "").strip()
    if abstract:
        for passage in extract_relevant_passages(abstract, q, max_passages=2) or [abstract[:400]]:
            if passage not in facts:
                facts.append(passage)

    def _fetchable(u: str) -> bool:
        lu = (u or "").lower()
        if not u.startswith("http"):
            return False
        # Wikipedia HTML → chaos; wiki API jau chat.py. DDG stub → nav satura.
        if "wikipedia.org" in lu or "duckduckgo.com" in lu:
            return False
        return True

    # Paralēli ielādē top lapas (saturs, ne virsraksts)
    fetch_targets = [r for r in ranked if _fetchable(str(r.get("url") or ""))][:max_pages]
    # Fallback: ja nav īsto URL — mēģina wiki (labāk kaut kas)
    if not fetch_targets:
        fetch_targets = [
            r for r in ranked
            if str(r.get("url") or "").startswith("http")
            and "duckduckgo.com" not in str(r.get("url") or "").lower()
        ][:max_pages]

    async def _one(item: dict[str, str]) -> dict[str, Any]:
        url = str(item.get("url") or "")
        fetched = await http_fetch(url, max_chars=max_chars_per_page)
        return {"item": item, "fetched": fetched}

    fetched_list: list[dict[str, Any]] = []
    if fetch_targets:
        import asyncio

        try:
            fetched_list = await asyncio.wait_for(
                asyncio.gather(*[_one(it) for it in fetch_targets], return_exceptions=True),
                timeout=10.0,
            )
        except Exception:  # noqa: BLE001
            fetched_list = []

    for entry in fetched_list:
        if isinstance(entry, Exception) or not isinstance(entry, dict):
            continue
        item = entry.get("item") or {}
        fetched = entry.get("fetched") or {}
        url = str(item.get("url") or fetched.get("url") or "")
        title = str(item.get("title") or "").strip()
        snip = str(item.get("snippet") or "").strip()
        page_text = ""
        if isinstance(fetched, dict) and fetched.get("ok"):
            page_text = str(fetched.get("text") or "")
            pages.append(
                {
                    "url": url,
                    "title": title,
                    "chars": len(page_text),
                    "status": fetched.get("status"),
                }
            )
        # 1) no lapas satura
        passages = extract_relevant_passages(page_text, q, max_passages=3) if page_text else []
        # 2) fallback — snippet, ja lapa nedeva saturu
        if not passages and snip and len(snip) >= 40:
            # Neņem snippet, ja tas ir tikai nosaukuma atkārtojums
            if _score_text_vs_query(snip, _query_tokens(q)) >= 0.55:
                passages = [snip[:400]]
        for p in passages:
            chunk = p.strip()
            # Noņem tikai «Title - rest» echo, ne teikuma subjektu («Python is…»)
            if title and chunk.lower().startswith(title.lower()[: min(24, len(title))]):
                after = chunk[len(title) :] if len(chunk) >= len(title) else ""
                if after[:2].lstrip()[:1] in {"-", "|", ":", "·", "—"}:
                    rest = after.lstrip(" -|:·—.")
                    if len(rest) >= 40:
                        chunk = rest
            if chunk and chunk not in facts and len(chunk) >= 40:
                facts.append(chunk)

    # Ja lapas neko nedeva — ņem labākos snippetus (joprojām pēc satura ranga)
    if len(facts) < 2:
        for item in ranked[:4]:
            snip = str(item.get("snippet") or "").strip()
            title = str(item.get("title") or "").strip()
            if len(snip) < 40:
                continue
            if _score_text_vs_query(snip, _query_tokens(q)) < 0.4:
                continue
            # Nevienkārši «Title. Title» paste
            if title and snip.lower().startswith(title.lower()[: min(24, len(title))]):
                continue
            if snip not in facts:
                facts.append(snip[:400])
            if len(facts) >= 4:
                break

    return {
        "ok": bool(facts) or bool(search.get("ok")),
        "query": q,
        "abstract": abstract,
        "results": ranked,
        "pages": pages,
        "facts": facts[:8],
        "search_url": search.get("search_url")
        or f"https://www.google.com/search?q={quote_plus(q)}",
        "engines": search.get("engines") or [],
        "error": search.get("error"),
    }
