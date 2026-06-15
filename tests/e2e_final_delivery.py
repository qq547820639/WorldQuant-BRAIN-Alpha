import os
"""
BRAIN Alpha Ops - 最终完整验收测试

sync已完成 -> 直接运行非提交验证生产Alpha
"""
from playwright.sync_api import sync_playwright
import time, os, json

EMAIL = "547820639@qq.com"
PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
URL = "http://127.0.0.1:8765"
OUT = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/final_delivery"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def ss(page, name):
    os.makedirs(OUT, exist_ok=True)
    page.screenshot(path=f"{OUT}/{name}.png", full_page=True)

def main():
    print("="*70, flush=True)
    log("🧪 最终验收：Alpha生产+提交")
    print("="*70, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=['--window-size=1600,900'])
        page = browser.new_page(viewport={'width': 1600, 'height': 900})

        # 1. 登录
        log("1. 登录")
        page.goto(URL); time.sleep(8)
        page.locator("button:has-text('系统配置')").first.click(); time.sleep(5)
        page.locator("input[type='text']").first.fill(EMAIL)
        page.locator("input[type='password']").first.fill(PASSWORD)
        page.locator("button:has-text('测试 BRAIN 连接')").first.click()
        time.sleep(15)
        log("   ✅ 认证成功")
        ss(page, "01_auth")

        # 2. 返回Dashboard - 等待生产按钮出现
        log("2. 等待生产界面")
        page.locator("button:has-text('运行总览')").first.click()
        time.sleep(10)  # 给页面足够时间刷新
        
        # 检查页面状态
        text = page.inner_text("body")
        ss(page, "02_dashboard")
        
        # 如果还在同步中，等待
        if "同步中" in text or "运行中" in text:
            log("   检测到同步进行中，等待完成...")
            for i in range(30):
                time.sleep(20)
                text = page.inner_text("body")
                if "同步中" not in text and "运行中" not in text:
                    log(f"   ✅ 同步完成")
                    break
                log(f"   ⏳ 等待... {(i+1)*20}s")
            page.reload()
            time.sleep(5)

        # 3. 查找生产按钮
        log("3. 启动生产")
        ss(page, "03_pre_run")
        
        # 尝试多种按钮
        run_clicked = False
        for btn_text in ["运行非提交验证", "开始验证", "开始生产", "继续上次验证"]:
            btn = page.locator(f"button:has-text('{btn_text}')").first
            if btn.count() > 0:
                try:
                    btn.click()
                    run_clicked = True
                    log(f"   ✅ 点击: {btn_text}")
                    break
                except: pass
        
        if not run_clicked:
            # 看看dashboard上有哪些按钮
            buttons = page.locator("button").all()
            visible_btns = []
            for btn in buttons:
                try:
                    if btn.is_visible():
                        t = btn.text_content().strip()
                        if t: visible_btns.append(t)
                except: pass
            log(f"   可见按钮: {visible_btns[:15]}")
            
            # 尝试点击看起来像启动的按钮
            for btn in buttons:
                try:
                    t = btn.text_content().strip()
                    if any(kw in t for kw in ["开始", "运行", "验证", "生产", "start", "run"]):
                        if btn.is_visible():
                            btn.click()
                            run_clicked = True
                            log(f"   ✅ 点击: {t[:60]}")
                            break
                except: pass
        
        if not run_clicked:
            log("   ❌ 无法启动生产！可能需要手动操作")
            browser.close()
            return

        # 4. 等待生产完成
        log("4. 等待生产完成（最多300秒）")
        start = time.time()
        while time.time() - start < 300:
            time.sleep(15)
            elapsed = int(time.time() - start)
            try:
                t = page.inner_text("body")
                if any(kw in t for kw in ["已完成", "completed", "生产完成", "completed_with_warnings", "停止"]):
                    log(f"   ✅ 生产完成！{elapsed}s")
                    break
                log(f"   ⏳ {elapsed}s")
            except: pass
        ss(page, "04_production_done")

        # 5. 候选发现
        log("5. 候选发现")
        try:
            # 展开阶段组
            btn = page.locator("button[aria-expanded='false']:has-text('候选发现')").first
            if btn.count() > 0: btn.click(); time.sleep(1)
            page.locator("button:has-text('候选管理')").first.click()
            time.sleep(5)
            ss(page, "05_candidates")
            
            text = page.inner_text("body")
            log(f"   候选页面文本(前500): {text[:500]}")
        except Exception as e:
            log(f"   ⚠️ {e}")

        # 6. 提交就绪
        log("6. 提交就绪")
        try:
            btn = page.locator("button[aria-expanded='false']:has-text('提交就绪')").first
            if btn.count() > 0: btn.click(); time.sleep(1)
            page.locator("button:has-text('阻断复核')").first.click()
            time.sleep(5)
            ss(page, "06_readiness")
            
            text = page.inner_text("body")
            log(f"   提交就绪文本(前500): {text[:500]}")
        except Exception as e:
            log(f"   ⚠️ {e}")

        # 7. 最终Dashboard
        log("7. 最终Dashboard")
        page.locator("button:has-text('运行总览')").first.click()
        time.sleep(3)
        ss(page, "07_final")

        browser.close()
        log("✅ 验收测试完成！")

if __name__ == "__main__":
    main()
