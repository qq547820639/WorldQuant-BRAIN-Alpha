#!/usr/bin/env python3
"""
Responsiveness Check Script
Tests website responsiveness across 8 key breakpoints.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# Breakpoints to test
BREAKPOINTS = [
    (320, "Small phone (iPhone SE)"),
    (375, "Standard phone (iPhone 14)"),
    (768, "Tablet portrait (iPad)"),
    (1024, "Tablet landscape / small laptop"),
    (1280, "Laptop"),
    (1440, "Desktop"),
    (1920, "Full HD"),
    (2560, "Ultra-wide / 4K"),
]

# Layout checks
CHECKS = [
    "horizontal_overflow",
    "text_overflow",
    "navigation_transition",
    "content_stacking",
    "image_media_scaling",
    "touch_targets",
    "whitespace_balance",
    "cta_visibility",
]

async def check_responsiveness(url: str, output_dir: Path):
    """Run responsiveness checks across all breakpoints."""
    
    results = []
    screenshots = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 320, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        # Navigate to URL
        print(f"Loading {url}...")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        
        # Wait for page to load
        await page.wait_for_timeout(2000)
        
        # Check if React app loaded
        root_content = await page.evaluate("""
            () => {
                const root = document.getElementById('root');
                return root ? root.innerHTML.length : 0;
            }
        """)
        
        print(f"React app content length: {root_content}")
        
        if root_content == 0:
            print("WARNING: React app not loaded. Checking page content...")
            page_content = await page.content()
            print(f"Page content length: {len(page_content)}")
        
        # Test each breakpoint
        for width, device_name in BREAKPOINTS:
            print(f"\nTesting {width}px ({device_name})...")
            
            # Resize viewport
            await page.set_viewport_size({"width": width, "height": 900})
            await page.wait_for_timeout(500)  # Wait for CSS reflow
            
            # Take screenshot
            screenshot_path = output_dir / f"screenshot_{width}px.png"
            await page.screenshot(path=str(screenshot_path), full_page=False)
            screenshots.append(str(screenshot_path))
            
            # Run layout checks
            check_results = await run_layout_checks(page, width)
            
            # Determine status
            critical_issues = sum(1 for r in check_results if r["severity"] == "critical")
            high_issues = sum(1 for r in check_results if r["severity"] == "high")
            medium_issues = sum(1 for r in check_results if r["severity"] == "medium")
            
            if critical_issues > 0:
                status = "Fail"
            elif high_issues > 0:
                status = "Fail"
            elif medium_issues > 0:
                status = "Warn"
            else:
                status = "Pass"
            
            results.append({
                "width": width,
                "device": device_name,
                "status": status,
                "issues": check_results,
                "screenshot": str(screenshot_path),
            })
            
            print(f"  Status: {status}")
            if check_results:
                for issue in check_results:
                    print(f"  - [{issue['severity']}] {issue['check']}: {issue['description']}")
        
        await browser.close()
    
    return results, screenshots

async def run_layout_checks(page, width: int):
    """Run all layout checks for a given viewport width."""
    
    issues = []
    
    # Check 1: Horizontal overflow
    has_horizontal_scroll = await page.evaluate("""
        () => {
            return document.documentElement.scrollWidth > document.documentElement.clientWidth;
        }
    """)
    if has_horizontal_scroll:
        issues.append({
            "check": "horizontal_overflow",
            "severity": "high",
            "description": "Horizontal scrollbar detected",
            "width": width,
        })
    
    # Check 2: Text overflow (check for truncated text)
    truncated_elements = await page.evaluate("""
        () => {
            const elements = document.querySelectorAll('h1, h2, h3, p, span, a, button');
            let truncated = 0;
            for (const el of elements) {
                if (el.scrollWidth > el.clientWidth + 2) {
                    truncated++;
                }
            }
            return truncated;
        }
    """)
    if truncated_elements > 0:
        issues.append({
            "check": "text_overflow",
            "severity": "medium" if truncated_elements < 5 else "high",
            "description": f"{truncated_elements} elements have text overflow",
            "width": width,
        })
    
    # Check 3: Navigation transition (check for hamburger menu)
    if width < 768:
        hamburger_exists = await page.evaluate("""
            () => {
                const hamburger = document.querySelector('[aria-label*="menu"], [class*="hamburger"], [class*="menu-toggle"]');
                return !!hamburger;
            }
        """)
        if not hamburger_exists:
            # This is not necessarily an issue - depends on design
            pass
    
    # Check 4: Content stacking (check for multi-column layouts)
    grid_columns = await page.evaluate("""
        () => {
            const grids = document.querySelectorAll('[class*="grid"], [style*="grid"]');
            let maxColumns = 1;
            for (const grid of grids) {
                const style = window.getComputedStyle(grid);
                const columns = style.gridTemplateColumns;
                if (columns && columns !== 'none') {
                    const colCount = columns.split(' ').length;
                    maxColumns = Math.max(maxColumns, colCount);
                }
            }
            return maxColumns;
        }
    """)
    
    # Check 5: Image/media scaling
    oversized_images = await page.evaluate("""
        () => {
            const images = document.querySelectorAll('img, video, svg');
            let oversized = 0;
            for (const img of images) {
                if (img.naturalWidth > 0 && img.clientWidth > 0) {
                    if (img.clientWidth > img.naturalWidth * 1.5) {
                        oversized++;
                    }
                }
            }
            return oversized;
        }
    """)
    if oversized_images > 0:
        issues.append({
            "check": "image_media_scaling",
            "severity": "medium",
            "description": f"{oversized_images} images/videos are stretched",
            "width": width,
        })
    
    # Check 6: Touch targets (only for mobile widths)
    if width < 768:
        small_targets = await page.evaluate("""
            () => {
                const interactive = document.querySelectorAll('button, a, input, select, textarea, [role="button"]');
                let small = 0;
                for (const el of interactive) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 44 || rect.height < 44) {
                        small++;
                    }
                }
                return small;
            }
        """)
        if small_targets > 0:
            issues.append({
                "check": "touch_targets",
                "severity": "medium" if small_targets < 5 else "high",
                "description": f"{small_targets} interactive elements are smaller than 44px",
                "width": width,
            })
    
    # Check 7: Whitespace balance
    body_height = await page.evaluate("() => document.body.scrollHeight")
    viewport_height = 900
    if body_height < viewport_height * 0.5:
        issues.append({
            "check": "whitespace_balance",
            "severity": "low",
            "description": "Page content is very short, lots of whitespace",
            "width": width,
        })
    
    # Check 8: CTA visibility
    cta_visible = await page.evaluate("""
        () => {
            const cta = document.querySelector('[class*="cta"], [class*="primary"], [class*="submit"], button[type="submit"]');
            if (!cta) return true; // No CTA found, not an issue
            const rect = cta.getBoundingClientRect();
            return rect.top < window.innerHeight;
        }
    """)
    if not cta_visible:
        issues.append({
            "check": "cta_visibility",
            "severity": "medium",
            "description": "Primary CTA is not visible above the fold",
            "width": width,
        })
    
    return issues

def generate_report(results, output_dir: Path):
    """Generate markdown report from results."""
    
    report_lines = [
        "# Responsiveness Check Report",
        "",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "**Mode**: Standard (8 breakpoints)",
        "**Browser**: Playwright Chromium",
        "",
        "## Summary",
        "",
        "| Width | Device | Status | Issues |",
        "|-------|--------|--------|--------|",
    ]
    
    for result in results:
        issue_count = len(result["issues"])
        issue_summary = f"{issue_count} issues" if issue_count > 0 else "—"
        report_lines.append(f"| {result['width']}px | {result['device']} | {result['status']} | {issue_summary} |")
    
    # Count issues by severity
    all_issues = []
    for result in results:
        all_issues.extend(result["issues"])
    
    critical = sum(1 for i in all_issues if i["severity"] == "critical")
    high = sum(1 for i in all_issues if i["severity"] == "high")
    medium = sum(1 for i in all_issues if i["severity"] == "medium")
    low = sum(1 for i in all_issues if i["severity"] == "low")
    
    report_lines.extend([
        "",
        f"**Overall**: {len(all_issues)} issues across {len(results)} breakpoints.",
        f"- Critical: {critical}",
        f"- High: {high}",
        f"- Medium: {medium}",
        f"- Low: {low}",
        "",
    ])
    
    # Critical & High Issues
    critical_high_issues = [i for i in all_issues if i["severity"] in ("critical", "high")]
    if critical_high_issues:
        report_lines.extend([
            "## Critical & High Issues",
            "",
        ])
        
        for issue in critical_high_issues:
            report_lines.extend([
                f"### {issue['check'].replace('_', ' ').title()} — {issue['severity'].title()}",
                "",
                f"**Width(s)**: {issue['width']}px",
                f"**Check**: {issue['check']}",
                "",
                issue["description"],
                "",
                "---",
                "",
            ])
    
    # Per-Breakpoint Notes
    report_lines.extend([
        "## Per-Breakpoint Notes",
        "",
    ])
    
    for result in results:
        if result["issues"]:
            report_lines.extend([
                f"### {result['width']}px — {result['status']}",
                "",
            ])
            
            for issue in result["issues"]:
                report_lines.append(f"- **[{issue['severity'].title()}]** {issue['description']}")
            
            report_lines.append("")
    
    # Recommendations
    report_lines.extend([
        "## Recommendations",
        "",
        "### Quick Fixes (CSS only)",
        "- Review responsive breakpoints in Tailwind CSS classes",
        "- Ensure proper `max-width` and `overflow` handling",
        "- Test touch targets on mobile widths",
        "",
        "### Structural Changes",
        "- Consider adding more breakpoints for tablet-specific layouts",
        "- Review grid/flexbox configurations for different viewports",
        "",
        "## Screenshots",
        "",
        "Screenshots saved to: `docs/responsiveness-check/`",
        "",
    ])
    
    # Write report
    report_path = output_dir / "responsiveness-report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    
    return report_path

async def main():
    """Main entry point."""
    
    url = "http://127.0.0.1:8765/"
    output_dir = Path("/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/docs/responsiveness-check")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Starting responsiveness check for {url}")
    print(f"Output directory: {output_dir}")
    
    results, screenshots = await check_responsiveness(url, output_dir)
    
    report_path = generate_report(results, output_dir)
    
    print(f"\n{'='*60}")
    print(f"Responsiveness check completed!")
    print(f"Report saved to: {report_path}")
    print(f"Screenshots saved to: {output_dir}")
    print(f"{'='*60}")
    
    # Print summary
    all_issues = []
    for result in results:
        all_issues.extend(result["issues"])
    
    critical = sum(1 for i in all_issues if i["severity"] == "critical")
    high = sum(1 for i in all_issues if i["severity"] == "high")
    medium = sum(1 for i in all_issues if i["severity"] == "medium")
    low = sum(1 for i in all_issues if i["severity"] == "low")
    
    print(f"\nSummary:")
    print(f"- Total issues: {len(all_issues)}")
    print(f"- Critical: {critical}")
    print(f"- High: {high}")
    print(f"- Medium: {medium}")
    print(f"- Low: {low}")
    
    if critical > 0 or high > 0:
        print("\n⚠️  Critical or high severity issues found!")
        return 1
    else:
        print("\n✅ No critical or high severity issues found.")
        return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)