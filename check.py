import requests, json, os, sys
from urllib.parse import urljoin
from bs4 import BeautifulSoup

URL = "https://egy.voxcinemas.com"
TOKEN = os.environ["TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
FILE = "seen.json"

r = requests.get(URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
print("status:", r.status_code, "| length:", len(r.text))
print(r.text[:500])

html = r.text
soup = BeautifulSoup(html, "html.parser")

movies = {}
for a in soup.select('a[href*="/movies/"]'):
    name = a.get("title") or a.get_text(strip=True)
    if name:
        movies[a["href"]] = name

print("لقيت", len(movies), "فيلم")
if not movies:
    sys.exit("مفيش أفلام اتقرأت")

seen = set(json.load(open(FILE))) if os.path.exists(FILE) else None

if seen is not None:
    for href in movies.keys() - seen:
        requests.get(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            params={"chat_id": CHAT_ID,
                    "text": f"فيلم جديد نزل: {movies[href]}\n{urljoin(URL, href)}"},
        )

json.dump(sorted((seen or set()) | set(movies)), open(FILE, "w"), ensure_ascii=False)
