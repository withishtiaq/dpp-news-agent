#!/usr/bin/env python3
"""
DPP নিউজ এজেন্ট — Final (Debug version)
"""

import asyncio
import json
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

SOURCE_URL = 'https://padmatimes24.com/rajshahi/'
BD_TZ      = timezone(timedelta(hours=6))

def get_layout() -> str:
    layouts = ['layout1', 'layout2', 'layout3', 'layout4', 'layout5', 'layout6']
    return layouts[datetime.now(BD_TZ).hour % 6]

CONTENT_SELECTORS = [
    'div.entry-content p',
    'div[class*="post-content"] p',
    'div[class*="article-content"] p',
    'div[class*="news_content"] p',
    'article p',
    'main p',
    'p',
]

UPAZILA_LIST = ['পবা','মোহনপুর','চারঘাট','পুঠিয়া','দুর্গাপুর','বাগমারা','গোদাগাড়ী','তানোর','বাঘা']

def detect_upazila(text: str) -> str:
    for u in UPAZILA_LIST:
        if u in text:
            return u
    return 'রাজশাহী শহর'

async def get_article_urls(page) -> list:
    print(f"\n🔗 Listing page: {SOURCE_URL}")

    try:
        response = await page.goto(SOURCE_URL, timeout=45000, wait_until='domcontentloaded')
        print(f"  📡 HTTP status: {response.status if response else 'N/A'}")
    except Exception as e:
        print(f"  ❌ Goto error: {e}")
        return []

    await asyncio.sleep(5)

    # Page info
    print(f"  📍 Final URL: {page.url}")
    try:
        title = await page.title()
        print(f"  📄 Title: {title}")
    except Exception:
        pass

    # Screenshot সেভ করো — Playwright কী দেখছে তা বোঝার জন্য
    os.makedirs('data', exist_ok=True)
    try:
        await page.screenshot(path='data/debug.png', full_page=False)
        print(f"  📸 Screenshot → data/debug.png")
    except Exception as e:
        print(f"  ⚠️ Screenshot error: {e}")

    # Page HTML (প্রথম ৫০০ অক্ষর)
    try:
        html = await page.content()
        print(f"  📜 HTML length: {len(html)}")
        print(f"  📜 HTML preview: {html[:300].strip()}")
    except Exception:
        pass

    # সব link
    try:
        all_links = await page.eval_on_selector_all(
            'a[href]',
            "els => [...new Set(els.map(e => e.href).filter(Boolean))]"
        )
        print(f"  🔗 Total a[href]: {len(all_links)}")
        for l in all_links[:5]:
            print(f"      → {l}")
    except Exception as e:
        print(f"  ❌ Link extract error: {e}")
        all_links = []

    if not all_links:
        return []

    # Article URLs filter করো
    article_urls = []
    for link in all_links:
        if 'padmatimes24.com' not in link: continue
        if link.rstrip('/') == SOURCE_URL.rstrip('/'): continue
        path  = urlparse(link).path.rstrip('/')
        parts = [p for p in path.split('/') if p]
        if len(parts) < 2: continue
        if any(s in link for s in ['/page/', '/tag/', '/author/', '/wp-admin/', '/feed/']): continue
        if len(parts[-1]) >= 5:
            article_urls.append(link)

    print(f"  📊 Article URLs found: {len(article_urls)}")
    return article_urls[:10]

async def scrape_article(page, url: str) -> dict | None:
    try:
        await page.goto(url, timeout=45000, wait_until='domcontentloaded')
        await asyncio.sleep(3)
    except Exception:
        return None

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
                sel, "els => els.map(e => e.innerText.trim()).filter(t => t.length > 20)"
            )
            if paras:
                bn = [p for p in paras if len([c for c in p if '\u0980'<=c<='\u09FF'])>=8]
                if bn:
                    j = '\n\n'.join(bn)
                    if len(j) >= 80:
                        content = j[:6000]; break
        except Exception:
            continue

    if not title or not content:
        return None

    return {
        'title':      title,
        'content':    content,
        'image_url':  image_url,
        'source_url': url,
        'upazila':    detect_upazila(title+' '+content),
    }

async def main():
    layout  = get_layout()
    bd_time = datetime.now(BD_TZ).strftime('%Y-%m-%d %H:%M')

    print(f"{'='*55}")
    print(f"🤖 DPP নিউজ এজেন্ট — {bd_time} (BD)")
    print(f"🗞️  লেআউট: {layout} | সোর্স: পদ্মা টাইমস ২৪")
    print(f"{'='*55}")

    articles = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-setuid-sandbox',
                  '--disable-dev-shm-usage','--disable-gpu',
                  '--disable-blink-features=AutomationControlled'],
        )

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            locale='bn-BD',
            viewport={'width': 1366, 'height': 768},
            extra_http_headers={
                'Accept-Language': 'bn-BD,bn;q=0.9,en-US;q=0.8',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
        )
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await context.new_page()
        article_urls = await get_article_urls(page)
        await context.close()

        for i, url in enumerate(article_urls, 1):
            print(f"\n[{i}/{len(article_urls)}] {url}")
            ctx2 = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                locale='bn-BD', viewport={'width':1366,'height':768},
            )
            await ctx2.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            p2 = await ctx2.new_page()
            try:
                art = await scrape_article(p2, url)
                if art:
                    print(f"  📝 {art['title'][:60]}")
                    print(f"  📊 {len(art['content'])}c | 🖼️{'✓'if art['image_url']else'✗'} | 📍{art['upazila']}")
                    articles.append(art)
                else:
                    print(f"  ⚠️ Content পাওয়া যায়নি")
            except Exception as e:
                print(f"  ❌ {e}")
            finally:
                await ctx2.close()
            await asyncio.sleep(2)

        await browser.close()

    os.makedirs('data', exist_ok=True)
    with open('data/articles.json','w',encoding='utf-8') as f:
        json.dump({'generated_at':datetime.now(BD_TZ).isoformat(),'layout':layout,'articles':articles},f,ensure_ascii=False,indent=2)

    print(f"\n{'='*55}")
    print(f"💾 {len(articles)} আর্টিকেল → data/articles.json")
    print(f"✅ শেষ।")
    print(f"{'='*55}")

if __name__ == '__main__':
    asyncio.run(main())
