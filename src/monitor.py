from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


SOURCE_URL = "https://fxtwitter.com/thsottiaux/feed.xml?count=50"
ACCOUNT_URL = "https://x.com/thsottiaux"
STATE_PATH = Path("state/seen.json")

KEYWORDS = (
    "usage limit",
    "usage limits",
    "rate limit",
    "quota",
    "five-hour",
    "5-hour",
    "weekly limit",
    "temporarily paused",
    "restore the five-hour",
    "restored",
    "limits have been reset",
    "limit reset",
    "limits reset",
)


@dataclass
class Post:
    text: str
    published: str
    url: str
    fingerprint: str


def fetch_page() -> str:
    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; TiboCodexMonitor/1.0)",
            "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_posts(page: str) -> list[Post]:
    root = ElementTree.fromstring(page)
    posts: list[Post] = []
    for item in root.findall("./channel/item"):
        description = item.findtext("description", default="")
        # Ignore an embedded quoted post so it cannot create a false keyword match.
        description = re.split(r"<blockquote\b", description, maxsplit=1, flags=re.I)[0]
        description = re.sub(r"<br\s*/?>", "\n", description, flags=re.I)
        description = re.sub(r"<[^>]+>", " ", description)
        text = re.sub(r"\s+", " ", html.unescape(description)).strip()
        if not text:
            continue
        url = (item.findtext("link", default=ACCOUNT_URL) or ACCOUNT_URL).strip()
        published = (item.findtext("pubDate", default="unknown time") or "unknown time").strip()
        fingerprint = hashlib.sha256(url.encode("utf-8")).hexdigest()
        posts.append(Post(text=text, published=published, url=url, fingerprint=fingerprint))

    # Preserve feed order while removing duplicates.
    unique: dict[str, Post] = {}
    for post in posts:
        unique.setdefault(post.fingerprint, post)
    return list(unique.values())


def is_relevant(post: Post) -> bool:
    text = post.text.lower()
    return any(keyword in text for keyword in KEYWORDS)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"seen": [], "bootstrapped": False}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return {"seen": list(data.get("seen", [])), "bootstrapped": bool(data.get("bootstrapped", False))}
    except (OSError, json.JSONDecodeError):
        return {"seen": [], "bootstrapped": False}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"seen": state["seen"][-200:], "bootstrapped": state["bootstrapped"]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def send_wecom(posts: list[Post]) -> None:
    webhook = os.environ.get("WECOM_WEBHOOK_URL", "").strip()
    if not webhook:
        raise RuntimeError("WECOM_WEBHOOK_URL is not configured")
    lines = ["**Tibo 有新的 Codex 使用限制/重置相关动态**", ""]
    for post in posts[:3]:
        text = post.text if len(post.text) <= 900 else post.text[:897] + "..."
        lines.extend([f"- {post.published}：{text}", f"  [查看原帖]({post.url})", ""])
    if len(posts) > 3:
        lines.append(f"另有 {len(posts) - 3} 条匹配动态，请打开账号查看。")
    payload = json.dumps({"msgtype": "markdown", "markdown": {"content": "\n".join(lines)}}).encode("utf-8")
    request = Request(webhook, data=payload, method="POST", headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        result = response.read().decode("utf-8", errors="replace")
    if '"errcode":0' not in result.replace(" ", ""):
        raise RuntimeError(f"WeCom rejected the message: {result[:300]}")


def main() -> int:
    try:
        page = fetch_page()
        posts = extract_posts(page)
    except (HTTPError, URLError, TimeoutError, OSError, ElementTree.ParseError) as exc:
        print(f"Source fetch failed: {exc}", file=sys.stderr)
        return 1

    state = load_state()
    seen = set(state["seen"])
    current_ids = [post.fingerprint for post in posts]

    # First successful run establishes a baseline without sending old alerts.
    if not state["bootstrapped"]:
        state["seen"] = current_ids[-200:]
        state["bootstrapped"] = True
        save_state(state)
        print(f"Bootstrapped {len(posts)} visible posts; no notification sent.")
        return 0

    new_posts = [post for post in posts if post.fingerprint not in seen]
    relevant = [post for post in new_posts if is_relevant(post)]
    if relevant:
        send_wecom(relevant)
        print(f"Sent {len(relevant)} relevant update(s).")
    else:
        print(f"No relevant update. New posts seen: {len(new_posts)}.")

    state["seen"] = list(dict.fromkeys((state["seen"] + current_ids)[-200:]))
    save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
