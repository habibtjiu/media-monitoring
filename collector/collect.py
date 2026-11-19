#!/usr/bin/env python3
"""Kolektor mention live untuk dashboard media-monitoring (GitHub Pages).

Mengambil RSS gratis (Google News RSS, ANTARA, CNBC Indonesia), memfilter
hanya item tentang 5 entitas yang dipantau, mengklasifikasi sentimen/emosi
dengan daftar kata Bahasa Indonesia, lalu menulis data.json dalam format
yang dipakai dashboard (lihat data.js).

- Engagement TIDAK tersedia dari RSS gratis -> selalu 0 (aplikasi
  menampilkan "—" dalam mode live).
- Region tidak tersedia dari RSS -> "Nasional".
- Output deterministik: item yang sama (link sama) selalu menghasilkan
  id dan isi yang sama, supaya commit GitHub hanya berubah kalau ada
  mention baru.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote, urlparse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
WIB = timezone(timedelta(hours=7))
OUT = sys.argv[1] if len(sys.argv) > 1 else "data.json"

BRANDS = ["Artha Graha", "Sea Bank", "Allo Bank", "Bank Saqu", "IBK Bank"]
PRIMARY = "Bank Artha Graha Internasional"

# query Google News -> (brand fallback, topic)
GNEWS_QUERIES = [
    ("Bank Artha Graha", "Artha Graha", PRIMARY),
    ("Artha Graha Peduli", "Artha Graha", "(CSSR) Artha Graha Peduli - BAGI"),
    ("SeaBank", "Sea Bank", PRIMARY),
    ("Allo Bank", "Allo Bank", PRIMARY),
    ("Bank Saqu", "Bank Saqu", PRIMARY),
    ("IBK Bank", "IBK Bank", PRIMARY),
    ("Artha Graha", "Artha Graha", PRIMARY),
    ("INPC", "Artha Graha", PRIMARY),
    ("AGP Artha Graha", "Artha Graha", "(CSSR) Artha Graha Peduli - BAGI"),
    ("bank digital", None, "Program Digital Banking"),
    ("penipuan bank", None, "Fraud & Scam"),
    ("literasi keuangan", None, "Edukasi dan Literasi keuangan Bank Artha Graha Internasional"),
]
# feed umum -> hanya item yang menyebut salah satu entitas
GENERAL_FEEDS = [
    ("https://www.antaranews.com/rss/terkini", "Antara"),
    ("https://www.antaranews.com/rss/ekonomi", "Antara"),
    ("https://www.cnbcindonesia.com/rss", "CNBC Indonesia"),
]

POS_WORDS = """untung laba tumbuh naik meningkat rekor ekspansi luncurkan meluncurkan
inovasi penghargaan apresiasi sukses positif dukung dukungan kerjasama kerja sama
investasi raih capai terbaik aman percaya digitalisasi transformasi kinerja
dividen untung bersih naik kelas solid kuat bertumbuh melesat lampaui""".split()
NEG_WORDS = """rugi turun anjlok merosot skandal penipuan scam fraud bobol gagal
ditangkap tersangka dugaan kerugian phk bangkrut kolaps denda sanksi gugatan
protes keluhan macet eror gangguan bocor diretas hack korupsi suap palsu
dicuri dibobol waspada hati-hati rugi bersih turun tajam terpuruk""".split()

EMOTION_RULES = [
    (["penipuan", "scam", "palsu", "bobol", "diretas", "dicuri"], "Anger"),
    (["skandal", "dugaan", "tersangka", "ditangkap", "korupsi", "suap"], "Disgust"),
    (["rugi", "turun", "anjlok", "merosot", "gagal", "kerugian", "phk"], "Sadness"),
    (["tiba-tiba", "mengejutkan", "tak terduga", "mendadak"], "Surprise"),
    (["takut", "khawatir", "cemas", "ancam"], "Fear"),
    (["luncurkan", "meluncurkan", "inovasi", "ekspansi", "kerjasama", "kerja sama"], "Anticipation"),
    (["penghargaan", "terbaik", "rekor", "raih", "sukses"], "Joy"),
    (["aman", "percaya", "dukung", "apresiasi"], "Trust"),
]
ORG_STOP = {"bank", "otoritas", "pemerintah", "kementerian", "indonesia", "artha",
            "graha", "sea", "allo", "saqu", "ibk", "dpr", "bi", "ojk", "asosiasi",
            "direktur", "presiden", "komisaris", "chief", "pt"}

# Judul spam judi / situs yang dibajak: bukan berita tentang bank.
JUNK_TITLE = ["jackpot", "megaways", "maxwin", "mahjong", "kasino", "casino",
              "togel", "gacor", "lotre", " 4d", "4d ", "bonus new member",
              "bonus selamat datang", "gampang menang", "link alternatif",
              "rtp slot", "scatter", "judi "]
JUNK_SOURCE = ["direktorat jenderal pemasyarakatan", "ditjenpas", "vietnam", ".vn"]

KNOWN_PEOPLE = ["Tomy Winata", "Sugianto Kusuma", "Jefri R. Sirait",
                "Andi Buchari", "Kartika Wirjoatmodjo", "Aguan"]


def is_junk(title, source):
    t = " " + title.lower() + " "
    s = source.lower()
    if any(w in t for w in JUNK_TITLE):
        return True
    return any(w in s for w in JUNK_SOURCE)


def fetch(url):
    for _ in range(2):
        try:
            p = subprocess.run(
                ["curl", "-s", "-m", "25", "-A", UA, url],
                capture_output=True, timeout=40)
            if p.returncode == 0 and p.stdout:
                return p.stdout
        except Exception:
            pass
    return b""


def clean(text):
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_brand(text):
    t = " " + text.lower() + " "
    if "artha graha" in t:
        return "Artha Graha"
    if "sea bank" in t or "seabank" in t:
        return "Sea Bank"
    if "allo bank" in t:
        return "Allo Bank"
    if "bank saqu" in t or " saqu " in t:
        return "Bank Saqu"
    if "ibk bank" in t or " ibk " in t:
        return "IBK Bank"
    return None


def sentiment(text):
    low = text.lower()
    pos = sum(low.count(w) for w in POS_WORDS)
    neg = sum(low.count(w) for w in NEG_WORDS)
    if pos > neg:
        return "Positive"
    if neg > pos:
        return "Negative"
    return "Neutral"


def emotion(text, senti):
    t = text.lower()
    for words, emo in EMOTION_RULES:
        if any(w in t for w in words):
            return emo
    return "Trust" if senti != "Negative" else "Sadness"


def extract_person(text):
    for name in KNOWN_PEOPLE:
        if name.lower() in text.lower():
            return name
    m = re.search(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}),?\s+"
        r"(Direktur Utama|Presiden Direktur|Direktur|Komisaris|CEO|Chief)",
        text)
    if m:
        name = m.group(1)
    else:
        m = re.search(
            r"(?:kata|ujar|menurut|ungkap|tutur)\s+"
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", text)
        name = m.group(2) if m else ""
    if not name:
        return ""
    words = [w for w in name.split() if w.lower() not in ORG_STOP]
    return " ".join(words) if len(words) >= 2 else ""


def extract_org(text, brand):
    t = text.lower()
    if "otoritas jasa keuangan" in t or " ojk " in (" " + t + " "):
        return "Otoritas Jasa Keuangan"
    if "bank indonesia" in t:
        return "Bank Indonesia"
    return brand


def topic_for(text, fallback):
    t = text.lower()
    if "pasar wiwitan" in t:
        return "The Local Market ID Pasar Wiwitan SCBD"
    if any(w in t for w in ("fraud", "penipuan", "scam", "palsu")):
        return "Fraud & Scam"
    if "literasi" in t or "edukasi" in t:
        return "Edukasi dan Literasi keuangan Bank Artha Graha Internasional"
    if any(w in t for w in ("peduli", "baksos", "aksi sosial", "bakti")):
        return "(CSSR) Artha Graha Peduli - BAGI"
    if "digital banking" in t or "digitalisasi" in t:
        return "Program Digital Banking"
    return fallback or PRIMARY
    try:
        host = urlparse(link).netloc.lower().replace("www.", "")
    except Exception:
        host = ""
    mapping = {"antaranews.com": "Antara",
               "cnbcindonesia.com": "CNBC Indonesia",
               "news.google.com": fallback}
    return mapping.get(host, fallback or host or "Media Online")


def parse_date(raw):
    try:
        dt = parsedate_to_datetime(raw)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(WIB).date().isoformat()
    except Exception:
        return None


def parse_feed(xml_bytes, fallback_source, query_brand, query_topic):
    items = []
    if not xml_bytes:
        return items
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return items
    for it in root.iter("item"):
        title = clean(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        desc = clean(it.findtext("description"))
        pub = parse_date(it.findtext("pubDate") or "")
        if not title or not link or not pub:
            continue
        src_el = it.find("source")
        source = clean(src_el.text) if src_el is not None and src_el.text else ""
        if is_junk(title, source):
            continue
        text = title + " " + desc
        brand = detect_brand(text) or query_brand
        if not brand:
            continue
        items.append({
            "title": title, "link": link, "desc": desc, "date": pub,
            "brand": brand, "topic": query_topic or PRIMARY,
            "source": source or outlet_from(link, fallback_source),
            "text": text,
        })
    return items


def main():
    now = datetime.now(WIB)
    cutoff = (now.date() - timedelta(days=30)).isoformat()
    seen = {}
    failed_feeds = []
    for q, qbrand, qtopic in GNEWS_QUERIES:
        url = ("https://news.google.com/rss/search?q=" + quote('"' + q + '"') +
               "&hl=id&gl=ID&ceid=ID:id")
        xml = fetch(url)
        if not xml:
            failed_feeds.append("gnews:" + q)
            continue
        for it in parse_feed(xml, "Google News", qbrand, qtopic):
            seen.setdefault(it["link"], it)
    for url, name in GENERAL_FEEDS:
        xml = fetch(url)
        if not xml:
            failed_feeds.append(name)
            continue
        for it in parse_feed(xml, name, None, PRIMARY):
            seen.setdefault(it["link"], it)

    out = []
    for it in seen.values():
        if it["date"] < cutoff or it["date"] > now.date().isoformat():
            continue
        senti = sentiment(it["text"])
        emo = emotion(it["text"], senti)
        person = extract_person(it["title"] + ". " + it["desc"])
        brand = it["brand"]
        name = PRIMARY if brand == "Artha Graha" else brand
        iid = "m" + hashlib.sha1(it["link"].encode()).hexdigest()[:12]
        kw = [name.lower()]
        if brand == "Artha Graha":
            kw += ["bank artha graha", "artha graha"]
        title_words = [w.lower() for w in re.findall(r"[A-Za-z]{5,}", it["title"])]
        stop = {"bank", "artha", "graha", "internasional", "indonesia",
                "digital", "keuangan", "nasabah", "layanan"}
        for w in title_words:
            if w not in stop and w not in kw:
                kw.append(w)
            if len(kw) >= 4:
                break
        statement = it["desc"] or it["title"]
        if len(statement) > 220:
            statement = statement[:217].rsplit(" ", 1)[0] + "…"
        out.append({
            "id": iid, "date": it["date"], "brand": brand,
            "language": "Indonesia", "channel": "Media Online",
            "source": it["source"], "title": it["title"],
            "sentiment": senti, "emotion": emo, "engagement": 0,
            "person": person, "organization": extract_org(it["text"], name),
            "keywords": kw[:4],
            "hashtags": ["#BankArthaGraha"] if brand == "Artha Graha"
                        else ["#" + brand.replace(" ", "")],
            "region": "Nasional",
            "topic": topic_for(it["text"], it["topic"]),
            "statement": (person + " menyoroti " + it["title"] + "."
                          if person else statement),
            "comparisonWeight": 1, "sentimentWeight": 1,
            "link": it["link"],
        })
    out.sort(key=lambda x: (x["date"], x["title"]), reverse=True)
    # Jangan menimpa data bagus dengan hasil gagal sebagian: kalau ada feed
    # yang gagal ambil, atau hasilnya anjlok dibanding file lama, pertahankan
    # file lama dan keluar non-zero supaya workflow tidak commit.
    if len(failed_feeds) >= 2:
        print(f"ABORT: {len(failed_feeds)} feed gagal: {failed_feeds}")
        return 1
    if not out:
        print("ABORT: 0 item")
        return 1
    if os.path.exists(OUT):
        try:
            old_n = len(json.load(open(OUT, encoding="utf-8")).get("items", []))
            if old_n >= 10 and len(out) < old_n / 2:
                print(f"ABORT: hasil anjlok {old_n} -> {len(out)} item")
                return 1
        except Exception:
            pass
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_at_wib": now.strftime("%d %b %Y, %H:%M WIB"),
        "items": out,
    }
    # Kalau tidak ada mention baru, pertahankan timestamp lama supaya file
    # byte-identik dan workflow GitHub tidak commit sia-sia tiap 15 menit.
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding="utf-8"))
            if old.get("items") == payload["items"]:
                payload["generated_at"] = old.get("generated_at", payload["generated_at"])
                payload["generated_at_wib"] = old.get(
                    "generated_at_wib", payload["generated_at_wib"])
        except Exception:
            pass
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
    brands = {}
    for it in out:
        brands[it["brand"]] = brands.get(it["brand"], 0) + 1
    print(f"items={len(out)} brands={brands} "
          f"dates={out[-1]['date'] if out else '-'}..{out[0]['date'] if out else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
