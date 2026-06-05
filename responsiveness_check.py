#!/usr/bin/env python3
"""
响应式设计检查脚本
测试Web应用在不同视口宽度下的布局表现
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# 测试断点配置
BREAKPOINTS = [
    {"width": 320, "height": 900, "label": "320px - 小手机 (iPhone SE)"},
    {"width": 375, "height": 900, "label": "375px - 标准手机 (iPhone 14)"},
    {"width": 768, "height": 900, "label": "768px - 平板竖屏 (iPad)"},
    {"width": 1024, "height": 900, "label": "1024px - 平板横屏/小笔记本"},
    {"width": 1280, "height": 900, "label": "1280px - 笔记本"},
    {"width": 1440, "height": 900, "label": "1440px - 桌面"},
    {"width": 1920, "height": 900, "label": "1920px - 全高清"},
    {"width": 2560, "height": 900, "label": "2560px - 超宽/4K"},
]

# 布局检查项
LAYOUT_CHECKS = [
    "horizontal_overflow",      # 水平溢出
    "text_overflow",           # 文本溢出
    "navigation_transition",   # 导航转换
    "content_stacking",        # 内容堆叠
    "image_scaling",           # 图片缩放
    "touch_targets",           # 触摸目标
    "whitespace_balance",      # 空白平衡
    "cta_visibility",          # CTA可见性
]


async def check_responsiveness():
    """执行响应式检查"""
    
    # 创建输出目录
    output_dir = Path("docs/responsiveness-check")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    screenshot_dir = output_dir / f"screenshots_{timestamp}"
    screenshot_dir.mkdir(exist_ok=True)
    
    report_lines = []
    report_lines.append("# 响应式设计检查报告")
    report_lines.append(f"\n**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"**URL**: http://127.0.0.1:8765/")
    report_lines.append(f"**模式**: 标准检查 (8个断点)")
    report_lines.append(f"**浏览器工具**: Playwright Python")
    
    issues_summary = []
    
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        # 访问页面
        print("正在访问 http://127.0.0.1:8765/ ...")
        await page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
        await page.wait_for_timeout(2000)  # 等待动画完成
        
        report_lines.append("\n## 总结")
        report_lines.append("\n| 宽度 | 状态 | 问题 |")
        report_lines.append("|------|------|------|")
        
        # 测试每个断点
        for bp in BREAKPOINTS:
            width = bp["width"]
            label = bp["label"]
            print(f"\n测试 {label}...")
            
            # 调整视口大小
            await page.set_viewport_size({"width": width, "height": bp["height"]})
            await page.wait_for_timeout(500)  # 等待CSS重排
            
            # 截图
            screenshot_path = screenshot_dir / f"viewport_{width}px.png"
            await page.screenshot(path=str(screenshot_path), full_page=False)
            print(f"  截图已保存: {screenshot_path}")
            
            # 执行布局检查
            issues = await check_layout_issues(page, width)
            
            # 确定状态
            if any(i["severity"] in ["critical", "high"] for i in issues):
                status = "Fail"
            elif any(i["severity"] in ["medium", "low"] for i in issues):
                status = "Warn"
            else:
                status = "Pass"
            
            # 添加到总结
            issue_count = len(issues)
            if issue_count > 0:
                report_lines.append(f"| {width}px | {status} | {issue_count} 个问题 |")
                issues_summary.extend([{**issue, "width": width} for issue in issues])
            else:
                report_lines.append(f"| {width}px | {status} | — |")
        
        await browser.close()
    
    # 生成详细报告
    report_lines.append("\n## 关键和高优先级问题")
    
    critical_high_issues = [i for i in issues_summary if i["severity"] in ["critical", "high"]]
    if critical_high_issues:
        for issue in critical_high_issues:
            report_lines.append(f"\n### {issue['title']} — {issue['severity'].upper()}")
            report_lines.append(f"\n**宽度**: {issue['width']}px")
            report_lines.append(f"**检查项**: {issue['check']}")
            report_lines.append(f"\n{issue['description']}")
            if "fix" in issue:
                report_lines.append(f"\n**修复建议**: {issue['fix']}")
    else:
        report_lines.append("\n未发现关键或高优先级问题。")
    
    # 添加中等和低优先级问题
    medium_low_issues = [i for i in issues_summary if i["severity"] in ["medium", "low"]]
    if medium_low_issues:
        report_lines.append("\n## 其他问题")
        for issue in medium_low_issues:
            report_lines.append(f"\n### {issue['title']} — {issue['severity'].upper()}")
            report_lines.append(f"\n**宽度**: {issue['width']}px")
            report_lines.append(f"**检查项**: {issue['check']}")
            report_lines.append(f"\n{issue['description']}")
            if "fix" in issue:
                report_lines.append(f"\n**修复建议**: {issue['fix']}")
    
    # 添加断点转换分析
    report_lines.append("\n## 断点转换分析")
    report_lines.append("\n| 转换 | 观察点 | 清晰？ | 备注 |")
    report_lines.append("|------|--------|--------|------|")
    
    # 分析转换
    transitions = analyze_transitions(issues_summary)
    for trans in transitions:
        report_lines.append(f"| {trans['name']} | {trans['at']}px | {'是' if trans['clean'] else '否'} | {trans['notes']} |")
    
    if not transitions:
        report_lines.append("| — | — | — | 未检测到明显的布局转换 |")
    
    # 保存报告
    report_path = output_dir / f"responsiveness-report-{timestamp}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    
    print(f"\n报告已生成: {report_path}")
    print(f"截图目录: {screenshot_dir}")
    
    return report_path


async def check_layout_issues(page, width):
    """检查当前视口的布局问题"""
    issues = []
    
    # 1. 检查水平溢出
    has_horizontal_scroll = await page.evaluate("""
        () => {
            return document.documentElement.scrollWidth > document.documentElement.clientWidth;
        }
    """)
    
    if has_horizontal_scroll:
        scroll_width = await page.evaluate("() => document.documentElement.scrollWidth")
        client_width = await page.evaluate("() => document.documentElement.clientWidth")
        overflow = scroll_width - client_width
        
        severity = "critical" if overflow > 50 else "high" if overflow > 20 else "medium"
        issues.append({
            "title": "水平溢出",
            "check": "horizontal_overflow",
            "severity": severity,
            "description": f"页面宽度({scroll_width}px)超过视口宽度({client_width}px)，出现水平滚动条。溢出{overflow}px。",
            "fix": "检查是否有元素设置了固定宽度或最小宽度超过视口。添加 `overflow-x: hidden` 或使用 `max-width: 100%`。"
        })
    
    # 2. 检查文本溢出
    text_overflow_elements = await page.evaluate("""
        () => {
            const elements = document.querySelectorAll('h1, h2, h3, h4, h5, h6, p, span, a, button, label');
            const overflowed = [];
            
            elements.forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.right > window.innerWidth || rect.left < 0) {
                    overflowed.push({
                        tag: el.tagName,
                        text: el.textContent?.substring(0, 50),
                        left: rect.left,
                        right: rect.right
                    });
                }
            });
            
            return overflowed.slice(0, 5);  // 只返回前5个
        }
    """)
    
    if text_overflow_elements:
        issues.append({
            "title": "文本溢出",
            "check": "text_overflow",
            "severity": "high",
            "description": f"发现{len(text_overflow_elements)}个文本元素超出视口边界。",
            "fix": "为文本容器添加 `overflow: hidden; text-overflow: ellipsis; white-space: nowrap;` 或使用响应式字体大小。"
        })
    
    # 3. 检查触摸目标大小（移动端）
    if width < 768:
        small_targets = await page.evaluate("""
            () => {
                const interactive = document.querySelectorAll('button, a, input, select, textarea, [role="button"]');
                const small = [];
                
                interactive.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 44 || rect.height < 44) {
                        small.push({
                            tag: el.tagName,
                            text: el.textContent?.substring(0, 30) || el.placeholder || '',
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        });
                    }
                });
                
                return small.slice(0, 5);
            }
        """)
        
        if small_targets:
            issues.append({
                "title": "触摸目标过小",
                "check": "touch_targets",
                "severity": "medium",
                "description": f"在{width}px宽度下，发现{len(small_targets)}个交互元素小于44px×44px的最小触摸目标。",
                "fix": "增加按钮和链接的内边距，确保最小尺寸为44px×44px。"
            })
    
    # 4. 检查导航状态
    if width >= 768:
        nav_visible = await page.evaluate("""
            () => {
                const nav = document.querySelector('nav, [role="navigation"]');
                if (!nav) return null;
                
                const style = window.getComputedStyle(nav);
                return {
                    display: style.display,
                    visibility: style.visibility,
                    width: nav.getBoundingClientRect().width
                };
            }
        """)
        
        # 这里可以根据需要添加更多导航检查逻辑
    
    # 5. 检查内容堆叠
    grid_columns = await page.evaluate("""
        () => {
            const grids = document.querySelectorAll('[class*="grid"], [class*="Grid"]');
            const columns = [];
            
            grids.forEach(grid => {
                const style = window.getComputedStyle(grid);
                const template = style.gridTemplateColumns;
                if (template && template !== 'none') {
                    const colCount = template.split(' ').length;
                    columns.push({
                        element: grid.className?.substring(0, 50),
                        columns: colCount
                    });
                }
            });
            
            return columns;
        }
    """)
    
    # 根据宽度检查网格列数是否合理
    for grid in grid_columns:
        if width < 640 and grid["columns"] > 2:
            issues.append({
                "title": "网格列数过多",
                "check": "content_stacking",
                "severity": "medium",
                "description": f"在{width}px宽度下，网格仍有{grid['columns']}列，可能导致内容过窄。",
                "fix": "在小屏幕上使用 `grid-cols-1` 或 `grid-cols-2`。"
            })
    
    return issues


def analyze_transitions(issues):
    """分析布局转换点"""
    transitions = []
    
    # 按宽度分组问题
    width_issues = {}
    for issue in issues:
        width = issue["width"]
        if width not in width_issues:
            width_issues[width] = []
        width_issues[width].append(issue)
    
    # 检测明显的转换点
    widths = sorted(width_issues.keys())
    
    for i in range(len(widths) - 1):
        w1 = widths[i]
        w2 = widths[i + 1]
        
        issues1 = set(i["check"] for i in width_issues.get(w1, []))
        issues2 = set(i["check"] for i in width_issues.get(w2, []))
        
        # 如果问题类型发生变化，可能是布局转换
        if issues1 != issues2:
            new_issues = issues2 - issues1
            resolved_issues = issues1 - issues2
            
            notes = []
            if new_issues:
                notes.append(f"新增: {', '.join(new_issues)}")
            if resolved_issues:
                notes.append(f"解决: {', '.join(resolved_issues)}")
            
            transitions.append({
                "name": f"{w1}px → {w2}px",
                "at": w2,
                "clean": len(new_issues) == 0,
                "notes": "; ".join(notes) if notes else "布局变化"
            })
    
    return transitions


if __name__ == "__main__":
    asyncio.run(check_responsiveness())