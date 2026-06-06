#!/usr/bin/env python3
"""
DPP নিউজ এজেন্ট — GitHub Actions Scraper
৬টা বাংলা নিউজ সাইট থেকে রাজশাহীর সর্বশেষ খবর সংগ্রহ করে WordPress-এ পোস্ট করে।
"""

import asyncio
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ─── কনফিগ ──────────────────────────────────────────────────
WP_URL          = os.environ.get('WP_URL',          'https://doinikprothompata.com').rstrip('/')
WP_USER         = os.environ.get('WP_USER',         'prothompata')
WP_APP_PASSWORD = os.environ.get('WP_APP_PASSWORD', '').replace(' ', '')
API_ENDPOINT    = f"{WP_URL}/wp-json/dppna/v1/create-post"

BD_TZ = timezone(timedelta(hours=6))

# ─── লেআউট রোটেশন (ঘণ্টা অনুযায়ী) ─────────────────────────
def get_layout() -> str:
    hour    = datetime.now(BD_TZ).hour
    layouts = ['layout1', 'layout2', 'layout3', 'layout4', 'layout5', 'layout6']
    return layouts[hour % 6]

# ─── ৬টা সোর্সের তালিকা ──────────────────────────────────────
SOURCES = [
    # ── কাজ ১: প্রথম আলো ─────────────────────────────────
    {
        'id':       'prothomalo',
        'name':     'প্রথম আলো',
        'list_url': 'https://www.prothomalo.com/search?type=text%2Cteam-bio%2Clisticle%2Cphoto%2Cgallery%2Cvideo%2Clive-blog%2Cinterview&q=%E0%A6%B0%E0%A6%BE%E0%A6%9C%E0%A6%B6%E0%A6%BE%E0%A6%B9%E0%A7%80',
        'upazila':  '',
    },

    # ── কাজ ২: যুগান্তর — ৯টা উপজেলা ──────────────────────
    {
        'id':       'jugantor_bagha',
        'name':     'যুগান্তর — বাঘা',
        'list_url': 'https://www.jugantor.com/location/rajshahi-rajshahi-bagha',
        'upazila':  'বাঘা',
    },
    {
        'id':       'jugantor_bagmara',
        'name':     'যুগান্তর — বাগমারা',
        'list_url': 'https://www.jugantor.com/location/rajshahi-rajshahi-bagmara',
        'upazila':  'বাগমারা',
    },
    {
        'id':       'jugantor_charghat',
        'name':     'যুগান্তর — চারঘাট',
        'list_url': 'https://www.jugantor.com/location/rajshahi-rajshahi-charghat',
        'upazila':  'চারঘাট',
    },
    {
        'id':       'jugantor_durgapur',
        'name':     'যুগান্তর — দুর্গাপুর',
        'list_url': 'https://www.jugantor.com/location/rajshahi-rajshahi-durgapur',
        'upazila':  'দুর্গাপুর',
    },
    {
        'id':       'jugantor_godagari',
        'name':     'যুগান্তর — গোদাগাড়ী',
        'list_url': 'https://www.jugantor.com/location/rajshahi-rajshahi-godagari',
        'upazila':  'গোদাগাড়ী',
    },
    {
        'id':       'jugantor_mohanpur',
        'name':     'যুগান্তর — মোহনপুর',
        'list_url': 'https://www.jugantor.com/location/rajshahi-rajshahi-mohanpur',
        'upazila':  'মোহনপুর',
    },
    {
        'id':       'jugantor_paba',
        'name':     'যুগান্তর — পবা',
        'list_url': 'https://www.jugantor.com/location/rajshahi-rajshahi-paba',
        'upazila':  'পবা',
    },
    {
        'id':       'jugantor_puthia',
        'name':     'যুগান্তর — পুঠিয়া',
        'list_url': 'https://www.jugantor.com/location/rajshahi-rajshahi-puthia',
        'upazila':  'পুঠিয়া',
    },
    {
        'id':       'jugantor_tanore',
        'name':     'যুগান্তর — তানোর',
        'list_url': 'https://www.jugantor.com/location/rajshahi-rajshahi-tanore',
        'upazila':  'তানোর',
    },

    # ── কাজ ৩: জাগো নিউজ ২৪ ─────────────────────────────
    {
        'id':       'jagonews24',
        'name':     'জাগো নিউজ ২৪',
        'list_url': 'https://www.jagonews24.com/bangladesh/rajshahi/rajshahi',
        'upazila':  '',
    },

    # ── কাজ ৪: আজকের পত্রিকা ─────────────────────────────
    {
        'id':       'ajkerpatrika',
        'name':     'আজকের পত্রিকা',
        'list_url': 'https://www.ajkerpatrika.com/country/rajshahi-division',
        'upazila':  '',
    },

    # ── কাজ ৫: পদ্মা টাইমস ২৪ ───────────────────────────
    {
        'id':       'padmatimes24',
        'name':     'পদ্মা টাইমস ২৪',
        'list_url': 'https://padmatimes24.com/rajshahi/',
        'upazila':  '',
    },

    # ── কাজ ৬: উত্তরা প্রতিদিন ──────────────────────────
    {
        'id':       'uttaraprotidin',
        'name':     'উত্তরা প্রতিদিন',
        'list_url': 'https://www.uttaraprotidin.com/category/uttranchl',
        'upazila':  '',
    },
]

# ─── যে path গুলো article নয় (skip করবো) ───────────────────
SKIP_PATH_KEYWORDS = [
    'category', 'tag', 'author', 'page', 'search', 'feed',
    'login', 'register', 'wp-admin', 'wp-login', 'cart',
    'location', 'country', 'division', 'bangladesh',
    'uttranchl', 'rajshahi-division', 'sitemap', 'contact',
    'about', 'privacy', 'terms', 'advertise',
]

# ─── Popup বন্ধ করো ─────────────────────────────────────────
async def dismiss_popups(page):
    selectors = [
        'button[class*="close"]',
        'button[aria-label*="lose"]',
        '[class*="popup"] button',
        '[class*="modal"] button[class*="close"]',
        '[class*="cookie"] button[class*="accept"]',
        '[class*="consent"] button[class*="accept"]',
        '[id*="popup"] button',
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=800):
                await btn.click(timeout=800)
                await asyncio.sleep(0.3)
        except Exception:
            pass

# ─── Listing page থেকে সবচেয়ে নতুন article URL বের করো ────
async def get_latest_article_url(page, list_url: str) -> str | None:
    try:
        await page.goto(list_url, timeout=45000, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        await dismiss_popups(page)
    except PWTimeout:
        print(f"    ⚠️ Timeout: {list_url}")
        return None
    except Exception as e:
        print(f"    ⚠️ Error loading list: {e}")
        return None

    site_domain = urlparse(list_url).netloc.replace('www.', '')

    # সব link বের করো
    try:
        all_links = await page.eval_on_selector_all(
            'a[href]',
            "els => [...new Set(els.map(e => e.href))].filter(Boolean)"
        )
    except Exception:
        return None

    for link in all_links:
        if not link or not link.startswith('http'):
            continue

        try:
            parsed = urlparse(link)
        except Exception:
            continue

        # একই সাইটের link হতে হবে
        if site_domain not in parsed.netloc:
            continue

        path       = parsed.path.rstrip('/')
        path_parts = [p for p in path.split('/') if p]

        # Path অন্তত ২ অংশের হতে হবে (e.g., /rajshahi/some-news-slug)
        if len(path_parts) < 2:
            continue

        # list page নিজেই skip
        if link.rstrip('/') == list_url.rstrip('/'):
            continue

        # Navigation/category page skip
        last_part = path_parts[-1]
        if any(kw in last_part for kw in SKIP_PATH_KEYWORDS):
            continue
        if any(kw in path for kw in SKIP_PATH_KEYWORDS) and len(path_parts) < 3:
            continue

        # শুধু সংখ্যা বা খুব ছোট slug skip
        if re.match(r'^\d{1,4}$', last_part):
            continue

        # এটা article মনে হচ্ছে!
        return link

    return None

# ─── Article page থেকে content বের করো ─────────────────────
async def scrape_article(page, url: str) -> dict:
    try:
        await page.goto(url, timeout=45000, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        await dismiss_popups(page)
    except PWTimeout:
        print(f"    ⚠️ Timeout: {url}")
        return {}
    except Exception as e:
        print(f"    ⚠️ Error: {e}")
        return {}

    # ── শিরোনাম ───────────────────────────────────────────
    title = ''
    for meta_sel in [
        'meta[property="og:title"]',
        'meta[name="twitter:title"]',
        'meta[name="title"]',
    ]:
        try:
            val = await page.get_attribute(meta_sel, 'content', timeout=2000)
            if val and len(val.strip()) > 5:
                title = val.strip()
                break
        except Exception:
            pass

    if not title:
        try:
            title = (await page.inner_text('h1', timeout=3000)).strip()
        except Exception:
            pass

    if not title:
        try:
            raw   = await page.title()
            title = re.sub(r'\s*[\|\-–—]\s*.{0,30}$', '', raw).strip()
        except Exception:
            pass

    # ── ফিচার ইমেজ ────────────────────────────────────────
    image_url = ''
    for meta_sel in [
        'meta[property="og:image"]',
        'meta[name="twitter:image"]',
        'meta[itemprop="image"]',
    ]:
        try:
            val = await page.get_attribute(meta_sel, 'content', timeout=2000)
            if val and val.strip().startswith('http'):
                image_url = val.strip()
                break
        except Exception:
            pass

    # ── বিস্তারিত কন্টেন্ট ────────────────────────────────
    content = ''
    content_selectors = [
        # সাইট-নির্দিষ্ট (বাংলাদেশের নিউজ সাইট)
        'div[class*="article__body"] p',
        'div[class*="story-content"] p',
        'div[class*="story_content"] p',
        'div[class*="article-content"] p',
        'div[class*="news_content"] p',
        'div[class*="news-content"] p',
        'div[class*="details-body"] p',
        'div[class*="detail_body"] p',
        'div[class*="dtl_body"] p',
        'div[class*="content-details"] p',
        'div[class*="single-post-content"] p',
        'div[class*="article-detail-body"] p',
        'div[class*="post-body"] p',
        'div[class*="body-text"] p',
        # Generic
        'article p',
        'div.entry-content p',
        'div[class*="post-content"] p',
        'div[class*="article-body"] p',
        'main article p',
        'main p',
    ]

    for sel in content_selectors:
        try:
            paras = await page.eval_on_selector_all(
                sel,
                "els => els.map(e => e.innerText.trim()).filter(t => t.length > 25)"
            )
            if paras:
                joined = '\n\n'.join(paras)
                if len(joined) >= 200:
                    content = joined[:8000]   # সর্বোচ্চ ৮০০০ অক্ষর
                    break
        except Exception:
            continue

    return {
        'title':     title,
        'content':   content,
        'image_url': image_url,
        'url':       url,
    }

# ─── WordPress REST API-তে পোস্ট করো ────────────────────────
async def post_to_wordpress(article: dict, layout: str, upazila: str) -> bool:
    if not WP_APP_PASSWORD:
        print("    ❌ WP_APP_PASSWORD সেট করা নেই!")
        return False

    payload = {
        'title':      article['title'],
        'content':    article['content'],
        'image_url':  article['image_url'],
        'layout':     layout,
        'source_url': article['url'],
        'upazila':    upazila,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                API_ENDPOINT,
                json=payload,
                auth=(WP_USER, WP_APP_PASSWORD),
            )
            data = resp.json()

            status = data.get('status', '')
            if status == 'created':
                print(f"    ✅ পোস্ট হয়েছে (ID:{data.get('post_id')}) — {article['title'][:55]}")
                return True
            elif status == 'skipped':
                print(f"    ⏭️  Skip ({data.get('reason')}) — {article['title'][:55]}")
                return False
            else:
                print(f"    ❌ ব্যর্থ: {data}")
                return False

    except Exception as e:
        print(f"    ❌ API Error: {e}")
        return False

# ─── একটা সোর্স প্রসেস করো ──────────────────────────────────
async def process_source(browser, source: dict, layout: str):
    print(f"\n📰 {source['name']}")
    print(f"   🔗 {source['list_url']}")

    context = await browser.new_context(
        user_agent = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        locale   = 'bn-BD',
        viewport = {'width': 1366, 'height': 768},
        extra_http_headers = {
            'Accept-Language': 'bn-BD,bn;q=0.9,en-US;q=0.8,en;q=0.7',
        },
    )

    # Ads/tracker block করো (দ্রুত লোডের জন্য)
    await context.route(
        re.compile(r'\.(png|jpg|jpeg|gif|webp|svg|woff2?|ttf)$'),
        lambda r: r.abort() if any(
            x in r.request.url for x in ['doubleclick', 'googlesyndication', 'adservice']
        ) else r.continue_()
    )

    page = await context.new_page()

    try:
        # ১. Listing page থেকে সর্বশেষ article URL বের করো
        article_url = await get_latest_article_url(page, source['list_url'])
        if not article_url:
            print(f"   ⚠️ কোনো article URL পাওয়া যায়নি")
            return

        print(f"   📄 {article_url}")

        # ২. Article scrape করো
        article = await scrape_article(page, article_url)
        if not article.get('title') or not article.get('content'):
            print(f"   ⚠️ শিরোনাম বা কন্টেন্ট পাওয়া যায়নি")
            return

        print(f"   📝 শিরোনাম: {article['title'][:60]}")
        print(f"   📊 কন্টেন্ট: {len(article['content'])} অক্ষর")
        print(f"   🖼️  ছবি: {'✓' if article['image_url'] else '✗'}")

        # ৩. WordPress-এ পোস্ট করো
        await post_to_wordpress(article, layout, source.get('upazila', ''))

    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
    finally:
        await context.close()

# ─── Main ────────────────────────────────────────────────────
async def main():
    layout  = get_layout()
    bd_time = datetime.now(BD_TZ).strftime('%Y-%m-%d %H:%M')

    print(f"{'='*60}")
    print(f"🤖 DPP নিউজ এজেন্ট — {bd_time} (BD)")
    print(f"🗞️  এই রানের লেআউট: {layout}")
    print(f"📊 মোট সোর্স: {len(SOURCES)}")
    print(f"{'='*60}")

    if not WP_APP_PASSWORD:
        print("❌ WP_APP_PASSWORD environment variable সেট করা নেই!")
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless = True,
            args     = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-extensions',
            ],
        )

        for source in SOURCES:
            try:
                await process_source(browser, source, layout)
                await asyncio.sleep(3)   # সোর্সের মধ্যে বিরতি
            except Exception as e:
                print(f"\n❌ {source['name']}: {e}")

        await browser.close()

    print(f"\n{'='*60}")
    print(f"✅ সব শেষ।")
    print(f"{'='*60}")

if __name__ == '__main__':
    asyncio.run(main())
