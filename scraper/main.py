#!/usr/bin/env python3
"""
DPP নিউজ এজেন্ট — Final (Simple)
পদ্মা টাইমস ২৪ থেকে রাজশাহীর সব নতুন নিউজ সংগ্রহ করে।
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
    'div[class*="single-post"] p',
    'div[class*="article-content"] p',
    'div[class*="news_content"] p',
    'article p',
    'main p',
    'p',
]

UPAZILA_LIST = [
    'পবা', 'মোহনপুর', 'চারঘাট', 'পুঠিয়া',
    'দুর্গাপুর', 'বাগমারা', 'গোদাগাড়ী', 'তানোর', 'বাঘা',
]

def detect_upazila(text: str) -> str:
    for u in UPAZILA_LIST:
        if u in text:
            return u
    return 'রাজশাহী শহর'

async def dismiss_popups(page):
    for sel in [
        'button[class*="close"]', '[class*="popup"] button',
        '[class*="overlay"] button', '[id*="close"]',
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=500):
                await btn.click(timeout=500)
                await asyncio.sleep(0.3)
        except Exception:
            pass

async def get_article_urls(page) -> list:
    """Listing page থেকে সব article URL বের করো"""
    print(f"\n🔗 Listing page লোড করছি: {SOURCE_URL}")
    try:
        await page.goto(SOURCE_URL, timeout=45000, wait_until='domcontentloaded')
        try:
            await page.wait_for_load_state('networkidle', timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(3)
        await dismiss_popups(page)
    except Exception as e:
        print(f"  ❌ Listing page error: {e}")
        return []

    # সব article link বের করো
    try:
        all_links = await page.eval_on_selector_all(
            'a[href]',
            "els => [...new Set(els.map(e => e.href).filter(Boolean))]"
        )
    except Exception:
        return []

    article_urls = []
    seen = set()
    for link in all_links:
        if not link or link in seen:
            continue
        seen.add(link)
        if 'padmatimes24.com' not in link:
            continue
        if link.rstrip('/') == SOURCE_URL.rstrip('/'):
            continue
        path  = urlparse(link).path.rstrip('/')
        parts = [p for p in path.split('/') if p]
        if len(parts) < 2:
            continue
        # Skip category/tag/author pages
        for bad in ['/category/', '/tag/', '/author/', '/page/', '/rajshahi/$']:
            if bad.rstrip('$') in link.lower():
                break
        else:
            # Article URL — numeric ID বা long slug
            last = parts[-1]
            if re.search(r'\d{3,}', last) or len(last) >= 15:
                article_urls.append(link)

    print(f"  📊 {len(article_urls)} টি article URL পাওয়া গেছে")
    return article_urls[:15]  # সর্বোচ্চ ১৫টা process করবো

async def scrape_article(page, url: str) -> dict | None:
    """একটা article page থেকে title, content, image বের করো"""
    try:
        await page.goto(url, timeout=45000, wait_until='domcontentloaded')
        try:
            await page.wait_for_load_state('networkidle', timeout=6000)
        except Exception:
            pass
        await asyncio.sleep(3)
        await dismiss_popups(page)
    except PWTimeout:
        return None
    except Exception:
        return None

    # শিরোনাম
    title = ''
    for sel in ['meta[property="og:title"]', 'meta[name="twitter:title"]']:
        try:
            v = await page.get_attribute(sel, 'content', timeout=2000)
            if v and len(v.strip()) > 5:
                title = v.strip(); break
        except Exception:
            pass
    if not title:
        try:
            title = (await page.inner_text('h1', timeout=3000)).strip()
        except Exception:
            pass

    # ফিচার ইমেজ
    image_url = ''
    for sel in ['meta[property="og:image"]', 'meta[name="twitter:image"]']:
        try:
            v = await page.get_attribute(sel, 'content', timeout=2000)
            if v and v.strip().startswith('http'):
                image_url = v.strip(); break
        except Exception:
            pass

    # বিস্তারিত content
    content = ''
    for sel in CONTENT_SELECTORS:
        try:
            paras = await page.eval_on_selector_all(
                sel,
                "els => els.map(e => e.innerText.trim()).filter(t => t.length > 20)"
            )
            if paras:
                bn_paras = [
                    p for p in paras
                    if len([c for c in p if '\u0980' <= c <= '\u09FF']) >= 8
                ]
                if bn_paras:
                    joined = '\n\n'.join(bn_paras)
                    if len(joined) >= 80:
                        content = joined[:6000]; break
        except Exception:
            continue

    if not title or not content:
        return None

    return {
        'title':      title,
        'content':    content,
        'image_url':  image_url,
        'source_url': url,
        'upazila':    detect_upazila(title + ' ' + content),
    }

async def main():
    layout  = get_layout()
    bd_time = datetime.now(BD_TZ).strftime('%Y-%m-%d %H:%M')

    print(f"{'='*55}")
    print(f"🤖 DPP নিউজ এজেন্ট — {bd_time} (BD)")
    print(f"🗞️  লেআউট: {layout}")
    print(f"📰 সোর্স: পদ্মা টাইমস ২৪")
    print(f"{'='*55}")

    articles = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox', '--disable-setuid-sandbox',
                '--disable-dev-shm-usage', '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
            ],
        )

        # ── Step 1: Listing page থেকে URLs বের করো ──────────
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            locale='bn-BD',
            viewport={'width': 1366, 'height': 768},
            extra_http_headers={'Accept-Language': 'bn-BD,bn;q=0.9,en-US;q=0.8'},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()
        article_urls = await get_article_urls(page)
        await context.close()

        # ── Step 2: প্রতিটা article scrape করো ──────────────
        for i, url in enumerate(article_urls, 1):
            print(f"\n[{i}/{len(article_urls)}] {url}")

            context2 = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                locale='bn-BD',
                viewport={'width': 1366, 'height': 768},
            )
            await context2.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page2 = await context2.new_page()

            try:
                article = await scrape_article(page2, url)
                if article:
                    print(f"  📝 {article['title'][:60]}")
                    print(f"  📊 {len(article['content'])} অক্ষর | 🖼️ {'✓' if article['image_url'] else '✗'} | 📍 {article['upazila']}")
                    articles.append(article)
                else:
                    print(f"  ⚠️ Content পাওয়া যায়নি")
            except Exception as e:
                print(f"  ❌ Error: {e}")
            finally:
                await context2.close()

            await asyncio.sleep(2)

        await browser.close()

    # ── Step 3: data/articles.json-এ সেভ করো ────────────────
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
    asyncio.run(main())
