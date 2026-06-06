#!/usr/bin/env python3
"""
DPP নিউজ এজেন্ট — RSS Feed version
পদ্মা টাইমস ২৪ এর RSS Feed থেকে রাজশাহীর নিউজ সংগ্রহ করে।
Cloudflare bypass করে সরাসরি XML data নেয়।
"""

import json
import os
import re
import sys
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import requests
warnings.filterwarnings('ignore')  # SSL warning suppress

RSS_URL  = 'https://padmatimes24.com/rajshahi/feed/'
BD_TZ    = timezone(timedelta(hours=6))

def get_layout() -> str:
    layouts = ['layout1', 'layout2', 'layout3', 'layout4', 'layout5', 'layout6']
    return layouts[datetime.now(BD_TZ).hour % 6]

UPAZILA_LIST = [
    'পবা', 'মোহনপুর', 'চারঘাট', 'পুঠিয়া',
    'দুর্গাপুর', 'বাগমারা', 'গোদাগাড়ী', 'তানোর', 'বাঘা',
]

def detect_upazila(text: str) -> str:
    for u in UPAZILA_LIST:
        if u in text:
            return u
    return 'রাজশাহী শহর'

def strip_html(html: str) -> str:
    """HTML tags সরিয়ে plain text বের করো"""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&#\d+;', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def fetch_rss_articles() -> list:
    """RSS Feed থেকে article list বের করো"""
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        'Accept-Language': 'bn-BD,bn;q=0.9,en-US;q=0.8',
    }

    print(f"\n📡 RSS Feed fetch করছি: {RSS_URL}")

    try:
        r = requests.get(RSS_URL, headers=headers, timeout=30, verify=False)
        print(f"  HTTP status: {r.status_code}")
        if r.status_code != 200:
            print(f"  ❌ RSS feed accessible নয়")
            return []
    except Exception as e:
        print(f"  ❌ Fetch error: {e}")
        return []

    # XML parse
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        print(f"  ❌ XML parse error: {e}")
        print(f"  Response preview: {r.text[:200]}")
        return []

    # RSS namespaces
    ns = {
        'content': 'http://purl.org/rss/1.0/modules/content/',
        'media':   'http://search.yahoo.com/mrss/',
        'dc':      'http://purl.org/dc/elements/1.1/',
    }

    channel = root.find('channel')
    if channel is None:
        print("  ❌ RSS channel পাওয়া যায়নি")
        return []

    items = channel.findall('item')
    print(f"  📰 RSS-এ {len(items)} টি article পাওয়া গেছে")

    articles = []
    for item in items[:15]:  # সর্বোচ্চ ১৫টা

        # Title
        title = item.findtext('title', '').strip()
        if not title:
            continue

        # Link
        link = item.findtext('link', '').strip()
        if not link:
            link_el = item.find('link')
            if link_el is not None:
                link = (link_el.text or link_el.tail or '').strip()

        # Content — content:encoded থেকে প্রথমে চেষ্টা করো
        content = ''
        content_el = item.find('content:encoded', ns)
        if content_el is not None and content_el.text:
            content = strip_html(content_el.text)
        if not content:
            desc_el = item.find('description')
            if desc_el is not None and desc_el.text:
                content = strip_html(desc_el.text)

        if len(content) < 30:
            continue

        # Image — enclosure → media:content → content HTML-এ img
        image_url = ''
        enc = item.find('enclosure')
        if enc is not None:
            image_url = enc.get('url', '')
        if not image_url:
            med = item.find('media:content', ns)
            if med is not None:
                image_url = med.get('url', '')
        if not image_url:
            med_thumb = item.find('media:thumbnail', ns)
            if med_thumb is not None:
                image_url = med_thumb.get('url', '')
        if not image_url and content_el is not None and content_el.text:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_el.text)
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
    print(f"🤖 DPP নিউজ এজেন্ট (RSS) — {bd_time} (BD)")
    print(f"🗞️  লেআউট: {layout} | সোর্স: পদ্মা টাইমস ২৪")
    print(f"{'='*55}")

    articles = fetch_rss_articles()

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
    print(f"✅ শেষ। WordPress GitHub থেকে পড়ে post করবে।")
    print(f"{'='*55}")

if __name__ == '__main__':
    main()
