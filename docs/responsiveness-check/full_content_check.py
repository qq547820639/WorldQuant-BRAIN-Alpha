#!/usr/bin/env python3
"""
页面完整内容检查脚本
"""

import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

async def full_content_check():
    """检查页面完整内容"""
    output_dir = Path("docs/responsiveness-check")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    screenshot_dir = output_dir / f"screenshots_full_{timestamp}"
    screenshot_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 900})
        page = await context.new_page()

        # 启用日志
        page.on("console", lambda msg: print(f"CONSOLE {msg.type}: {msg.text}") if "error" in msg.type.lower() else None)

        await page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
        await page.wait_for_timeout(5000)  # 等待5秒让数据加载

        # 截图
        screenshot_path = screenshot_dir / "full_page_1920px.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)

        # 获取页面完整内容
        content_info = await page.evaluate("""
            () => {
                // 获取页面HTML结构
                const body = document.body;
                const html = document.documentElement;

                // 获取所有直接子元素
                const children = Array.from(body.children).map((el, i) => ({
                    index: i,
                    tag: el.tagName,
                    id: el.id || null,
                    class: el.className || null,
                    rect: el.getBoundingClientRect()
                }));

                // 获取header内容
                const header = document.querySelector('header');
                const headerInfo = header ? {
                    innerHTML: header.innerHTML.substring(0, 500),
                    children: header.children.length,
                    textContent: header.textContent?.substring(0, 200)
                } : null;

                // 获取main内容
                const main = document.querySelector('main');
                const mainInfo = main ? {
                    innerHTML: main.innerHTML.substring(0, 1000),
                    children: main.children.length,
                    textContent: main.textContent?.substring(0, 300)
                } : null;

                // 获取所有文本内容
                const allText = document.body.textContent || '';

                // 获取网络错误
                const networkErrors = window.performance ? 
                    window.performance.getEntriesByType('resource').filter(r => r.responseStatus >= 400).map(r => ({
                        name: r.name,
                        status: r.responseStatus
                    })) : [];

                return {
                    bodyClass: body.className,
                    bodyHTML: body.innerHTML.substring(0, 2000),
                    children: children,
                    headerInfo,
                    mainInfo,
                    allTextLength: allText.length,
                    sampleText: allText.substring(0, 500),
                    networkErrors
                };
            }
        """)

        print("\n=== 页面内容分析 ===")
        print(f"\nBody class: {content_info['bodyClass']}")
        print(f"\nBody HTML (前2000字符):\n{content_info['bodyHTML']}")
        print(f"\n\nHeader信息:")
        if content_info['headerInfo']:
            print(f"  子元素数: {content_info['headerInfo']['children']}")
            print(f"  文本内容: {content_info['headerInfo']['textContent']}")
        else:
            print("  未找到header")

        print(f"\n\nMain信息:")
        if content_info['mainInfo']:
            print(f"  子元素数: {content_info['mainInfo']['children']}")
            print(f"  文本内容: {content_info['mainInfo']['textContent']}")
        else:
            print("  未找到main")

        print(f"\n\n页面文本长度: {content_info['allTextLength']}")
        print(f"\n页面文本示例:\n{content_info['sampleText']}")

        print(f"\n\n网络错误: {len(content_info['networkErrors'])}")
        for err in content_info['networkErrors'][:5]:
            print(f"  - {err['name']}: {err['status']}")

        # 检查是否有React组件挂载
        react_root = await page.evaluate("""
            () => {
                const root = document.getElementById('root');
                if (root) {
                    return {
                        exists: true,
                        innerHTML: root.innerHTML.substring(0, 1000),
                        childCount: root.children.length
                    };
                }
                return { exists: false };
            }
        """)

        print(f"\n\nReact Root (#root):")
        print(f"  存在: {react_root['exists']}")
        if react_root['exists']:
            print(f"  子元素数: {react_root['childCount']}")
            print(f"  内容: {react_root['innerHTML']}")

        # 保存完整报告
        report_path = output_dir / f"full-content-{timestamp}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# 页面完整内容检查报告\n")
            f.write(f"\n**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"\n## 页面结构\n")
            f.write(f"\nBody class: {content_info['bodyClass']}\n")
            f.write(f"\n### Body HTML\n\n```html\n{content_info['bodyHTML']}\n```\n")
            f.write(f"\n### Header\n\n")
            if content_info['headerInfo']:
                f.write(f"子元素数: {content_info['headerInfo']['children']}\n\n")
                f.write(f"文本内容: {content_info['headerInfo']['textContent']}\n")
            f.write(f"\n### Main\n\n")
            if content_info['mainInfo']:
                f.write(f"子元素数: {content_info['mainInfo']['children']}\n\n")
                f.write(f"文本内容: {content_info['mainInfo']['textContent']}\n")
            f.write(f"\n### React Root\n\n")
            f.write(f"存在: {react_root['exists']}\n")
            if react_root['exists']:
                f.write(f"子元素数: {react_root['childCount']}\n")
                f.write(f"内容: {react_root['innerHTML']}\n")

        print(f"\n\n报告已保存: {report_path}")
        print(f"截图已保存: {screenshot_dir / 'full_page_1920px.png'}")

    return report_path, screenshot_dir

if __name__ == "__main__":
    asyncio.run(full_content_check())