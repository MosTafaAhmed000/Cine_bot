import requests, json, os, sys
from urllib.parse import urljoin
from bs4 import BeautifulSoup

URL = "https://www.premiere-cinemas.com/en"
TOKEN = os.environ["TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
FILE = "seen.json"

html = requests.get(URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"}).text
soup = BeautifulSoup(html, "html.parser")

movies = {}
for a in soup.select('a[href*="/movie-details/"]'):
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
