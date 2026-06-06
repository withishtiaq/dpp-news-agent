#!/usr/bin/env python3
"""
DPP নিউজ এজেন্ট — Cloudscraper version
Cloudflare bypass করে পদ্মা টাইমস ২৪ থেকে RSS Feed নেয়।
"""

import json
import os
import re
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

warnings.filterwarnings('ignore')

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    import requests
    HAS_CLOUDSCRAPER = False

RSS_URLS = [
    'https://padmatimes24.com/rajshahi/feed/',
    'https://padmatimes24.com/rajshahi/feed/rss2/',
    'https://padmatimes24.com/feed/?cat=rajshahi',
    'https://padmatimes24.com/feed/',
]

BD_TZ = timezone(timedelta(hours=6))

def get_layout() -> str:
    layouts = ['layout1', 'layout2', 'layout3', 'layout4', 'layout5', 'layout6']
    return layouts[datetime.now(BD_TZ).hour % 6]

UPAZILA_LIST = [
    'পবা','মোহনপুর','চারঘাট','পুঠিয়া',
    'দুর্গাপুর','বাগমারা','গোদাগাড়ী','তানোর','বাঘা',
]

def detect_upazila(text: str) -> str:
    for u in UPAZILA_LIST:
        if u in text:
            return u
    return 'রাজশাহী শহর'

def strip_html(html: str) -> str:
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;|&amp;|&lt;|&gt;|&quot;|&#\d+;', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def make_session():
    if HAS_CLOUDSCRAPER:
        print("  🛡️ Cloudscraper (Cloudflare bypass) ব্যবহার করছি")
        return cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
    else:
        print("  ⚠️ Requests ব্যবহার করছি")
        import requests
        s = requests.Session()
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        return s

def fetch_rss(session, url: str):
    try:
        r = session.get(url, timeout=30, verify=False)
        print(f"  [{r.status_code}] {url}")
        if r.status_code == 200:
            return r.content
    except Exception as e:
        print(f"  ❌ {url}: {e}")
    return None

def parse_rss(content: bytes) -> list:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"  ❌ XML parse error: {e}")
        return []

    ns = {
        'content': 'http://purl.org/rss/1.0/modules/content/',
        'media':   'http://search.yahoo.com/mrss/',
    }

    channel = root.find('channel')
    if channel is None:
        return []

    items   = channel.findall('item')
    print(f"  📰 {len(items)} টি item পাওয়া গেছে")

    articles = []
    for item in items[:15]:
        title = item.findtext('title', '').strip()
        if not title:
            continue

        link = item.findtext('link', '').strip()

        # Content
        content = ''
        ce = item.find('content:encoded', ns)
        if ce is not None and ce.text:
            content = strip_html(ce.text)
        if not content:
            d = item.find('description')
            if d is not None and d.text:
                content = strip_html(d.text)
        if len(content) < 30:
            continue

        # Image
        image_url = ''
        enc = item.find('enclosure')
        if enc is not None:
            image_url = enc.get('url', '')
        if not image_url:
            med = item.find('media:content', ns)
            if med is not None:
                image_url = med.get('url', '')
        if not image_url and ce is not None and ce.text:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', ce.text)
            if m:
                image_url = m.group(1)

        articles.append({
            'title':      title,
            'content':    content[:6000],
            'image_url':  image_url,
            'source_url': link,
            'upazila':    detect_upazila(title + ' ' + content),
        })
        print(f"  ✓ {title[:60]}")

    return articles

def main():
    layout  = get_layout()
    bd_time = datetime.now(BD_TZ).strftime('%Y-%m-%d %H:%M')

    print(f"{'='*55}")
    print(f"🤖 DPP নিউজ এজেন্ট — {bd_time} (BD)")
    print(f"🗞️  লেআউট: {layout} | সোর্স: পদ্মা টাইমস ২৪")
    print(f"{'='*55}")

    session  = make_session()
    articles = []

    # RSS URLs একে একে try করো
    for rss_url in RSS_URLS:
        content = fetch_rss(session, rss_url)
        if content:
            # XML কিনা check করো
            if b'<rss' in content[:500] or b'<feed' in content[:500]:
                articles = parse_rss(content)
                if articles:
                    break
            else:
                preview = content[:200].decode('utf-8', errors='ignore')
                print(f"  ⚠️ XML নয়: {preview}")

    os.makedirs('data', exist_ok=True)
    output = {
        'generated_at': datetime.now(BD_TZ).isoformat(),
        'layout':       layout,
        'articles':     articles,
    }
    with open('data/articles.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*55}")
    print(f"💾 {len(articles)} আর্টিকেল → data/articles.json")
    print(f"✅ শেষ।")
    print(f"{'='*55}")

if __name__ == '__main__':
    main()
