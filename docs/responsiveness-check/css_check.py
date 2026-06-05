#!/usr/bin/env python3
"""
详细CSS类和应用检查脚本
"""

import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

BREAKPOINTS = [
    {"width": 320, "height": 900, "name": "手机小屏"},
    {"width": 375, "height": 900, "name": "手机标准"},
    {"width": 640, "height": 900, "name": "手机大屏/平板小屏"},
    {"width": 768, "height": 900, "name": "平板竖屏"},
    {"width": 1024, "height": 900, "name": "平板横屏"},
    {"width": 1280, "height": 900, "name": "笔记本"},
    {"width": 1440, "height": 900, "name": "桌面"},
    {"width": 1920, "height": 900, "name": "全高清"},
]

async def detailed_check():
    """执行详细检查"""
    output_dir = Path("docs/responsiveness-check")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    screenshot_dir = output_dir / f"screenshots_css_{timestamp}"
    screenshot_dir.mkdir(exist_ok=True)

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 900})
        page = await context.new_page()

        await page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
        await page.wait_for_timeout(3000)  # 等待数据加载

        for bp in BREAKPOINTS:
            width = bp["width"]
            name = bp["name"]
            print(f"\n检查 {width}px ({name})...")

            await page.set_viewport_size({"width": width, "height": bp["height"]})
            await page.wait_for_timeout(1000)

            # 截图
            screenshot_path = screenshot_dir / f"viewport_{width}px.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)

            # 获取CSS类和计算样式
            css_info = await page.evaluate("""
                () => {
                    // 查找grid容器
                    const gridContainers = [];
                    document.querySelectorAll('[class*="grid"]').forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        gridContainers.push({
                            class: el.className,
                            tag: el.tagName,
                            rect: {
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                left: Math.round(rect.left),
                                right: Math.round(rect.right)
                            },
                            gridTemplateColumns: style.gridTemplateColumns,
                            gridTemplateRows: style.gridTemplateRows,
                            display: style.display
                        });
                    });

                    // 查找卡片
                    const cards = [];
                    document.querySelectorAll('.state-card, [class*="state-card"]').forEach((el, i) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        cards.push({
                            index: i,
                            visible: rect.width > 0 && rect.height > 0,
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            gridColumn: style.gridColumn,
                            gridRow: style.gridRow
                        });
                    });

                    // 检查body的class
                    const bodyClass = document.body.className;

                    return {
                        gridContainers,
                        cards,
                        bodyClass,
                        viewportWidth: window.innerWidth,
                        viewportHeight: window.innerHeight
                    };
                }
            """)

            print(f"  视口: {css_info['viewportWidth']}x{css_info['viewportHeight']}")
            print(f"  Grid容器数: {len(css_info['gridContainers'])}")
            for i, gc in enumerate(css_info['gridContainers']):
                print(f"    容器{i+1}: {gc['class']}")
                print(f"      尺寸: {gc['rect']['width']}x{gc['rect']['height']}")
                print(f"      grid-template-columns: {gc['gridTemplateColumns']}")
                print(f"      display: {gc['display']}")
            print(f"  卡片数: {len(css_info['cards'])}")
            visible_cards = [c for c in css_info['cards'] if c['visible']]
            print(f"  可见卡片: {len(visible_cards)}")

            results.append({
                "width": width,
                "name": name,
                "css_info": css_info
            })

        await browser.close()

    # 生成报告
    report_lines = []
    report_lines.append("# 响应式设计检查报告 - CSS布局分析")
    report_lines.append(f"\n**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"**URL**: http://127.0.0.1:8765/")
    report_lines.append(f"**截图目录**: {screenshot_dir}")
    report_lines.append("\n## CSS Grid布局分析")
    report_lines.append("\n| 宽度 | 设备类型 | 网格容器 | grid-template-columns | 可见卡片数 |")
    report_lines.append("|------|----------|----------|----------------------|------------|")

    for result in results:
        width = result["width"]
        name = result["name"]
        info = result["css_info"]

        grid_desc = f"{len(info['gridContainers'])}个"
        if info['gridContainers']:
            first_grid = info['gridContainers'][0]
            grid_cols = first_grid['gridTemplateColumns'].replace('px', '').replace('fr', '')[:30]
            grid_desc = f"{len(info['gridContainers'])}个 ({grid_cols})"

        visible_count = len([c for c in info['cards'] if c['visible']])
        report_lines.append(f"| {width}px | {name} | {grid_desc} | {info['gridContainers'][0]['gridTemplateColumns'] if info['gridContainers'] else 'N/A'} | {visible_count} |")

    report_lines.append("\n## 详细分析")

    for result in results:
        width = result["width"]
        name = result["name"]
        info = result["css_info"]

        report_lines.append(f"\n### {width}px - {name}")

        if info['gridContainers']:
            for i, gc in enumerate(info['gridContainers']):
                report_lines.append(f"\n**Grid容器 {i+1}**:")
                report_lines.append(f"- class: `{gc['class']}`")
                report_lines.append(f"- 尺寸: {gc['rect']['width']}x{gc['rect']['height']}")
                report_lines.append(f"- grid-template-columns: `{gc['gridTemplateColumns']}`")
                report_lines.append(f"- display: `{gc['display']}`")
        else:
            report_lines.append("\n未找到grid容器")

        if info['cards']:
            visible_cards = [c for c in info['cards'] if c['visible']]
            report_lines.append(f"\n**卡片**: 共{len(info['cards'])}个，{len(visible_cards)}个可见")
            if visible_cards:
                report_lines.append("\n| 序号 | 宽度 | 高度 |")
                report_lines.append("|------|------|------|")
                for card in visible_cards[:5]:
                    report_lines.append(f"| {card['index']+1} | {card['width']}px | {card['height']}px |")
        else:
            report_lines.append("\n未找到卡片元素")

    # 检测断点转换
    report_lines.append("\n## 断点转换检测")

    prev_cols = None
    transitions = []
    for result in results:
        width = result["width"]
        cols_str = result["css_info"]['gridContainers'][0]['gridTemplateColumns'] if result["css_info"]['gridContainers'] else "none"
        cols_count = len(cols_str.split(' ')) if cols_str and cols_str != 'none' else 0

        if prev_cols is not None and cols_count != prev_cols:
            transitions.append(f"- **{prev_cols}列 → {cols_count}列**: 在 {width}px 断点")
        prev_cols = cols_count

    if transitions:
        for t in transitions:
            report_lines.append(t)
    else:
        report_lines.append("\n未检测到网格列数变化，所有断点均使用相同列数。")
        report_lines.append("\n**注意**: 这可能表示Tailwind响应式类未正确应用，或页面数据尚未加载。")

    # 保存报告
    report_path = output_dir / f"css-report-{timestamp}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\n\n报告已生成: {report_path}")
    return report_path, screenshot_dir

if __name__ == "__main__":
    asyncio.run(detailed_check())