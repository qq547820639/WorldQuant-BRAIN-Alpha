#!/usr/bin/env python3
"""
网络请求详细检查脚本
"""

import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

async def network_check():
    """检查网络请求和响应"""
    output_dir = Path("docs/responsiveness-check")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        # 记录所有网络请求和响应
        requests = []
        responses = []
        errors = []

        def on_request(request):
            requests.append({
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type
            })

        def on_response(response):
            responses.append({
                "url": response.url,
                "status": response.status,
                "headers": dict(response.headers)
            })

        def on_console(msg):
            if msg.type == "error":
                errors.append(f"[{msg.type}] {msg.text}")

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("console", on_console)

        print("访问页面...")
        await page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
        await page.wait_for_timeout(5000)

        print(f"\n请求数量: {len(requests)}")
        print(f"响应数量: {len(responses)}")
        print(f"控制台错误: {len(errors)}")

        print("\n=== 所有请求 ===")
        for req in requests:
            print(f"  {req['method']} {req['url']} [{req['resource_type']}]")

        print("\n=== 所有响应 ===")
        for resp in responses:
            print(f"  {resp['status']} {resp['url']}")

        print("\n=== 控制台错误 ===")
        for err in errors:
            print(f"  {err}")

        # 检查页面内容
        page_content = await page.evaluate("""
            () => {
                return {
                    rootChildren: document.getElementById('root')?.children.length || 0,
                    rootInnerHTML: document.getElementById('root')?.innerHTML.substring(0, 500) || 'N/A',
                    bodyClasses: document.body.className,
                    allText: document.body.textContent?.substring(0, 200)
                };
            }
        """)

        print("\n=== 页面内容 ===")
        print(f"Root 子元素: {page_content['rootChildren']}")
        print(f"Root HTML: {page_content['rootInnerHTML']}")
        print(f"Body classes: {page_content['bodyClasses']}")
        print(f"页面文本: {page_content['allText']}")

        # 保存报告
        report_path = output_dir / f"network-check-{timestamp}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# 网络请求检查报告\n\n")
            f.write(f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## 请求\n\n")
            for req in requests:
                f.write(f"- {req['method']} {req['url']} [{req['resource_type']}]\n")
            f.write("\n## 响应\n\n")
            for resp in responses:
                f.write(f"- {resp['status']} {resp['url']}\n")
            f.write("\n## 控制台错误\n\n")
            for err in errors:
                f.write(f"- {err}\n")
            f.write("\n## 页面内容\n\n")
            f.write(f"Root 子元素: {page_content['rootChildren']}\n\n")
            f.write(f"Root HTML: {page_content['rootInnerHTML']}\n\n")
            f.write(f"Body classes: {page_content['bodyClasses']}\n\n")
            f.write(f"页面文本: {page_content['allText']}\n")

        print(f"\n报告已保存: {report_path}")

    return report_path

if __name__ == "__main__":
    asyncio.run(network_check())