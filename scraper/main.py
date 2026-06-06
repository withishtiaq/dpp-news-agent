#!/usr/bin/env python3
"""
DPP নিউজ এজেন্ট — GitHub Actions Scraper v3
Bengali character count দিয়ে article URL detect করে।
"""

import asyncio
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ─── Config ──────────────────────────────────────────────────
WP_URL          = os.environ.get('WP_URL', 'https://doinikprothompata.com').rstrip('/')
WP_USER         = os.environ.get('WP_USER', 'prothompata')
WP_APP_PASSWORD = os.environ.get('WP_APP_PASSWORD', '').replace(' ', '')
API_ENDPOINT    = f"{WP_URL}/wp-json/dppna/v1/create-post"
BD_TZ           = timezone(timedelta(hours=6))

def get_layout() -> str:
    layouts = ['layout1', 'layout2', 'layout3', 'layout4', 'layout5', 'layout6']
    return layouts[datetime.now(BD_TZ).hour % 6]

# ─── সোর্স তালিকা ────────────────────────────────────────────
# extra_skip = এই URL pattern গুলো article নয়, skip করো
SOURCES = [
    # কাজ ১: প্রথম আলো
    {
        'id': 'prothomalo', 'name': 'প্রথম আলো', 'upazila': '',
        'url': 'https://www.prothomalo.com/search?type=text%2Cteam-bio%2Clisticle%2Cphoto%2Cgallery%2Cvideo%2Clive-blog%2Cinterview&q=%E0%A6%B0%E0%A6%BE%E0%A6%9C%E0%A6%B6%E0%A6%BE%E0%A6%B9%E0%A7%80',
        'extra_skip': [],
    },
    # কাজ ২: যুগান্তর ৯ উপজেলা — /location/ অন্য লোকেশন পেজ skip
    {'id': 'jugantor_bagha',    'name': 'যুগান্তর — বাঘা',     'upazila': 'বাঘা',    'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-bagha',    'extra_skip': ['/location/']},
    {'id': 'jugantor_bagmara',  'name': 'যুগান্তর — বাগমারা',  'upazila': 'বাগমারা', 'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-bagmara',  'extra_skip': ['/location/']},
    {'id': 'jugantor_charghat', 'name': 'যুগান্তর — চারঘাট',   'upazila': 'চারঘাট',  'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-charghat', 'extra_skip': ['/location/']},
    {'id': 'jugantor_durgapur', 'name': 'যুগান্তর — দুর্গাপুর', 'upazila': 'দুর্গাপুর','url': 'https://www.jugantor.com/location/rajshahi-rajshahi-durgapur', 'extra_skip': ['/location/']},
    {'id': 'jugantor_godagari', 'name': 'যুগান্তর — গোদাগাড়ী', 'upazila': 'গোদাগাড়ী','url': 'https://www.jugantor.com/location/rajshahi-rajshahi-godagari', 'extra_skip': ['/location/']},
    {'id': 'jugantor_mohanpur', 'name': 'যুগান্তর — মোহনপুর',  'upazila': 'মোহনপুর', 'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-mohanpur', 'extra_skip': ['/location/']},
    {'id': 'jugantor_paba',     'name': 'যুগান্তর — পবা',       'upazila': 'পবা',      'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-paba',     'extra_skip': ['/location/']},
    {'id': 'jugantor_puthia',   'name': 'যুগান্তর — পুঠিয়া',   'upazila': 'পুঠিয়া',  'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-puthia',   'extra_skip': ['/location/']},
    {'id': 'jugantor_tanore',   'name': 'যুগান্তর — তানোর',     'upazila': 'তানোর',    'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-tanore',   'extra_skip': ['/location/']},
    # কাজ ৩: জাগো নিউজ ২৪
    {'id': 'jagonews24',    'name': 'জাগো নিউজ ২৪',   'upazila': '', 'url': 'https://www.jagonews24.com/bangladesh/rajshahi/rajshahi',    'extra_skip': ['/bangladesh/rajshahi']},
    # কাজ ৪: আজকের পত্রিকা
    {'id': 'ajkerpatrika', 'name': 'আজকের পত্রিকা',   'upazila': '', 'url': 'https://www.ajkerpatrika.com/country/rajshahi-division',    'extra_skip': ['/country/', '/division']},
    # কাজ ৫: পদ্মা টাইমস ২৪
    {'id': 'padmatimes24', 'name': 'পদ্মা টাইমস ২৪',  'upazila': '', 'url': 'https://padmatimes24.com/rajshahi/',                       'extra_skip': ['/rajshahi/', '/category/']},
    # কাজ ৬: উত্তরা প্রতিদিন
    {'id': 'uttaraprotidin','name': 'উত্তরা প্রতিদিন','upazila': '', 'url': 'https://www.uttaraprotidin.com/category/uttranchl',         'extra_skip': ['/category/']},
]

# ─── Content Selectors ───────────────────────────────────────
CONTENT_SELECTORS = [
    # Jugantor
    'div.col-xl-8 .details p', 'div[class*="news_dtl_body"] p',
    'div[class*="news_dtl"] p', 'div.details p',
    # Prothom Alo
    'div[class*="story-element-text"] p', 'div[class*="story-content"] p',
    # Jago News
    'div[class*="news-details"] p', 'div[class*="details_body"] p',
    # Ajker Patrika
    'div[class*="content-wrapper"] p', 'div[class*="article-content"] p',
    # WordPress-based sites
    'div.entry-content p', 'div[class*="post-content"] p',
    'div[class*="single-post-content"] p',
    # Generic
    'article p', 'div[class*="content-details"] p',
    'div[class*="news_content"] p', 'div[class*="news-content"] p',
    'div[class*="body-text"] p', 'div[class*="article-body"] p',
    'main p',
]

# ─── Popup বন্ধ ──────────────────────────────────────────────
async def dismiss_popups(page):
    for sel in [
        'button[class*="close"]', '[class*="popup"] button',
        '[class*="modal"] button[class*="close"]',
        '[class*="cookie"] button', '[id*="close-btn"]',
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=500):
                await btn.click(timeout=500)
                await asyncio.sleep(0.3)
        except Exception:
            pass

# ─── Bengali char count দিয়ে Article URL বের করো ───────────────
async def get_latest_article_url(page, source: dict) -> str | None:
    list_url    = source['url']
    extra_skip  = source.get('extra_skip', [])
    site_domain = urlparse(list_url).netloc.replace('www.', '')

    try:
        await page.goto(list_url, timeout=45000, wait_until='domcontentloaded')
        await asyncio.sleep(4)
        await dismiss_popups(page)
    except PWTimeout:
        print(f"    ⚠️ Timeout loading list page")
        return None
    except Exception as e:
        print(f"    ⚠️ List load error: {e}")
        return None

    # সব link বের করো + Bengali character count
    # Article title = ২৫+ Bengali char, navigation link = অনেক কম
    try:
        links_data = await page.eval_on_selector_all(
            'a[href]',
            r"""els => els.map(e => ({
                href: e.href,
                bn: (e.innerText.match(/[\u0980-\u09FF]/g) || []).length
            })).filter(e => e.href && e.bn >= 25)"""
        )
    except Exception:
        return None

    seen = set()
    for item in links_data:
        link = item.get('href', '')
        if not link or link in seen:
            continue
        seen.add(link)

        if not link.startswith('http'):
            continue

        # একই সাইট হতে হবে
        if site_domain not in link:
            continue

        # List page নিজেই skip
        if link.rstrip('/') == list_url.rstrip('/'):
            continue

        path  = urlparse(link).path.rstrip('/')
        parts = [p for p in path.split('/') if p]

        # কমপক্ষে ২ level deep হতে হবে
        if len(parts) < 2:
            continue

        # Source-specific skip
        if extra_skip and any(p in link.lower() for p in extra_skip):
            continue

        # Global bad patterns
        bad = ['/tag/', '/author/', '/page/', '/feed/', '/wp-admin/',
               '/search/', '/login/', '/register/']
        if any(p in link.lower() for p in bad):
            continue

        # এটা article URL!
        return link

    return None

# ─── Article scrape ───────────────────────────────────────────
async def scrape_article(page, url: str) -> dict:
    try:
        await page.goto(url, timeout=45000, wait_until='domcontentloaded')
        await asyncio.sleep(5)
        await dismiss_popups(page)
    except PWTimeout:
        print(f"    ⚠️ Article timeout")
        return {}
    except Exception as e:
        print(f"    ⚠️ Article load error: {e}")
        return {}

    # শিরোনাম
    title = ''
    for sel in ['meta[property="og:title"]', 'meta[name="twitter:title"]']:
        try:
            v = await page.get_attribute(sel, 'content', timeout=2000)
            if v and len(v.strip()) > 5:
                title = v.strip()
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
            title = re.sub(r'\s*[\|\-–—]\s*.{0,40}$', '', await page.title()).strip()
        except Exception:
            pass

    # ফিচার ইমেজ
    image_url = ''
    for sel in ['meta[property="og:image"]', 'meta[name="twitter:image"]']:
        try:
            v = await page.get_attribute(sel, 'content', timeout=2000)
            if v and v.strip().startswith('http'):
                image_url = v.strip()
                break
        except Exception:
            pass

    # Content
    content = ''
    for sel in CONTENT_SELECTORS:
        try:
            paras = await page.eval_on_selector_all(
                sel,
                "els => els.map(e => e.innerText.trim()).filter(t => t.length > 25)"
            )
            if paras:
                joined = '\n\n'.join(paras)
                if len(joined) >= 150:
                    content = joined[:5000]
                    break
        except Exception:
            continue

    return {'title': title, 'content': content, 'image_url': image_url, 'url': url}

# ─── WordPress REST API call (retry সহ) ──────────────────────
async def post_to_wordpress(article: dict, layout: str, upazila: str) -> bool:
    payload = {
        'title':      article['title'],
        'content':    article['content'],
        'image_url':  article['image_url'],
        'layout':     layout,
        'source_url': article['url'],
        'upazila':    upazila,
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=60, verify=False) as client:
                resp = await client.post(
                    API_ENDPOINT,
                    json=payload,
                    auth=(WP_USER, WP_APP_PASSWORD),
                    headers={'Accept': 'application/json'},
                )

                # Response log করো
                if resp.status_code not in (200, 201):
                    print(f"    ⚠️ HTTP {resp.status_code}: {resp.text[:200]}")
                    if attempt < 2:
                        await asyncio.sleep(5)
                        continue
                    return False

                data = resp.json()
                status = data.get('status', '')

                if status == 'created':
                    print(f"    ✅ পোস্ট (ID:{data.get('post_id')}) — {article['title'][:55]}")
                    return True
                elif status == 'skipped':
                    print(f"    ⏭️  Skip ({data.get('reason')}) — {article['title'][:50]}")
                    return False
                else:
                    print(f"    ❌ ব্যর্থ: {data}")
                    return False

        except httpx.RemoteProtocolError as e:
            print(f"    ❌ Connection dropped (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                await asyncio.sleep(8)
                continue
        except Exception as e:
            print(f"    ❌ Error (attempt {attempt+1}/3): {type(e).__name__}: {e}")
            if attempt < 2:
                await asyncio.sleep(5)
                continue

    return False

# ─── একটা source process করো ─────────────────────────────────
async def process_source(browser, source: dict, layout: str):
    print(f"\n📰 {source['name']}")

    context = await browser.new_context(
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        locale='bn-BD',
        viewport={'width': 1366, 'height': 768},
        extra_http_headers={'Accept-Language': 'bn-BD,bn;q=0.9,en-US;q=0.8'},
    )
    page = await context.new_page()

    try:
        article_url = await get_latest_article_url(page, source)
        if not article_url:
            print(f"    ⚠️ Article URL পাওয়া যায়নি")
            return

        print(f"    🔗 {article_url}")

        article = await scrape_article(page, article_url)
        if not article.get('title') or not article.get('content'):
            print(f"    ⚠️ শিরোনাম বা কন্টেন্ট পাওয়া যায়নি")
            return

        print(f"    📝 {article['title'][:65]}")
        print(f"    📊 {len(article['content'])} অক্ষর | ছবি: {'✓' if article['image_url'] else '✗'}")

        await post_to_wordpress(article, layout, source.get('upazila', ''))

    except Exception as e:
        print(f"    ❌ Unexpected: {e}")
    finally:
        await context.close()

# ─── Main ─────────────────────────────────────────────────────
async def main():
    layout  = get_layout()
    bd_time = datetime.now(BD_TZ).strftime('%Y-%m-%d %H:%M')

    print(f"{'='*60}")
    print(f"🤖 DPP নিউজ এজেন্ট — {bd_time} (BD)")
    print(f"🗞️  লেআউট: {layout}")
    print(f"📊 সোর্স: {len(SOURCES)}")
    print(f"{'='*60}")

    if not WP_APP_PASSWORD:
        print("❌ WP_APP_PASSWORD সেট নেই!")
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox',
                  '--disable-dev-shm-usage', '--disable-gpu'],
        )
        for source in SOURCES:
            try:
                await process_source(browser, source, layout)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"\n❌ {source['name']}: {e}")

        await browser.close()

    print(f"\n{'='*60}")
    print(f"✅ শেষ।")

if __name__ == '__main__':
    asyncio.run(main())
