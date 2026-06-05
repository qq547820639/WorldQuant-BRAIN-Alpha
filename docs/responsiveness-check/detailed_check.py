#!/usr/bin/env python3
"""
详细响应式设计检查脚本
"""

import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

BREAKPOINTS = [
    {"width": 320, "height": 900},
    {"width": 375, "height": 900},
    {"width": 768, "height": 900},
    {"width": 1024, "height": 900},
    {"width": 1280, "height": 900},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 900},
    {"width": 2560, "height": 900},
]

async def detailed_check():
    """执行详细检查"""
    output_dir = Path("docs/responsiveness-check")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    screenshot_dir = output_dir / f"screenshots_detailed_{timestamp}"
    screenshot_dir.mkdir(exist_ok=True)

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 900})
        page = await context.new_page()

        await page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        for bp in BREAKPOINTS:
            width = bp["width"]
            print(f"\n详细检查 {width}px...")

            await page.set_viewport_size({"width": width, "height": bp["height"]})
            await page.wait_for_timeout(800)

            # 截图
            screenshot_path = screenshot_dir / f"viewport_{width}px.png"
            await page.screenshot(path=str(screenshot_path), full_page=False)

            # 获取详细布局信息
            layout_info = await page.evaluate("""
                () => {
                    const html = document.documentElement;
                    const viewportWidth = window.innerWidth;
                    const viewportHeight = window.innerHeight;
                    const scrollWidth = html.scrollWidth;
                    const scrollHeight = html.scrollHeight;
                    const hasHorizontalScroll = scrollWidth > viewportWidth;
                    const hasVerticalScroll = scrollHeight > viewportHeight;

                    // 获取首屏可见元素信息
                    const header = document.querySelector('header');
                    const main = document.querySelector('main');

                    const headerInfo = header ? {
                        visible: header.getBoundingClientRect().top < viewportHeight,
                        height: header.getBoundingClientRect().height,
                        children: header.children.length
                    } : null;

                    const mainInfo = main ? {
                        visible: main.getBoundingClientRect().top < viewportHeight,
                        children: main.children.length
                    } : null;

                    // 获取state cards grid信息
                    const stateCards = document.querySelector('.state-card-grid') || document.querySelector('[class*="grid"]');
                    let gridColumns = 1;
                    if (stateCards) {
                        const style = window.getComputedStyle(stateCards);
                        if (style.gridTemplateColumns) {
                            gridColumns = style.gridTemplateColumns.split(' ').length;
                        }
                    }

                    // 检查是否有溢出元素
                    const overflowElements = [];
                    document.querySelectorAll('*').forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.right > viewportWidth + 1 || rect.left < -1) {
                            overflowElements.push({
                                tag: el.tagName,
                                class: el.className?.substring(0, 50),
                                right: Math.round(rect.right),
                                left: Math.round(rect.left),
                                width: Math.round(rect.width)
                            });
                        }
                    });

                    return {
                        viewportWidth,
                        viewportHeight,
                        scrollWidth,
                        scrollHeight,
                        hasHorizontalScroll,
                        hasVerticalScroll,
                        headerInfo,
                        mainInfo,
                        gridColumns,
                        overflowElements: overflowElements.slice(0, 10)
                    };
                }
            """)

            print(f"  视口: {layout_info['viewportWidth']}x{layout_info['viewportHeight']}")
            print(f"  页面: {layout_info['scrollWidth']}x{layout_info['scrollHeight']}")
            print(f"  水平滚动: {layout_info['hasHorizontalScroll']}")
            print(f"  网格列数: {layout_info['gridColumns']}")
            print(f"  溢出元素: {len(layout_info['overflowElements'])}")

            results.append({
                "width": width,
                "layout": layout_info
            })

        await browser.close()

    # 生成详细报告
    report_lines = []
    report_lines.append("# 响应式设计详细检查报告")
    report_lines.append(f"\n**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"**URL**: http://127.0.0.1:8765/")
    report_lines.append(f"**截图目录**: {screenshot_dir}")
    report_lines.append("\n## 布局分析")

    prev_cols = None
    prev_overflow = None
    prev_width = None

    for result in results:
        width = result["width"]
        info = result["layout"]

        report_lines.append(f"\n### {width}px 视口")
        report_lines.append(f"\n- 视口尺寸: {info['viewportWidth']}x{info['viewportHeight']}px")
        report_lines.append(f"- 页面尺寸: {info['scrollWidth']}x{info['scrollHeight']}px")

        issues = []

        if info['hasHorizontalScroll']:
            issues.append("**水平溢出**: 出现水平滚动条")

        if info['overflowElements']:
            report_lines.append(f"- **溢出元素**: {len(info['overflowElements'])}个")
            for el in info['overflowElements'][:3]:
                report_lines.append(f"  - `{el['tag']}` (class: {el['class']}) 位置: {el['left']}px - {el['right']}px")

        grid_col_note = ""
        if width < 640 and info['gridColumns'] > 2:
            issues.append(f"**网格列数过多**: 在{width}px宽度下有{info['gridColumns']}列")
            grid_col_note = f" (注意: {info['gridColumns']}列在小屏可能过窄)"
        elif width >= 1024 and info['gridColumns'] < 5:
            grid_col_note = f" (当前{info['gridColumns']}列)"

        report_lines.append(f"- 网格列数: {info['gridColumns']}列{grid_col_note}")

        if info['headerInfo']:
            report_lines.append(f"- Header: 高度{info['headerInfo']['height']}px, {info['headerInfo']['children']}个子元素")

        if issues:
            report_lines.append(f"- **问题**: {'; '.join(issues)}")
        else:
            report_lines.append("- **状态**: 无明显布局问题")

        # 记录转换
        if prev_cols is not None and info['gridColumns'] != prev_cols:
            report_lines.append(f"\n  **[转换]** {prev_cols}列 → {info['gridColumns']}列 (在 {prev_width}px → {width}px)")

        prev_cols = info['gridColumns']
        prev_overflow = info['hasHorizontalScroll']
        prev_width = width

    # 总结
    report_lines.append("\n## 总结")

    all_pass = all(not r["layout"]["hasHorizontalScroll"] for r in results)
    grid_transitions = []
    for i in range(1, len(results)):
        if results[i]["layout"]["gridColumns"] != results[i-1]["layout"]["gridColumns"]:
            grid_transitions.append(f"{results[i-1]['width']}px→{results[i]['width']}px: {results[i-1]['layout']['gridColumns']}列→{results[i]['layout']['gridColumns']}列")

    if all_pass:
        report_lines.append("\n**所有断点测试通过**，未发现严重布局问题。")
    else:
        report_lines.append("\n**存在布局问题，需要修复。**")

    if grid_transitions:
        report_lines.append(f"\n**网格列数转换点**: {', '.join(grid_transitions)}")

    # 保存报告
    report_path = output_dir / f"detailed-report-{timestamp}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\n\n报告已生成: {report_path}")
    return report_path, screenshot_dir

if __name__ == "__main__":
    asyncio.run(detailed_check())