"""
Locally-run web search — deliberately NOT any AI provider's own
built-in search tool (no Anthropic/OpenAI/Gemini search infrastructure
involved). Chirp's own server makes these HTTP requests directly, so
this works identically regardless of which AI provider is assigned to
a feature, and doesn't depend on any AI vendor at all.

Two real, currently-working, key-free sources, used for two different
purposes — genuinely different content, not the same lookup twice:

- Wikipedia's search API: stable, official, always free, real content
  for factual/encyclopedic species and migration-pattern context.
  Confirmed directly against the live API before building this (not
  assumed) — real, relevant search results for a species query.

- Google News RSS: also free, no key, meant for programmatic
  consumption (an RSS feed, not HTML scraping) — real, current news
  headlines. Its feed license explicitly permits "rendering Google
  News results within a personal feed reader for personal,
  non-commercial use," which is exactly this use case (a self-hosted,
  personal, non-commercial application) — checked, not assumed.

What was tried and rejected, and why (worth keeping this on record so
a future change doesn't reintroduce a known-bad approach): DuckDuckGo's
HTML search endpoint returns an anti-bot challenge page immediately —
confirmed with a real request, not a guess — making it categorically
unreliable for a production feature. DuckDuckGo's Instant Answer JSON
API returns empty/placeholder content for this kind of general query —
also confirmed directly — it's built for narrow "infobox" facts
(capital of France, etc.), not general search coverage, and isn't a
fit here.

Both functions below are best-effort: any failure (network, parsing,
rate limiting) is caught and returns an empty list rather than raising
— a failed search should never be able to break Daily/Weekly Journal
generation, which is itself already an optional, best-effort feature.
"""
import logging
import httpx

logger = logging.getLogger("chirp.web_search")

# Wikimedia answers 403 to agents without a contact URL (meta.wikimedia.org/wiki/User-Agent_policy).
USER_AGENT = "ChirpBirdMonitor/1.0 (https://ourchirp.com; self-hosted bioacoustic monitor) python-httpx"


def search_wikipedia(query: str, max_results: int = 2) -> list:
    """
    Real Wikipedia article search — good for factual/encyclopedic
    context (species behavior, migration patterns, general biology).
    Returns [{"title", "snippet", "url"}, ...], snippets stripped of
    Wikipedia's own HTML <span> highlight markup (their API returns
    match-highlighting inline, which isn't useful once handed to an AI
    prompt as plain context).
    """
    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "list": "search", "srsearch": query,
                "format": "json", "srlimit": max_results, "srprop": "snippet",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=8.0,
        )
        if resp.status_code != 200:
            logger.warning("Wikipedia search returned HTTP %s for query %r: %s",
                           resp.status_code, query, resp.text[:160].replace("\n", " "))
            return []
        results = resp.json().get("query", {}).get("search", [])
        out = []
        for r in results[:max_results]:
            title = r.get("title", "")
            snippet = _strip_html_tags(r.get("snippet", ""))
            url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            out.append({"title": title, "snippet": snippet, "url": url})
        return out
    except Exception as e:
        logger.warning("Wikipedia search failed (non-fatal): %s", e)
        return []


def search_news(query: str, max_results: int = 2) -> list:
    """
    Real, current news headlines via Google News' RSS feed — genuinely
    different content from search_wikipedia (recent, dated articles,
    not encyclopedic reference content). Returns
    [{"title", "snippet", "url"}, ...] — "snippet" here is really just
    the source name (e.g. "Audubon", "Nature"), since the RSS feed's own
    description field is mostly a repeated link, not real body text;
    the title itself is where the actual information is.
    """
    try:
        resp = httpx.get(
            "https://news.google.com/rss/search",
            params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            headers={"User-Agent": USER_AGENT},
            timeout=8.0,
        )
        if resp.status_code != 200:
            logger.warning("News search returned HTTP %s for query %r", resp.status_code, query)
            return []
        return _parse_news_rss(resp.text, max_results)
    except Exception as e:
        logger.warning("News search failed (non-fatal): %s", e)
        return []


def _parse_news_rss(xml_text: str, max_results: int) -> list:
    """
    Minimal, dependency-free RSS <item> parser — this feed's structure
    is simple and stable enough (title/link/source per item) that a
    full XML library isn't needed for just these three fields, and
    avoids adding a new dependency for something this narrow.
    """
    import re
    items = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)
    out = []
    for item in items[:max_results]:
        title_match = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
        link_match = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
        source_match = re.search(r'<source[^>]*>(.*?)</source>', item, re.DOTALL)
        title = _unescape_xml(title_match.group(1)) if title_match else ""
        url = link_match.group(1).strip() if link_match else ""
        source = _unescape_xml(source_match.group(1)) if source_match else ""
        if title:
            out.append({"title": title, "snippet": source, "url": url})
    return out


def _strip_html_tags(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text)


def _unescape_xml(text: str) -> str:
    return (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&#39;", "'"))


def search_web(query: str, max_results: int = 2) -> list:
    """
    Convenience wrapper used by Daily/Weekly Journal — Wikipedia first
    (usually the more reliably relevant source for a species-name
    query), falling back to news only if Wikipedia comes up empty, so a
    single call site doesn't need to know about both sources or how to
    combine them. Callers that specifically want news (not migration/
    factual context) should call search_news() directly instead.
    """
    results = search_wikipedia(query, max_results=max_results)
    if results:
        return results
    return search_news(query, max_results=max_results)


if __name__ == "__main__":
    # Real tests against MOCKED responses (deterministic — this file's
    # docstring already documents that the live endpoints were checked
    # by hand beforehand; this test verifies the PARSING logic, not
    # network reachability, which a mocked test can't meaningfully
    # exercise anyway).
    import unittest.mock as mock

    print("=== web_search.py self-test ===\n")

    # Test 1: Wikipedia parsing with a realistic response shape
    fake_wiki_response = {
        "query": {"search": [
            {"title": "Cedar Waxwing", "pageid": 1, "snippet": "The <span class=\"searchmatch\">Cedar Waxwing</span> is a member of the family Bombycillidae."},
            {"title": "Bird migration", "pageid": 2, "snippet": "Bird migration is a seasonal movement."},
        ]}
    }
    with mock.patch("httpx.get") as fake_get:
        fake_get.return_value = mock.Mock(status_code=200, json=lambda: fake_wiki_response)
        results = search_wikipedia("Cedar Waxwing migration", max_results=2)
    assert len(results) == 2
    assert results[0]["title"] == "Cedar Waxwing"
    assert "<span" not in results[0]["snippet"], "HTML tags should be stripped from the snippet"
    assert results[0]["snippet"] == "The Cedar Waxwing is a member of the family Bombycillidae."
    assert results[0]["url"] == "https://en.wikipedia.org/wiki/Cedar_Waxwing"
    print("Test 1 PASS: Wikipedia search parses real response shape correctly, HTML tags stripped")

    # Test 2: Wikipedia HTTP failure -> empty list, not an exception
    with mock.patch("httpx.get") as fake_get:
        fake_get.return_value = mock.Mock(status_code=429)
        results = search_wikipedia("anything", max_results=2)
    assert results == []
    print("Test 2 PASS: non-200 Wikipedia response returns [] rather than raising")

    # Test 3: News RSS parsing with a realistic minimal feed
    fake_rss = """<?xml version="1.0"?><rss><channel>
      <item><title>Bird migration hits record numbers this fall</title>
            <link>https://news.example.com/article1</link>
            <source url="https://example.com">Example News</source></item>
      <item><title>New study on Cedar Waxwing range shifts</title>
            <link>https://news.example.com/article2</link>
            <source url="https://example.com">Audubon</source></item>
    </channel></rss>"""
    with mock.patch("httpx.get") as fake_get:
        fake_get.return_value = mock.Mock(status_code=200, text=fake_rss)
        results = search_news("bird migration", max_results=2)
    assert len(results) == 2
    assert results[0]["title"] == "Bird migration hits record numbers this fall"
    assert results[0]["snippet"] == "Example News"
    assert results[1]["title"] == "New study on Cedar Waxwing range shifts"
    print("Test 3 PASS: News RSS parsing correctly extracts title/source/link from real feed structure")

    # Test 4: search_web() falls back to news when Wikipedia is empty
    with mock.patch("httpx.get") as fake_get:
        def side_effect(url, **kwargs):
            if "wikipedia" in url:
                return mock.Mock(status_code=200, json=lambda: {"query": {"search": []}})
            return mock.Mock(status_code=200, text=fake_rss)
        fake_get.side_effect = side_effect
        results = search_web("some obscure query with no wiki article", max_results=2)
    assert len(results) == 2
    assert results[0]["title"] == "Bird migration hits record numbers this fall"
    print("Test 4 PASS: search_web() correctly falls back to news when Wikipedia returns nothing")

    print("\nALL TESTS PASS")
