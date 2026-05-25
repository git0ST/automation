import httpx
from html.parser import HTMLParser


class _TrendingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.repos = []
        self._in_h2 = False
        self._in_p = False
        self._current = {}
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article" and "Box-row" in attrs.get("class", ""):
            self._current = {}
        if tag == "h2" and "h3" in attrs.get("class", ""):
            self._in_h2 = True
        if tag == "a" and self._in_h2:
            href = attrs.get("href", "")
            if href.count("/") == 2:
                self._current["url"] = "https://github.com" + href
                self._current["title"] = href.lstrip("/")
        if tag == "p" and "col-9" in attrs.get("class", ""):
            self._in_p = True

    def handle_endtag(self, tag):
        if tag == "h2":
            self._in_h2 = False
        if tag == "p" and self._in_p:
            self._in_p = False
        if tag == "article" and self._current.get("url"):
            self.repos.append(self._current.copy())
            self._current = {}

    def handle_data(self, data):
        if self._in_p and data.strip():
            self._current["description"] = data.strip()


async def fetch_github_trending(language: str = "", limit: int = 10) -> list[dict]:
    url = f"https://github.com/trending/{language}"
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
        try:
            html = (await client.get(url)).text
        except Exception:
            return []

    parser = _TrendingParser()
    parser.feed(html)

    return [
        {
            "id":      f"github-{r['title'].replace('/', '-')}",
            "source":  "github",
            "title":   r.get("title", ""),
            "url":     r.get("url", ""),
            "score":   0,
            "preview": r.get("description", "No description"),
            "tags":    ["code", "opensource"],
        }
        for r in parser.repos[:limit]
        if r.get("url")
    ]
