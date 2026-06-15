import os
"""
BRAIN Alpha Ops - 完整验收测试（扩展版）

覆盖路径：
1. 正常登录+生产流程
2. 错误凭证场景
3. 候选数据验证
4. 提交就绪面板内容验证
5. 各阶段页面可访问性
"""

from playwright.sync_api import sync_playwright
import time, json, os

EMAIL = os.environ.get("BRAIN_USERNAME", "")
PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
URL = "http://127.0.0.1:8765"
OUT = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/acceptance"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def ss(page, name):
    os.makedirs(OUT, exist_ok=True)
    page.screenshot(path=f"{OUT}/{name}.png", full_page=True)

def check_a11y(page):
    """快速可访问性检查"""
    issues = []
    # 检查图片alt属性
    imgs = page.locator("img:not([alt])").all()
    if len(imgs) > 0:
        issues.append(f"{len(imgs)} images missing alt text")
    # 检查按钮是否有文本
    buttons = page.locator("button").all()
    for btn in buttons:
        try:
            if btn.is_visible() and not btn.text_content().strip():
                issues.append(f"Empty button found")
                break
        except: pass
    # 检查role=alert是否用于错误消息
    return issues

def check_performance(page):
    """基本性能检查"""
    metrics = page.evaluate("""() => {
        const perf = performance.getEntriesByType('navigation')[0];
        return perf ? {
            domContentLoaded: perf.domContentLoadedEventEnd - perf.startTime,
            loadComplete: perf.loadEventEnd - perf.startTime,
            firstPaint: performance.getEntriesByType('paint').find(e => e.name === 'first-contentful-paint')?.startTime || 0
        } : {};
    }""")
    return metrics

def main():
    results = {"passed": [], "failed": [], "warnings": [], "issues": []}
    
    print("="*70, flush=True)
    log("🧪 BRAIN Alpha Ops — 完整验收测试")
    print("="*70, flush=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=['--window-size=1600,900'])
        page = browser.new_page(viewport={'width': 1600, 'height': 900})

        # ============================================================
        # 测试1: 页面加载性能
        # ============================================================
        log("1. 页面加载性能测试")
        page.goto(URL)
        time.sleep(5)
        perf = check_performance(page)
        log(f"   DOMContentLoaded: {perf.get('domContentLoaded', 'N/A'):.0f}ms")
        log(f"   FirstPain: {perf.get('firstPaint', 'N/A'):.0f}ms")
        ss(page, "01_load")
        
        a11y_issues = check_a11y(page)
        if a11y_issues:
            for i in a11y_issues:
                results["warnings"].append(f"A11y: {i}")
        results["passed"].append("页面加载")

        # ============================================================
        # 测试2: 错误密码场景
        # ============================================================
        log("2. 错误密码场景测试")
        page.locator("button:has-text('系统配置')").first.click()
        time.sleep(3)
        
        # 填写错误密码
        page.locator("input[type='text']").first.fill(EMAIL)
        page.locator("input[type='password']").first.fill("WrongPassword123")
        page.locator("button:has-text('测试 BRAIN 连接')").first.click()
        time.sleep(10)
        
        text = page.inner_text("body")
        if "失败" in text or "错误" in text or "error" in text.lower():
            results["passed"].append("错误密码被正确拒绝")
            log("   ✅ 错误密码被正确拒绝")
        else:
            results["failed"].append("错误密码未被拒绝")
            log("   ❌ 错误密码未被拒绝！")
        ss(page, "02_wrong_pwd")

        # ============================================================
        # 测试3: 正确密码连接
        # ============================================================
        log("3. 正确密码连接")
        page.locator("input[type='password']").first.clear()
        page.locator("input[type='password']").first.fill(PASSWORD)
        page.locator("button:has-text('测试 BRAIN 连接')").first.click()
        time.sleep(15)
        
        text = page.inner_text("body")
        if "连接正常" in text or "成功" in text:
            results["passed"].append("正确密码认证成功")
            log("   ✅ 认证成功")
        else:
            results["failed"].append("正确密码认证失败")
            log("   ❌ 认证失败！")
        ss(page, "03_correct_pwd")

        # ============================================================
        # 测试4: 返回Dashboard并检查状态
        # ============================================================
        log("4. Dashboard状态检查")
        page.locator("button:has-text('运行总览')").first.click()
        time.sleep(5)
        text = page.inner_text("body")
        
        if "连接成功" in text or "BRAIN 连接正常" in text:
            results["passed"].append("Dashboard显示连接状态")
        ss(page, "04_dashboard")

        # ============================================================
        # 测试5: 首次同步
        # ============================================================
        log("5. 首次同步测试")
        sync_btn = page.locator("button:has-text('开始首次同步')").first
        if sync_btn.count() > 0:
            sync_btn.click()
            log("   ✅ 已开始首次同步")
            
            # 等待同步完成
            start = time.time()
            while time.time() - start < 120:
                time.sleep(15)
                elapsed = int(time.time() - start)
                t = page.inner_text("body")
                if any(kw in t for kw in ["已完成", "completed", "停止", "candidates_count"]):
                    log(f"   ✅ 同步/生产完成！耗时 {elapsed}s")
                    results["passed"].append("首次同步完成")
                    break
                log(f"   ⏳ 等待同步... {elapsed}s")
        ss(page, "05_synced")

        # ============================================================
        # 测试6: 展开候选发现 & 验证候选数据
        # ============================================================
        log("6. 候选发现数据验证")
        try:
            # 展开阶段组
            phase_btn = page.locator("button[aria-expanded='false']:has-text('候选发现')").first
            if phase_btn.count() > 0:
                phase_btn.click()
                time.sleep(2)
            
            page.locator("button:has-text('候选管理')").first.click()
            time.sleep(5)
            
            text = page.inner_text("body")
            # 检查是否有候选表格或空状态
            if "候选" in text or "Alpha" in text or "表达式" in text:
                results["passed"].append("候选发现页面可访问")
                log("   ✅ 候选发现页面有内容")
            else:
                results["warnings"].append("候选发现页面内容为空")
                log("   ⚠️ 候选发现页面可能为空")
            ss(page, "06_candidates")
        except Exception as e:
            results["warnings"].append(f"候选发现访问失败: {e}")
            log(f"   ⚠️ {e}")

        # ============================================================
        # 测试7: 提交就绪检查
        # ============================================================
        log("7. 提交就绪面板验证")
        try:
            phase_btn = page.locator("button[aria-expanded='false']:has-text('提交就绪')").first
            if phase_btn.count() > 0:
                phase_btn.click()
                time.sleep(2)
            
            page.locator("button:has-text('阻断复核')").first.click()
            time.sleep(5)
            
            text = page.inner_text("body")
            if any(kw in text for kw in ["阻断", "ready", "提交", "就绪", "submit", "review"]):
                results["passed"].append("提交就绪面板可访问")
                log("   ✅ 提交就绪面板有内容")
            ss(page, "07_readiness")
        except Exception as e:
            results["warnings"].append(f"提交就绪访问失败: {e}")
            log(f"   ⚠️ {e}")

        # ============================================================
        # 测试8: 系统配置参数回读
        # ============================================================
        log("8. 配置参数回读验证")
        page.locator("button:has-text('系统配置')").first.click()
        time.sleep(3)
        text = page.inner_text("body")
        
        config_checks = ["EQUITY", "USA", "TOP3000", "资产类型", "股票池"]
        for check in config_checks:
            if check in text:
                results["passed"].append(f"配置项 '{check}' 存在")
            else:
                results["warnings"].append(f"配置项 '{check}' 缺失")
        ss(page, "08_config")

        # ============================================================
        # 测试9: 导出功能（不实际导出，只检查按钮）
        # ============================================================
        log("9. 导出/导入按钮检查")
        export_btn = page.locator("button:has-text('导出')").first
        import_btn = page.locator("button:has-text('导入')").first
        save_btn = page.locator("button:has-text('保存')").first
        
        if export_btn.count() > 0:
            results["passed"].append("导出按钮存在")
        if import_btn.count() > 0:
            results["passed"].append("导入按钮存在")
        if save_btn.count() > 0:
            results["passed"].append("保存按钮存在")
        log(f"   导出: {export_btn.count()>0} | 导入: {import_btn.count()>0} | 保存: {save_btn.count()>0}")

        # ============================================================
        # 测试10: 返回Dashboard & 检查生产状态
        # ============================================================
        log("10. 返回Dashboard检查生产状态")
        page.locator("button:has-text('运行总览')").first.click()
        time.sleep(3)
        text = page.inner_text("body")
        
        # 检查KPI卡片
        if "转换量" in text or "已通过" in text or "提交数" in text:
            results["passed"].append("Dashboard KPI卡片显示正常")
            log("   ✅ KPI卡片存在")
        ss(page, "09_dashboard_final")

        # ============================================================
        # 汇总
        # ============================================================
        browser.close()

    print("\n" + "="*70)
    print("   📊 验收测试汇总")
    print("="*70)
    print(f"\n   ✅ 通过: {len(results['passed'])}")
    for p in results['passed']:
        print(f"      ✅ {p}")
    
    print(f"\n   ⚠️ 警告: {len(results['warnings'])}")
    for w in results['warnings']:
        print(f"      ⚠️ {w}")
    
    print(f"\n   ❌ 失败: {len(results['failed'])}")
    for f in results['failed']:
        print(f"      ❌ {f}")
    
    print(f"\n   📸 截图保存至: {OUT}/")
    
    # 判定
    if len(results['failed']) == 0:
        print("\n   🎉 验收结论: 通过！项目核心流程可正常运作。")
    else:
        print(f"\n   🚨 验收结论: 不通过！有 {len(results['failed'])} 项失败需修复。")
    
    print("\n" + "="*70)
    
    # 保存结果JSON
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
