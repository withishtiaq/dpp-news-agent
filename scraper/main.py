#!/usr/bin/env python3
"""
DPP নিউজ এজেন্ট — v5
GitHub Actions-এ চলে, articles.json-এ সেভ করে।
WordPress পরে GitHub থেকে পড়ে পোস্ট করে।
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

BD_TZ    = timezone(timedelta(hours=6))
ARTICLES = []   # collected articles

def get_layout() -> str:
    layouts = ['layout1', 'layout2', 'layout3', 'layout4', 'layout5', 'layout6']
    return layouts[datetime.now(BD_TZ).hour % 6]

# ─── Sources ────────────────────────────────────────────────
SOURCES = [
    {'id': 'prothomalo',        'name': 'প্রথম আলো',        'upazila': '',
     'url': 'https://www.prothomalo.com/search?type=text%2Cteam-bio%2Clisticle%2Cphoto%2Cgallery%2Cvideo%2Clive-blog%2Cinterview&q=%E0%A6%B0%E0%A6%BE%E0%A6%9C%E0%A6%B6%E0%A6%BE%E0%A6%B9%E0%A7%80',
     'extra_skip': ['/photo/', '/video/', '/gallery/', '/international/', '/lifestyle/', '/entertainment/', '/sports/', '/feature/', '/opinion/', '/world/', '/technology/', '/science/']},

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
     'url': 'https://www.jagonews24.com/bangladesh/rajshahi/rajshahi',    'extra_skip': ['/bangladesh/rajshahi/rajshahi']},
    {'id': 'ajkerpatrika',   'name': 'আজকের পত্রিকা',  'upazila': '',
     'url': 'https://www.ajkerpatrika.com/country/rajshahi-division',     'extra_skip': ['/country/', '/division']},
    {'id': 'padmatimes24',   'name': 'পদ্মা টাইমস ২৪', 'upazila': '',
     'url': 'https://padmatimes24.com/rajshahi/',                         'extra_skip': ['/category/']},
    {'id': 'uttaraprotidin', 'name': 'উত্তরা প্রতিদিন','upazila': '',
     'url': 'https://www.uttaraprotidin.com/category/uttranchl',          'extra_skip': ['/category/']},
]

CONTENT_SELECTORS = [
    'div.col-xl-8 .details p', 'div[class*="news_dtl_body"] p',
    'div[class*="news_dtl"] p', 'div.details p',
    'div[class*="story-element-text"] p', 'div[class*="story-content"] p',
    'div[class*="news-details"] p', 'div[class*="details_body"] p',
    'div[class*="content-wrapper"] p', 'div[class*="article-content"] p',
    'div.entry-content p', 'div[class*="post-content"] p',
    'div[class*="single-post-content"] p',
    'article p', 'div[class*="news_content"] p', 'div[class*="news-content"] p',
    'div[class*="body-text"] p', 'div[class*="article-body"] p', 'main p',
]

async def dismiss_popups(page):
    for sel in ['button[class*="close"]', '[class*="popup"] button',
                '[class*="modal"] button[class*="close"]']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=500):
                await btn.click(timeout=500)
                await asyncio.sleep(0.3)
        except Exception:
            pass

async def get_latest_article_url(page, source: dict) -> str | None:
    list_url    = source['url']
    extra_skip  = source.get('extra_skip', [])
    site_domain = urlparse(list_url).netloc.replace('www.', '')

    try:
        await page.goto(list_url, timeout=45000, wait_until='domcontentloaded')
        # নেটওয়ার্ক idle হওয়ার জন্য অপেক্ষা করো (AJAX content)
        try:
            await page.wait_for_load_state('networkidle', timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(2)
        await dismiss_popups(page)
        # Scroll করো — lazy load trigger করতে
        await page.evaluate("window.scrollTo(0, 600)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, 1200)")
        await asyncio.sleep(1)
    except PWTimeout:
        print(f"    ⚠️ Timeout")
        return None
    except Exception as e:
        print(f"    ⚠️ Error: {e}")
        return None

    def is_valid(link):
        if not link or not link.startswith('http'): return False
        if site_domain not in link: return False
        if link.rstrip('/') == list_url.rstrip('/'): return False
        path  = urlparse(link).path.rstrip('/')
        parts = [p for p in path.split('/') if p]
        if len(parts) < 2: return False
        if extra_skip and any(p in link.lower() for p in extra_skip): return False
        for bad in ['/tag/', '/author/', '/page/', '/feed/', '/wp-admin/', '/search/']:
            if bad in link.lower(): return False
        return True

    # সব link বের করো
    try:
        all_links = await page.eval_on_selector_all(
            'a[href]',
            "els => [...new Set(els.map(e => e.href).filter(Boolean))]"
        )
    except Exception:
        return None

    # Strategy 1: Bengali char ≥15 (article title)
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
                print(f"    📌 Strategy 1 (Bengali)")
                return link
    except Exception:
        pass

    # Strategy 1.5: Jugantor-specific — সরাসরি article section URL খোঁজো
    if 'jugantor' in source.get('id', ''):
        jugantor_sections = ['/politics/', '/tp-city/', '/national-others/', '/district/',
                             '/crime/', '/court/', '/country/', '/economy/', '/campus/',
                             '/agriculture/', '/health/', '/science/', '/sports/']
        for link in all_links:
            if not link or not link.startswith('http'): continue
            if 'jugantor.com' not in link: continue
            if link.rstrip('/') == list_url.rstrip('/'): continue
            if '/location/' in link: continue
            path  = urlparse(link).path
            parts = [p for p in path.rstrip('/').split('/') if p]
            if len(parts) < 2: continue
            # Section + Numeric ID pattern
            last = parts[-1]
            if re.search(r'\d{4,}', last) and any(s in link for s in jugantor_sections):
                print(f"    📌 Strategy 1.5 (Jugantor article)")
                return link

    # Strategy 2: Numeric ID (jugantor style: /section/123456)
    for link in all_links:
        if not is_valid(link): continue
        last = urlparse(link).path.rstrip('/').split('/')[-1]
        if re.search(r'\d{4,}', last):
            print(f"    📌 Strategy 2 (Numeric ID)")
            return link

    # Strategy 3: Long slug (≥20 chars)
    for link in all_links:
        if not is_valid(link): continue
        last = urlparse(link).path.rstrip('/').split('/')[-1]
        if len(last) >= 20:
            print(f"    📌 Strategy 3 (Long slug)")
            return link

    return None

async def scrape_article(page, url: str) -> dict:
    try:
        await page.goto(url, timeout=45000, wait_until='domcontentloaded')
        try:
            await page.wait_for_load_state('networkidle', timeout=6000)
        except Exception:
            pass
        await asyncio.sleep(3)
        await dismiss_popups(page)
    except PWTimeout:
        return {}
    except Exception:
        return {}

    title = ''
    for sel in ['meta[property="og:title"]', 'meta[name="twitter:title"]']:
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
    for sel in ['meta[property="og:image"]', 'meta[name="twitter:image"]']:
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
            print(f"    ⚠️ Article URL পাওয়া যায়নি"); return

        print(f"    🔗 {url}")
        article = await scrape_article(page, url)

        if not article.get('title') or not article.get('content'):
            print(f"    ⚠️ শিরোনাম বা কন্টেন্ট পাওয়া যায়নি"); return

        # Prothom Alo-র জন্য: রাজশাহী সংক্রান্ত কিনা check করো
        if source['id'] == 'prothomalo':
            rajshahi_check = 'রাজশাহী' in article['title'] or 'rajshahi' in article['url'].lower() or 'রাজশাহী' in article['content'][:500]
            if not rajshahi_check:
                print(f"    ⚠️ রাজশাহী সংক্রান্ত নয় — skip: {article['title'][:50]}")
                return

        print(f"    📝 {article['title'][:65]}")
        print(f"    📊 {len(article['content'])} অক্ষর | 🖼️ {'✓' if article['image_url'] else '✗'}")

        ARTICLES.append({
            'title':      article['title'],
            'content':    article['content'],
            'image_url':  article['image_url'],
            'source_url': article['url'],
            'upazila':    source.get('upazila', ''),
        })
        print(f"    ✅ সংগ্রহ হয়েছে!")

    except Exception as e:
        print(f"    ❌ Error: {e}")
    finally:
        await context.close()

async def main():
    layout  = get_layout()
    bd_time = datetime.now(BD_TZ).strftime('%Y-%m-%d %H:%M')

    print(f"{'='*60}")
    print(f"🤖 DPP নিউজ এজেন্ট v5 — {bd_time} (BD)")
    print(f"🗞️  লেআউট: {layout} | সোর্স: {len(SOURCES)}")
    print(f"{'='*60}")

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

    # data/articles.json-এ সেভ করো
    os.makedirs('data', exist_ok=True)
    output = {
        'generated_at': datetime.now(BD_TZ).isoformat(),
        'layout':       layout,
        'articles':     ARTICLES,
    }
    with open('data/articles.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"💾 {len(ARTICLES)} আর্টিকেল → data/articles.json")
    print(f"✅ শেষ। WordPress এখন GitHub থেকে পড়বে।")
    print(f"{'='*60}")

if __name__ == '__main__':
    asyncio.run(main())
