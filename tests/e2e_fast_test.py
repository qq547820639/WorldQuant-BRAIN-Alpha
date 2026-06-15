import os
"""
BRAIN Alpha Ops - 完整Alpha提交流程验收测试（无截图版）

为生产环境优化：无截图，快速输出
"""

from playwright.sync_api import sync_playwright
import time

EMAIL = os.environ.get("BRAIN_USERNAME", "")
PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
URL = "http://127.0.0.1:8765"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def main():
    print("="*70, flush=True)
    log("BRAIN Alpha Ops - Alpha提交流程验收测试")
    log(f"账户: {EMAIL}")
    print("="*70, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=['--window-size=1600,900'])
        page = browser.new_page(viewport={'width': 1600, 'height': 900})

        # --- 1. 访问 ---
        log("1. 访问页面...")
        page.goto(URL)
        time.sleep(8)
        log(f"   标题: {page.title()}")

        # --- 2. 系统配置 ---
        log("2. 导航到系统配置...")
        page.locator("button:has-text('系统配置')").first.click()
        time.sleep(5)
        log("   ✅ 已进入配置页面")

        # --- 3. 填写凭据 ---
        log("3. 填写凭据...")
        page.locator("input[type='text']").first.fill(EMAIL)
        page.locator("input[type='password']").first.fill(PASSWORD)
        log(f"   ✅ 邮箱: {EMAIL}  密码: ●●●●●●●●")

        # --- 4. 测试连接 ---
        log("4. 测试 BRAIN 连接...")
        page.locator("button:has-text('测试 BRAIN 连接')").first.click()
        time.sleep(15)
        
        text = page.inner_text("body")
        if "连接正常" in text:
            log("   ✅ 认证成功！")
        else:
            log(f"   ⚠️ 状态: {text[:200]}")

        # --- 5. 返回Dashboard ---
        log("5. 返回运行总览...")
        page.locator("button:has-text('运行总览')").first.click()
        time.sleep(5)
        log("   ✅ 已返回Dashboard")

        # --- 6. 开始首次同步 ---
        log("6. 开始首次同步...")
        sync_btn = page.locator("button:has-text('开始首次同步')").first
        if sync_btn.count() > 0:
            sync_btn.click()
            log("   ✅ 已点击开始首次同步")
        else:
            log("   ⚠️ 未找到同步按钮")

        # --- 7. 等待完成（最多5分钟）---
        log("7. 等待同步+生产（最多300秒）...")
        start = time.time()
        while time.time() - start < 300:
            time.sleep(20)
            elapsed = int(time.time() - start)
            try:
                t = page.inner_text("body")
                if any(kw in t for kw in ["已完成", "completed", "停止"]):
                    log(f"   ✅ 完成！耗时 {elapsed}s")
                    break
                log(f"   ⏳ 等待中... {elapsed}s / 300s")
            except:
                pass

        # --- 8. 尝试查看候选 ---
        log("8. 查看候选发现...")
        try:
            # 先展开阶段组
            phase_btn = page.locator("button[aria-expanded='false']:has-text('候选发现')").first
            if phase_btn.count() > 0:
                phase_btn.click()
                time.sleep(2)
            
            page.locator("button:has-text('候选管理')").first.click()
            time.sleep(5)
            log("   ✅ 已进入候选管理")
        except Exception as e:
            log(f"   ⚠️ {e}")

        # --- 9. 提交就绪 ---
        log("9. 查看提交就绪...")
        try:
            phase_btn = page.locator("button[aria-expanded='false']:has-text('提交就绪')").first
            if phase_btn.count() > 0:
                phase_btn.click()
                time.sleep(2)
            
            page.locator("button:has-text('阻断复核')").first.click()
            time.sleep(5)
            log("   ✅ 已进入阻断复核")
        except Exception as e:
            log(f"   ⚠️ {e}")

        # --- 完成 ---
        log("✅ 验收测试完成！")
        log(f"   最终URL: {page.url}")
        time.sleep(30)
        browser.close()

if __name__ == "__main__":
    main()
