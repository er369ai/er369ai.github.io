#!/usr/bin/env python3
"""Fetch real, freely-licensed car photographs from Wikimedia Commons.

WHY THIS REPLACED THE INLINE SVG: the demo originally drew each "photo" as the
same cartoon car silhouette in a different hue with the brand name typed across
it. It was honest and it worked offline, and it also told every dealer who
opened it that nothing here was real. A car dealer's entire job is looking at
photographs of cars. The styling was never the thing being judged.

Real photos, committed into the repo rather than hotlinked, so the page still
works on a phone with no signal in someone's office.

Licence: only CC0 / public-domain / CC-BY / CC-BY-SA files are taken, and
`credits.json` records author and licence for each so the page can attribute
them. Attribution is a licence condition, not a nicety -- and a footer full of
real photo credits is itself something a generated page never has.

Scraping a rival dealer's photos to sell to their competitor was never an
option, which is the other reason this goes to Commons.

    python3 fetch_photos.py
"""
import json
import pathlib
import re
import subprocess
import urllib.parse

from PIL import Image

HERE = pathlib.Path(__file__).parent
OUT = HERE / "img"
API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia blocks generic agents and asks for a contact address.
UA = "ErfanBoostanDemoBuild/1.0 (erfan.boostan@gmail.com)"

OK_LICENCES = ("cc0", "cc-by", "cc by", "public domain", "pd")

# id -> (search term, what the listing claims it is). The search term names the
# actual generation so the photo matches the model year in the listing; a Mk7
# Golf under a 2019 listing is fine, a Mk4 is not.
WANTED = {
    1:  "Volkswagen Golf Mk7 hatchback",
    2:  "BMW G20 320i sedan",
    3:  "Toyota Corolla E170 sedan",
    4:  "Mercedes-Benz W205 C-Class sedan",
    5:  "Honda Civic FC sedan",
    6:  "Nissan Qashqai J11",
    7:  "Audi A3 8V Sportback",
    8:  "Toyota C-HR",
    9:  "Renault Clio V",
    10: "Volkswagen Passat B8 sedan",
    11: "Hyundai Tucson NX4",
    12: "BMW X1 U11",
}

# Average the middle of the frame and name the nearest colour, so the listing's
# "renk" field matches the car in the picture. A red photo under a listing that
# says Beyaz is the kind of detail that makes someone stop trusting the page.
NAMED = [
    ("Beyaz",    (235, 235, 235)), ("Gri",      (128, 130, 133)),
    ("Gümüş",    (190, 192, 195)), ("Siyah",    (32, 32, 34)),
    ("Kırmızı",  (170, 40, 40)),   ("Mavi",     (40, 70, 150)),
    ("Lacivert", (28, 40, 85)),    ("Yeşil",    (45, 105, 70)),
    ("Turuncu",  (205, 110, 40)),  ("Sarı",     (215, 190, 60)),
    ("Bej",      (198, 180, 150)), ("Kahve",    (110, 80, 55)),
]


def api(**params):
    params.update(format="json")
    url = API + "?" + urllib.parse.urlencode(params)
    r = subprocess.run(["curl", "-sL", "-m", "40", "-A", UA, url],
                       capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def licence_ok(meta):
    lic = (meta.get("LicenseShortName", {}).get("value", "")
           + " " + meta.get("License", {}).get("value", "")).lower()
    return any(k in lic for k in OK_LICENCES)


def clean(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def pick(term):
    """First search hit that is a real photo under a licence we can use."""
    res = api(action="query", list="search", srsearch=term,
              srnamespace=6, srlimit=12).get("query", {}).get("search", [])
    for hit in res:
        title = hit["title"]
        if not title.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        info = api(action="query", titles=title, prop="imageinfo",
                   iiprop="url|extmetadata|size", iiurlwidth=1400)
        pages = info.get("query", {}).get("pages", {})
        for p in pages.values():
            ii = (p.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata", {})
            if not ii.get("thumburl") or not licence_ok(meta):
                continue
            if ii.get("width", 0) < 900:
                continue
            return {
                "title": title,
                "url": ii["thumburl"],
                "page": ii.get("descriptionurl", ""),
                "author": clean(meta.get("Artist", {}).get("value", ""))[:90]
                          or "Wikimedia Commons",
                "licence": clean(meta.get("LicenseShortName", {})
                                 .get("value", "")) or "CC",
            }
    return None


def colour_name(im):
    w, h = im.size
    box = im.crop((int(w * .30), int(h * .35), int(w * .70), int(h * .65)))
    box = box.resize((1, 1))
    r, g, b = box.getpixel((0, 0))[:3]
    return min(NAMED, key=lambda n: sum((a - c) ** 2
                                        for a, c in zip(n[1], (r, g, b))))[0]


def main():
    OUT.mkdir(exist_ok=True)
    credits = {}
    for cid, term in WANTED.items():
        got = pick(term)
        if not got:
            print(f"  {cid:2d}  NO USABLE FILE for {term!r}")
            continue
        raw = OUT / f"{cid}.raw"
        subprocess.run(["curl", "-sL", "-m", "60", "-A", UA,
                        "-o", str(raw), got["url"]], check=False)
        try:
            im = Image.open(raw).convert("RGB")
        except Exception as e:
            print(f"  {cid:2d}  UNREADABLE ({e})")
            raw.unlink(missing_ok=True)
            continue
        # 16:10 centre crop, matching the card's aspect-ratio box so nothing
        # is letterboxed or stretched on the page.
        w, h = im.size
        target = 16 / 10
        if w / h > target:
            nw = int(h * target)
            im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = int(w / target)
            im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
        im = im.resize((900, 562), Image.LANCZOS)
        im.save(OUT / f"{cid}.jpg", "JPEG", quality=82, optimize=True,
                progressive=True)
        raw.unlink(missing_ok=True)
        credits[cid] = {k: got[k] for k in ("title", "page", "author",
                                            "licence")}
        credits[cid]["renk"] = colour_name(im)
        print(f"  {cid:2d}  {credits[cid]['renk']:9s} {got['licence']:14s} "
              f"{got['title'][:58]}")

    (HERE / "credits.json").write_text(
        json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(credits)}/12 photos in {OUT}")


if __name__ == "__main__":
    main()
