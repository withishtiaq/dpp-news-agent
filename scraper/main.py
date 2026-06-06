#!/usr/bin/env python3
"""
DPP নিউজ এজেন্ট — v4
- requests library (httpx বাদ)
- Scroll for lazy-load
- Bengali char + numeric ID fallback
"""

import asyncio
import os
import re
import sys
import json
import base64
import threading
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests as req_lib
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

# ─── API Headers ─────────────────────────────────────────────
def get_auth_headers() -> dict:
    creds   = base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()
    return {
        'Authorization': f'Basic {creds}',
        'Content-Type':  'application/json',
        'Accept':        'application/json',
        'User-Agent':    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }

# ─── API Connectivity Test ────────────────────────────────────
def test_api_connectivity() -> bool:
    print("\n🔌 WordPress API test করছি...")
    try:
        # Test 1: site accessible?
        r = req_lib.get(WP_URL, timeout=15, verify=False)
        print(f"   Site: HTTP {r.status_code}")

        # Test 2: REST API accessible?
        r2 = req_lib.get(f"{WP_URL}/wp-json/", timeout=15, verify=False)
        print(f"   REST API: HTTP {r2.status_code}")

        # Test 3: Auth works?
        r3 = req_lib.get(
            f"{WP_URL}/wp-json/wp/v2/users/me",
            headers=get_auth_headers(), timeout=15, verify=False
        )
        print(f"   Auth: HTTP {r3.status_code}")
        if r3.status_code == 200:
            data = r3.json()
            print(f"   User: {data.get('name', 'unknown')}")
            return True
        else:
            print(f"   Auth failed: {r3.text[:100]}")
            return False
    except Exception as e:
        print(f"   ❌ Cannot reach WordPress: {e}")
        return False

# ─── সোর্স তালিকা ────────────────────────────────────────────
SOURCES = [
    {'id': 'prothomalo',        'name': 'প্রথম আলো',        'upazila': '',
     'url': 'https://www.prothomalo.com/search?type=text%2Cteam-bio%2Clisticle%2Cphoto%2Cgallery%2Cvideo%2Clive-blog%2Cinterview&q=%E0%A6%B0%E0%A6%BE%E0%A6%9C%E0%A6%B6%E0%A6%BE%E0%A6%B9%E0%A7%80',
     'extra_skip': ['/photo/', '/video/', '/gallery/', '/international/']},

    {'id': 'jugantor_bagha',    'name': 'যুগান্তর — বাঘা',    'upazila': 'বাঘা',
     'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-bagha',    'extra_skip': ['/location/']},
    {'id': 'jugantor_bagmara',  'name': 'যুগান্তর — বাগমারা', 'upazila': 'বাগমারা',
     'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-bagmara',  'extra_skip': ['/location/']},
    {'id': 'jugantor_charghat', 'name': 'যুগান্তর — চারঘাট',  'upazila': 'চারঘাট',
     'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-charghat', 'extra_skip': ['/location/']},
    {'id': 'jugantor_durgapur', 'name': 'যুগান্তর — দুর্গাপুর','upazila': 'দুর্গাপুর',
     'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-durgapur', 'extra_skip': ['/location/']},
    {'id': 'jugantor_godagari', 'name': 'যুগান্তর — গোদাগাড়ী','upazila': 'গোদাগাড়ী',
     'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-godagari', 'extra_skip': ['/location/']},
    {'id': 'jugantor_mohanpur', 'name': 'যুগান্তর — মোহনপুর', 'upazila': 'মোহনপুর',
     'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-mohanpur', 'extra_skip': ['/location/']},
    {'id': 'jugantor_paba',     'name': 'যুগান্তর — পবা',      'upazila': 'পবা',
     'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-paba',     'extra_skip': ['/location/']},
    {'id': 'jugantor_puthia',   'name': 'যুগান্তর — পুঠিয়া',  'upazila': 'পুঠিয়া',
     'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-puthia',   'extra_skip': ['/location/']},
    {'id': 'jugantor_tanore',   'name': 'যুগান্তর — তানোর',    'upazila': 'তানোর',
     'url': 'https://www.jugantor.com/location/rajshahi-rajshahi-tanore',   'extra_skip': ['/location/']},

    {'id': 'jagonews24',     'name': 'জাগো নিউজ ২৪',   'upazila': '',
     'url': 'https://www.jagonews24.com/bangladesh/rajshahi/rajshahi',   'extra_skip': ['/bangladesh/rajshahi/rajshahi']},
    {'id': 'ajkerpatrika',   'name': 'আজকের পত্রিকা',  'upazila': '',
     'url': 'https://www.ajkerpatrika.com/country/rajshahi-division',    'extra_skip': ['/country/', '/division']},
    {'id': 'padmatimes24',   'name': 'পদ্মা টাইমস ২৪', 'upazila': '',
     'url': 'https://padmatimes24.com/rajshahi/',                        'extra_skip': ['/category/', '/rajshahi/$']},
    {'id': 'uttaraprotidin', 'name': 'উত্তরা প্রতিদিন','upazila': '',
     'url': 'https://www.uttaraprotidin.com/category/uttranchl',         'extra_skip': ['/category/']},
]

CONTENT_SELECTORS = [
    'div.col-xl-8 .details p', 'div[class*="news_dtl_body"] p',
    'div[class*="news_dtl"] p', 'div.details p',
    'div[class*="story-element-text"] p', 'div[class*="story-content"] p',
    'div[class*="news-details"] p', 'div[class*="details_body"] p',
    'div[class*="content-wrapper"] p', 'div[class*="article-content"] p',
    'div.entry-content p', 'div[class*="post-content"] p',
    'div[class*="single-post-content"] p',
    'article p', 'div[class*="news_content"] p',
    'div[class*="news-content"] p', 'div[class*="body-text"] p',
    'div[class*="article-body"] p', 'main p',
]

# ─── Popup dismiss ────────────────────────────────────────────
async def dismiss_popups(page):
    for sel in ['button[class*="close"]','[class*="popup"] button',
                '[class*="modal"] button[class*="close"]','[class*="cookie"] button']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=500):
                await btn.click(timeout=500)
                await asyncio.sleep(0.3)
        except Exception:
            pass

# ─── Article URL বের করো (multi-strategy) ────────────────────
async def get_latest_article_url(page, source: dict) -> str | None:
    list_url    = source['url']
    extra_skip  = source.get('extra_skip', [])
    site_domain = urlparse(list_url).netloc.replace('www.', '')

    try:
        await page.goto(list_url, timeout=45000, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        await dismiss_popups(page)
        # Scroll করো — lazy load trigger করতে
        await page.evaluate("window.scrollTo(0, 600)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, 1200)")
        await asyncio.sleep(1)
    except PWTimeout:
        print(f"    ⚠️ List page timeout")
        return None
    except Exception as e:
        print(f"    ⚠️ List load error: {e}")
        return None

    def is_valid(link):
        if not link or not link.startswith('http'):
            return False
        if site_domain not in link:
            return False
        if link.rstrip('/') == list_url.rstrip('/'):
            return False
        path  = urlparse(link).path.rstrip('/')
        parts = [p for p in path.split('/') if p]
        if len(parts) < 2:
            return False
        if extra_skip and any(p.rstrip('$') in link.lower() for p in extra_skip):
            return False
        bad = ['/tag/', '/author/', '/page/', '/feed/', '/wp-admin/', '/search/']
        if any(p in link.lower() for p in bad):
            return False
        return True

    # ── Strategy 1: Bengali char count (≥15) ─────────────────
    try:
        links_bn = await page.eval_on_selector_all(
            'a[href]',
            r"""els => els.map(e => ({
                href: e.href,
                bn: ((e.innerText + ' ' + (e.getAttribute('title')||'')).match(/[\u0980-\u09FF]/g)||[]).length
            })).filter(e => e.href && e.bn >= 15)"""
        )
        for item in links_bn:
            link = item.get('href', '')
            if is_valid(link):
                print(f"    [Strategy 1 — Bengali char]")
                return link
    except Exception:
        pass

    # ── Strategy 2: Numeric ID in URL (Jugantor style) ────────
    try:
        all_links = await page.eval_on_selector_all(
            'a[href]',
            "els => [...new Set(els.map(e => e.href).filter(Boolean))]"
        )
        for link in all_links:
            if not is_valid(link):
                continue
            last = urlparse(link).path.rstrip('/').split('/')[-1]
            if re.search(r'\d{4,}', last):   # 4+ digit number = article ID
                print(f"    [Strategy 2 — Numeric ID]")
                return link
    except Exception:
        pass

    # ── Strategy 3: Slug length (slug ≥25 chars = likely article) ─
    try:
        for link in all_links:
            if not is_valid(link):
                continue
            last = urlparse(link).path.rstrip('/').split('/')[-1]
            if len(last) >= 25 and not last.isdigit():  # long slug = article
                print(f"    [Strategy 3 — Long slug]")
                return link
    except Exception:
        pass

    return None

# ─── Article scrape ───────────────────────────────────────────
async def scrape_article(page, url: str) -> dict:
    try:
        await page.goto(url, timeout=45000, wait_until='domcontentloaded')
        await asyncio.sleep(5)
        await dismiss_popups(page)
    except PWTimeout:
        return {}
    except Exception:
        return {}

    title = ''
    for sel in ['meta[property="og:title"]','meta[name="twitter:title"]']:
        try:
            v = await page.get_attribute(sel, 'content', timeout=2000)
            if v and len(v.strip()) > 5:
                title = v.strip(); break
        except Exception:
            pass
    if not title:
        try: title = (await page.inner_text('h1', timeout=3000)).strip()
        except Exception: pass
    if not title:
        try: title = re.sub(r'\s*[\|\-–—]\s*.{0,40}$', '', await page.title()).strip()
        except Exception: pass

    image_url = ''
    for sel in ['meta[property="og:image"]','meta[name="twitter:image"]']:
        try:
            v = await page.get_attribute(sel, 'content', timeout=2000)
            if v and v.strip().startswith('http'):
                image_url = v.strip(); break
        except Exception:
            pass

    content = ''
    for sel in CONTENT_SELECTORS:
        try:
            paras = await page.eval_on_selector_all(
                sel, "els => els.map(e => e.innerText.trim()).filter(t => t.length > 25)"
            )
            if paras:
                joined = '\n\n'.join(paras)
                if len(joined) >= 150:
                    content = joined[:5000]; break
        except Exception:
            continue

    return {'title': title, 'content': content, 'image_url': image_url, 'url': url}

# ─── WordPress POST (requests library — synchronous) ──────────
def _do_post(payload: dict) -> dict:
    try:
        resp = req_lib.post(
            API_ENDPOINT,
            json=payload,
            headers=get_auth_headers(),
            timeout=60,
            verify=False,
        )
        return {'status_code': resp.status_code, 'data': resp.json()}
    except Exception as e:
        return {'error': str(e)}

async def post_to_wordpress(article: dict, layout: str, upazila: str) -> bool:
    payload = {
        'title':      article['title'],
        'content':    article['content'],
        'image_url':  article['image_url'],
        'layout':     layout,
        'source_url': article['url'],
        'upazila':    upazila,
    }

    loop = asyncio.get_event_loop()

    for attempt in range(3):
        result = await loop.run_in_executor(None, lambda: _do_post(payload))

        if 'error' in result:
            print(f"    ❌ Attempt {attempt+1}/3: {result['error']}")
            if attempt < 2:
                await asyncio.sleep(8)
            continue

        sc   = result['status_code']
        data = result['data']

        if sc not in (200, 201):
            print(f"    ⚠️ HTTP {sc}: {str(data)[:150]}")
            if attempt < 2:
                await asyncio.sleep(5)
            continue

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

    return False

# ─── Source process ───────────────────────────────────────────
async def process_source(browser, source: dict, layout: str):
    print(f"\n📰 {source['name']}")

    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        locale='bn-BD',
        viewport={'width': 1366, 'height': 768},
        extra_http_headers={'Accept-Language': 'bn-BD,bn;q=0.9,en-US;q=0.8'},
    )
    page = await context.new_page()

    try:
        url = await get_latest_article_url(page, source)
        if not url:
            print(f"    ⚠️ Article URL পাওয়া যায়নি")
            return
        print(f"    🔗 {url}")

        article = await scrape_article(page, url)
        if not article.get('title') or not article.get('content'):
            print(f"    ⚠️ শিরোনাম বা কন্টেন্ট পাওয়া যায়নি")
            return

        print(f"    📝 {article['title'][:65]}")
        print(f"    📊 {len(article['content'])} অক্ষর | 🖼️ {'✓' if article['image_url'] else '✗'}")

        await post_to_wordpress(article, layout, source.get('upazila', ''))
    except Exception as e:
        print(f"    ❌ Error: {e}")
    finally:
        await context.close()

# ─── Main ─────────────────────────────────────────────────────
async def main():
    layout  = get_layout()
    bd_time = datetime.now(BD_TZ).strftime('%Y-%m-%d %H:%M')

    print(f"{'='*60}")
    print(f"🤖 DPP নিউজ এজেন্ট v4 — {bd_time} (BD)")
    print(f"🗞️  লেআউট: {layout} | সোর্স: {len(SOURCES)}")
    print(f"{'='*60}")

    if not WP_APP_PASSWORD:
        print("❌ WP_APP_PASSWORD সেট নেই!"); sys.exit(1)

    # API connectivity test
    if not test_api_connectivity():
        print("❌ WordPress API-তে connect করা যাচ্ছে না! বন্ধ করছি।")
        sys.exit(1)
    print("✅ API connected!\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-setuid-sandbox',
                  '--disable-dev-shm-usage','--disable-gpu'],
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
