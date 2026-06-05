#!/usr/bin/env python3
"""
检查服务器返回的HTML内容
"""

import asyncio
from playwright.async_api import async_playwright

async def check_server_html():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        # 拦截HTML响应
        async def handle_response(response):
            if "text/html" in response.headers.get("content-type", ""):
                body = await response.body()
                text = body.decode("utf-8") if body else ""
                print(f"\n=== HTML Response from {response.url} ===")
                print(f"Status: {response.status}")
                print(f"Content-Type: {response.headers.get('content-type')}")
                print(f"\nHTML content (first 2000 chars):")
                print(text[:2000])

                import re
                src_matches = re.findall(r'src=([^\s>]+)', text)
                print(f"\nJS files found in HTML: {[m for m in src_matches if '.js' in m]}")

        page.on("response", handle_response)

        print("Loading page...")
        await page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
        await page.wait_for_timeout(2000)

if __name__ == "__main__":
    asyncio.run(check_server_html())