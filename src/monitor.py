from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOURCE_URL = "https://mobile.twstalker.com/thsottiaux"
ACCOUNT_URL = "https://x.com/thsottiaux"
STATE_PATH = Path("state/seen.json")

TIME_RE = re.compile(
    r"^(?:\d+\s+(?:second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago|"
    r"(?:just now|yesterday))$",
    re.IGNORECASE,
)
AUTHOR_RE = re.compile(r"^Tibo\s+@thsottiaux$", re.IGNORECASE)

KEYWORDS = (
    "reset",
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
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def visible_lines(page: str) -> list[str]:
    # The mirror is server-rendered. This deliberately uses a small, dependency-free
    # parser so the scheduled job does not need a third-party Python package.
    page = re.sub(r"<script\b[^>]*>.*?</script>", " ", page, flags=re.I | re.S)
    page = re.sub(r"<style\b[^>]*>.*?</style>", " ", page, flags=re.I | re.S)
    page = re.sub(r"<br\s*/?>", "\n", page, flags=re.I)
    page = re.sub(r"</(?:p|div|li|article|section|h[1-6])\s*>", "\n", page, flags=re.I)
    page = re.sub(r"<[^>]+>", " ", page)
    page = html.unescape(page).replace("\r", "")
    lines = []
    for line in page.split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return lines


def extract_posts(page: str) -> list[Post]:
    lines = visible_lines(page)
    starts = [i for i, line in enumerate(lines) if AUTHOR_RE.match(line)]
    posts: list[Post] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        block = lines[start + 1 : end]
        time_index = next((i for i, line in enumerate(block) if TIME_RE.match(line)), None)
        if time_index is None:
            continue
        published = block[time_index]
        body: list[str] = []
        for line in block[time_index + 1 :]:
            if line.lower() in {"view details", "load more"}:
                break
            # Engagement counts are exposed as one number per line by the mirror.
            if body and re.fullmatch(r"[\d,.]+[KMB]?", line, re.IGNORECASE):
                continue
            if line.startswith("@"):  # Keep the post body, but omit reply handles.
                continue
            body.append(line)
        text = " ".join(body).strip()
        if not text:
            continue
        fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
        posts.append(Post(text=text, published=published, url=ACCOUNT_URL, fingerprint=fingerprint))
    # Preserve page order while removing duplicate mirror blocks.
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
    for post in posts:
        lines.extend([f"- {post.published}：{post.text}", f"  [查看账号]({post.url})", ""])
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
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
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
