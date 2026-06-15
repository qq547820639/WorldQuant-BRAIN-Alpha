import os
"""
BRAIN Alpha Ops - 完整Alpha提交测试（最终生产版）

流程:
1. 访问 → 系统配置 → 填写凭据 → 测试连接
2. 返回Dashboard → 开始首次同步（拉取云端数据）
3. 等待同步+生产完成（可能需要几分钟）
4. 展开阶段组 → 查看候选 → 查看提交就绪
"""

from playwright.sync_api import sync_playwright
import time, os

EMAIL = os.environ.get("BRAIN_USERNAME", "")
PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
URL = "http://127.0.0.1:8765"
OUT = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/production_test"

def ss(page, name):
    os.makedirs(OUT, exist_ok=True)
    page.screenshot(path=f"{OUT}/{name}.png", full_page=True)

def log(msg):
    print(f"\n[{time.strftime('%H:%M:%S')}] {msg}")

def expand_phase_group(page, phase_name):
    """展开侧边栏的阶段组"""
    try:
        header = page.locator(f"button[aria-expanded='false']:has-text('{phase_name}')").first
        if header.count() > 0:
            header.click()
            time.sleep(1)
            return True
    except:
        pass
    return False

def main():
    print("="*70)
    print("   BRAIN Alpha Ops - 生产测试")
    print("="*70)
    print(f"开始: {time.strftime('%H:%M:%S')}  |  账户: {EMAIL}")
    print("="*70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=['--window-size=1600,900'])
        page = browser.new_page(viewport={'width': 1600, 'height': 900})

        #---------------------------------------------------------------------
        # 登录
        #---------------------------------------------------------------------
        log("1/7 访问页面")
        page.goto(URL)
        time.sleep(8)
        ss(page, "01_pageload")

        log("2/7 导航到系统配置 & 填写凭据")
        page.locator("button:has-text('系统配置')").first.click()
        time.sleep(5)

        page.locator("input[type='text']").first.fill(EMAIL)
        time.sleep(0.5)
        page.locator("input[type='password']").first.fill(PASSWORD)
        time.sleep(0.5)
        page.locator("button:has-text('测试 BRAIN 连接')").first.click()

        log("   等待认证（15秒）...")
        time.sleep(15)
        ss(page, "02_connected")

        #---------------------------------------------------------------------
        # 返回Dashboard & 开始首次同步
        #---------------------------------------------------------------------
        log("3/7 返回Dashboard | 开始首次同步")
        page.locator("button:has-text('运行总览')").first.click()
        time.sleep(5)

        # 查找并点击 "开始首次同步"
        sync_btn = page.locator("button:has-text('开始首次同步')").first
        if sync_btn.count() > 0:
            sync_btn.click()
            log("   已开始首次同步")
        else:
            # 备选：直接点击 "运行非提交验证"
            run_btn = page.locator("button:has-text('运行非提交验证')").first
            if run_btn.count() > 0:
                run_btn.click()
                log("   已点击运行非提交验证")

        #---------------------------------------------------------------------
        # 等待同步+生产完成（最多5分钟）
        #---------------------------------------------------------------------
        log("4/7 等待同步+生产完成（最多5分钟）...")
        max_wait = 300
        start = time.time()
        completed = False

        while time.time() - start < max_wait:
            time.sleep(15)
            elapsed = int(time.time() - start)
            try:
                text = page.inner_text("body")
                # 检查是否有完成提示
                if any(kw in text for kw in ["已完成", "completed", "生产完成", "停止"]):
                    log(f"   ✅ 同步/生产完成！耗时 {elapsed}s")
                    completed = True
                    break
                # 检查是否有错误
                if "失败" in text:
                    log(f"   ⚠️ 可能失败（耗时 {elapsed}s）")
                log(f"   ⏳ 等待中... {elapsed}s")
            except:
                pass

        if not completed:
            log("   ⚠️ 超时，继续后续步骤...")
        ss(page, "03_sync_done")

        #---------------------------------------------------------------------
        # 展开阶段组 & 导航
        #---------------------------------------------------------------------
        log("5/7 展开 '候选发现' 阶段组")
        expand_phase_group(page, "候选发现")
        time.sleep(3)

        # 查找并点击 "候选管理"
        manage_btn = page.locator("button:has-text('候选管理')").first
        if manage_btn.count() > 0 and manage_btn.is_visible():
            manage_btn.click()
            time.sleep(5)
            ss(page, "04_candidates")
            log("   ✅ 已进入候选管理")
        else:
            log("   ⚠️ 候选管理不可访问（可能需要先完成生产）")

        log("6/7 展开 '提交就绪' 阶段组")
        expand_phase_group(page, "提交就绪")
        time.sleep(3)

        ready_btn = page.locator("button:has-text('阻断复核')").first
        if ready_btn.count() > 0 and ready_btn.is_visible():
            ready_btn.click()
            time.sleep(5)
            ss(page, "05_submission")
            log("   ✅ 已进入阻断复核")
        else:
            log("   ⚠️ 阻断复核不可访问")

        #---------------------------------------------------------------------
        # 完成
        #---------------------------------------------------------------------
        log("7/7 测试完成")
        ss(page, "06_final")

        print("\n" + "="*70)
        print(f"   完成时间: {time.strftime('%H:%M:%S')}")
        print(f"   截图: {OUT}/")
        print("   ⏸️ 浏览器保持60秒...")
        print("="*70)
        time.sleep(60)
        browser.close()
        print("   ✅ 测试完成！")

if __name__ == "__main__":
    main()
