#!/usr/bin/env python3
"""
Cinema new-movie notifier -> Telegram.
Checks Scene, VOX and Premiere, and sends a message for every new movie.

Usage:
    python check.py            # normal run
    python check.py --debug    # prints what it found per site, sends nothing

Env vars required: TOKEN (bot token), CHAT_ID
Requires: pip install requests beautifulsoup4 curl_cffi
"""
import json
import os
import re
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi

DEBUG = "--debug" in sys.argv
TOKEN = os.environ.get("TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")

# "include" = regex a movie link's path must match.
# "exclude" (optional) = regex to drop listing/navigation links.
SITES = {
    "Scene CFC": {
        "url": "https://cfc.scenecinemas.com/home",
        "include": r"/movie-details/",
    },
    "Scene District5": {
        "url": "https://district5.scenecinemas.com/home",
        "include": r"/movie-details/",
    },
    "VOX": {
        "url": "https://egy.voxcinemas.com/movies/whatson",
        "include": r"^/movies/[^/]+$",
        "exclude": r"/movies/(whatson|comingsoon|advance-booking)$",
    },
    "Premiere": {
        "url": "https://www.premiere-cinemas.com/en/now-showing",
        "raw_regex": True,  # data is embedded in the HTML text (Next.js)
        # Movie pages look like <link_prefix>/now-showing/<unique id>
        "link_prefix": "https://www.premiere-cinemas.com/en",
    },
}

# Link texts that are buttons, not movie names.
GENERIC = {"showtimes", "book now", "book", "more info", "details", "trailer",
           "watch trailer", "buy tickets", "get tickets", "read more", "view more"}


def pretty(path):
    return path.rsplit("/", 1)[-1].replace(".html", "").replace("-", " ").title()


def fetch_raw(cfg, text):
    """For sites (e.g. Next.js) that embed movie data as JSON text instead of <a> tags."""
    text = text.replace('\\"', '"').replace('\\/', '/')
    uids = {}  # movie id -> unique identifier used in the movie page URL
    for m in re.finditer(r'"movie_unique_identifier"\s*:\s*"([^"]+)"\s*,\s*"movie_id"\s*:\s*(\d+)', text):
        uids.setdefault(m.group(2), m.group(1))

    ids = list(re.finditer(r'"movie_id"\s*:\s*(\d+)', text))
    found = {}
    for i, m in enumerate(ids):
        mid = m.group(1)
        end = ids[i + 1].start() if i + 1 < len(ids) else m.end() + 3000
        chunk = text[m.end(): min(end, m.end() + 3000)]
        t = re.search(r'"(?:movie_title|banner_name)"\s*:\s*"([^"]{1,100})"', chunk)
        if mid not in found or (t and found[mid][0].startswith("Movie #")):
            uid = uids.get(mid)
            link = cfg["link_prefix"] + (f"/now-showing/{uid}" if uid else "/now-showing")
            found[mid] = (t.group(1) if t else f"Movie #{mid}", link)
    return found


def fetch_movies(cfg):
    """Return {movie_key: (name, full_url)} for one site."""
    r = cffi.get(cfg["url"], impersonate="chrome", timeout=40)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    if cfg.get("raw_regex"):
        return fetch_raw(cfg, r.text)

    include = re.compile(cfg["include"])
    exclude = re.compile(cfg["exclude"]) if cfg.get("exclude") else None

    found = {}  # path -> [name, url, has_real_name]
    for a in soup.find_all("a", href=True):
        full = urljoin(cfg["url"], a["href"]).split("#")[0]
        path = urlparse(full).path.rstrip("/") or "/"
        if not include.search(path):
            continue
        if exclude and exclude.search(path):
            continue

        img = a.find("img")
        candidates = [a.get("title"), a.get_text(" ", strip=True),
                      img.get("alt") if img else None]
        name = next((c.strip() for c in candidates
                     if c and c.strip() and c.strip().lower() not in GENERIC), None)

        if path not in found:
            found[path] = [name or pretty(path), full, bool(name)]
        elif name and not found[path][2]:
            found[path] = [name, full, True]

    return {k: (v[0], v[1]) for k, v in found.items()}


def send_telegram(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text},
        timeout=20,
    )
    return r.ok


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)


def main():
    if not DEBUG and (not TOKEN or not CHAT_ID):
        sys.exit("Set TOKEN and CHAT_ID environment variables first.")

    state = load_state()
    failed = 0

    for site, cfg in SITES.items():
        try:
            movies = fetch_movies(cfg)
        except Exception as e:
            print(f"[{site}] ERROR: {e}")
            failed += 1
            continue

        print(f"[{site}] found {len(movies)} movies")
        if DEBUG:
            for key, (name, url) in list(movies.items())[:10]:
                print(f"    {name}  ->  {url}")
            continue

        if not movies:
            print(f"[{site}] no movies parsed, keeping old state")
            failed += 1
            continue

        seen = set(state.get(site, []))
        first_run = site not in state  # per-site baseline, no spam

        if not first_run:
            for key in sorted(set(movies) - seen):
                name, url = movies[key]
                if send_telegram(f"🎬 New movie at {site}: {name}\n{url}"):
                    seen.add(key)
                else:
                    print(f"[{site}] Telegram send failed for {name}, will retry next run")
        else:
            seen = set(movies)
            print(f"[{site}] first run: saved baseline, no notifications")

        state[site] = sorted(seen)

    if not DEBUG:
        save_state(state)
    if failed == len(SITES):
        sys.exit(1)


if __name__ == "__main__":
    main()