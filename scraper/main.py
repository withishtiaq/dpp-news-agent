#!/usr/bin/env python3
"""
DPP নিউজ এজেন্ট — v6 (Simplified)
৪টা সাইট থেকে রাজশাহীর আপডেটেড নিউজ সংগ্রহ করে।
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
ARTICLES = []

def get_layout() -> str:
    layouts = ['layout1', 'layout2', 'layout3', 'layout4', 'layout5', 'layout6']
    return layouts[datetime.now(BD_TZ).hour % 6]

SOURCES = [
    {
        'id':   'uttaraprotidin',
        'name': 'উত্তরা প্রতিদিন',
        'url':  'https://www.uttaraprotidin.com/category/uttranchl',
        'skip': ['/category/'],
    },
    {
        'id':   'jugantor',
        'name': 'যুগান্তর',
        'url':  'https://www.jugantor.com/location/rajshahi-rajshahi',
        'skip': ['/location/'],
    },
    {
        'id':   'jagonews24',
        'name': 'জাগো নিউজ ২৪',
        'url':  'https://www.jagonews24.com/bangladesh/rajshahi/rajshahi',
        'skip': [],
    },
    {
        'id':   'ajkerpatrika',
        'name': 'আজকের পত্রিকা',
        'url':  'https://www.ajkerpatrika.com/country/rajshahi-division/rajshahi',
        'skip': ['/country/', '/international/', '/world/', '/business/', '/sports/', '/entertainment/'],
    },
]

CONTENT_SELECTORS = [
    'div.col-xl-8 div.details p',
    'div.col-xl-8 p',
    'div[class*="news_dtl_body"] p',
    'div[class*="news_dtl"] p',
    'div[class*="dtls_body"] p',
    '.details p',
    'div.entry-content p',
    'div[class*="post-content"] p',
    'div[class*="single-post"] p',
    'div[class*="news-details"] p',
    'div[class*="details_body"] p',
    'div[class*="dtl_body"] p',
    'div[class*="article-content"] p',
    'div[class*="content-wrapper"] p',
    'article p',
    'div[class*="news_content"] p',
    'div[class*="body-text"] p',
    'main p',
    'p',
]

async def dismiss_popups(page):
    for sel in ['button[class*="close"]', '[class*="popup"] button',
                '[class*="modal"] button[class*="close"]', '[class*="cookie"] button']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=500):
                await btn.click(timeout=500)
                await asyncio.sleep(0.3)
        except Exception:
            pass

async def get_latest_article_url(page, source: dict) -> str | None:
    list_url    = source['url']
    skip        = source.get('skip', [])
    site_domain = urlparse(list_url).netloc.replace('www.', '')

    try:
        await page.goto(list_url, timeout=45000, wait_until='domcontentloaded')
        try:
            await page.wait_for_load_state('networkidle', timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(3)
        await dismiss_popups(page)
        await page.evaluate("window.scrollTo(0, 600)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, 1200)")
        await asyncio.sleep(1)
    except PWTimeout:
        print(f"    ⚠️ Page load timeout")
        return None
    except Exception as e:
        print(f"    ⚠️ Page load error: {e}")
        return None

    def is_valid(link):
        if not link or not link.startswith('http'): return False
        if site_domain not in link: return False
        if link.rstrip('/') == list_url.rstrip('/'): return False
        path  = urlparse(link).path.rstrip('/')
        parts = [p for p in path.split('/') if p]
        if len(parts) < 2: return False
        for bad in ['/tag/', '/author/', '/page/', '/feed/', '/wp-admin/', '/search/']:
            if bad in link.lower(): return False
        if skip and any(s in link.lower() for s in skip): return False
        return True

    # jagonews24-র জন্য article load হওয়ার জন্য অপেক্ষা করো
    if source.get('id') == 'jagonews24':
        try:
            await page.wait_for_selector('h2 a, h3 a, .news-title a, article a', timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(3)

    try:
        all_links = await page.eval_on_selector_all(
            'a[href]',
            "els => [...new Set(els.map(e => e.href).filter(Boolean))]"
        )
        print(f"    📊 মোট link: {len(all_links)}")
    except Exception:
        return None

    # Strategy 1: Bengali title
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
                print(f"    📌 Strategy 1 (Bengali title)")
                return link
    except Exception:
        pass

    # Strategy 1.5: Jugantor article sections
    if source['id'] == 'jugantor':
        jugantor_secs = ['/politics/', '/tp-city/', '/national-others/', '/district/',
                         '/crime/', '/court/', '/economy/', '/campus/', '/agriculture/']
        for link in all_links:
            if not is_valid(link): continue
            if '/location/' in link: continue
            last = urlparse(link).path.rstrip('/').split('/')[-1]
            if re.search(r'\d{4,}', last) and any(s in link for s in jugantor_secs):
                print(f"    📌 Strategy 1.5 (Jugantor section)")
                return link

    # Strategy 2: Numeric ID
    for link in all_links:
        if not is_valid(link): continue
        last = urlparse(link).path.rstrip('/').split('/')[-1]
        if re.search(r'\d{4,}', last):
            print(f"    📌 Strategy 2 (Numeric ID)")
            return link

    # Strategy 3: Long slug
    for link in all_links:
        if not is_valid(link): continue
        last = urlparse(link).path.rstrip('/').split('/')[-1]
        if len(last) >= 20:
            print(f"    📌 Strategy 3 (Long slug)")
            return link

    return None

async def scrape_article(page, url: str, source_id: str = '') -> dict:
    wait_time = 8 if source_id == 'jugantor' else 4

    try:
        await page.goto(url, timeout=45000, wait_until='domcontentloaded')
        try:
            await page.wait_for_load_state('networkidle', timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(wait_time)
        await dismiss_popups(page)
    except PWTimeout:
        print(f"    ⚠️ Article timeout")
        return {}
    except Exception as e:
        print(f"    ⚠️ Article error: {e}")
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
        try: title = re.sub(r'\s*[\|\-\u2013\u2014]\s*.{0,40}$', '', await page.title()).strip()
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
                bn_paras = [p for p in paras if len([c for c in p if '\u0980' <= c <= '\u09FF']) >= 10]
                if bn_paras:
                    joined = '\n\n'.join(bn_paras)
                    if len(joined) >= 100:
                        content = joined[:5000]; break
        except Exception:
            continue

    if not content:
        try:
            desc = await page.get_attribute('meta[property="og:description"]', 'content', timeout=2000)
            if desc and len(desc.strip()) > 50:
                content = desc.strip()
        except Exception:
            pass

    return {'title': title, 'content': content, 'image_url': image_url, 'url': url}

async def process_source(browser, source: dict, layout: str):
    print(f"\n{'─'*55}")
    print(f"📰 {source['name']}  →  {source['url']}")

    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        locale='bn-BD',
        viewport={'width': 1366, 'height': 768},
        extra_http_headers={'Accept-Language': 'bn-BD,bn;q=0.9,en-US;q=0.8'},
    )
    page = await context.new_page()

    try:
        article_url = await get_latest_article_url(page, source)
        if not article_url:
            print(f"    ⚠️ Article URL পাওয়া যায়নি"); return

        print(f"    🔗 {article_url}")
        article = await scrape_article(page, article_url, source['id'])

        if not article.get('title') or not article.get('content'):
            print(f"    ⚠️ শিরোনাম বা কন্টেন্ট পাওয়া যায়নি"); return

        # সব সোর্সের জন্য: রাজশাহী check
        title_has  = 'রাজশাহী' in article['title']
        content_has = 'রাজশাহী' in article['content']
        if title_has:
            print(f"    ✔️ শিরোনামে রাজশাহী পাওয়া গেছে")
        elif content_has:
            print(f"    ✔️ বিস্তারিতে রাজশাহী পাওয়া গেছে")
        else:
            print(f"    ⚠️ রাজশাহী সংক্রান্ত নয় — skip: {article['title'][:50]}")
            return

        print(f"    📝 {article['title'][:65]}")
        print(f"    📊 {len(article['content'])} অক্ষর | 🖼️ {'✓' if article['image_url'] else '✗'}")

        ARTICLES.append({
            'title':      article['title'],
            'content':    article['content'],
            'image_url':  article['image_url'],
            'source_url': article['url'],
            'upazila':    '',
        })
        print(f"    ✅ সংগ্রহ হয়েছে!")

    except Exception as e:
        print(f"    ❌ Error: {e}")
    finally:
        await context.close()

async def main():
    layout  = get_layout()
    bd_time = datetime.now(BD_TZ).strftime('%Y-%m-%d %H:%M')

    print(f"{'='*55}")
    print(f"🤖 DPP নিউজ এজেন্ট v6 — {bd_time} (BD)")
    print(f"🗞️  লেআউট: {layout} | সোর্স: {len(SOURCES)}")
    print(f"{'='*55}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-setuid-sandbox',
                  '--disable-dev-shm-usage','--disable-gpu'],
        )
        for source in SOURCES:
            try:
                await process_source(browser, source, layout)
                await asyncio.sleep(3)
            except Exception as e:
                print(f"\n❌ {source['name']}: {e}")
        await browser.close()

    os.makedirs('data', exist_ok=True)
    output = {
        'generated_at': datetime.now(BD_TZ).isoformat(),
        'layout':       layout,
        'articles':     ARTICLES,
    }
    with open('data/articles.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*55}")
    print(f"💾 {len(ARTICLES)} আর্টিকেল → data/articles.json")
    print(f"✅ শেষ। WordPress GitHub থেকে পড়বে।")
    print(f"{'='*55}")

if __name__ == '__main__':
    asyncio.run(main())
