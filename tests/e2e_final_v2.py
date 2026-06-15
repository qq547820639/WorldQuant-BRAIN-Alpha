import os
"""
BRAIN Alpha Ops - 完整Alpha提交流程UI测试（最终正确版）

基于完整代码分析的正确流程：
1. 页面加载 → 侧边栏 "10 系统配置" → ConfigPanel
2. ConfigPanel凭证表单直接可见（inputs[1]=email, inputs[2]=password）
3. 填写 → 点击"测试 BRAIN 连接" (button[16])
4. 返回Dashboard → 运行非提交验证 → 候选发现 → 提交就绪
"""

from playwright.sync_api import sync_playwright
import time, os

EMAIL = os.environ.get("BRAIN_USERNAME", "")
PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
URL = "http://127.0.0.1:8765"
OUT = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/final_correct"

def ss(page, name):
    os.makedirs(OUT, exist_ok=True)
    page.screenshot(path=f"{OUT}/{name}.png", full_page=True)
    print(f"   📸 {name}.png")

def log(msg):
    print(f"\n[{time.strftime('%H:%M:%S')}] {msg}")

def main():
    print("="*70)
    print("   BRAIN Alpha Ops - 完整Alpha提交UI测试（最终版）")
    print("="*70)
    print(f"开始: {time.strftime('%H:%M:%S')}  |  账户: {EMAIL}")
    print("="*70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=['--window-size=1600,900'])
        page = browser.new_page(viewport={'width': 1600, 'height': 900})

        # ============================================================
        # 步骤1: 访问页面
        # ============================================================
        log("步骤1: 访问页面")
        page.goto(URL)
        time.sleep(8)
        ss(page, "01_page")
        print(f"   ✅ 标题: {page.title()}")

        # ============================================================
        # 步骤2: 导航到系统配置页
        # ============================================================
        log("步骤2: 点击侧边栏 '10 系统配置'")
        page.wait_for_selector("button:has-text('系统配置')", timeout=15000)
        time.sleep(1)
        page.locator("button:has-text('系统配置')").first.click()
        time.sleep(5)
        ss(page, "02_config")
        print("   ✅ 已进入配置页面")

        # ============================================================
        # 步骤3: 填写凭证（inputs[1]=email, inputs[2]=password）
        # ============================================================
        log("步骤3: 填写凭证")

        # 通过type属性找到正确的输入框
        email_input = page.locator("input[type='text']").first  # inputs[1]
        password_input = page.locator("input[type='password']").first  # inputs[2]

        email_input.wait_for(state="visible", timeout=10000)
        email_input.fill(EMAIL)
        print(f"   ✅ 邮箱已填写: {EMAIL}")
        time.sleep(1)

        password_input.wait_for(state="visible", timeout=10000)
        password_input.fill(PASSWORD)
        print("   ✅ 密码已填写")
        time.sleep(1)

        ss(page, "03_credentials")

        # ============================================================
        # 步骤4: 点击 "测试 BRAIN 连接"
        # ============================================================
        log("步骤4: 点击 '测试 BRAIN 连接'")

        connect_btn = page.locator("button:has-text('测试 BRAIN 连接')").first
        connect_btn.wait_for(state="visible", timeout=10000)
        connect_btn.click()
        print("   ✅ 已点击连接按钮")

        # 等待认证结果
        log("   等待认证结果...")
        time.sleep(15)

        # 检查结果
        text = page.inner_text("body")
        if "连接正常" in text or "成功" in text:
            print("   ✅ 认证成功！")
        elif "失败" in text:
            print("   ❌ 认证失败！")
        else:
            print("   ⚠️ 状态不明确")

        ss(page, "04_connected")

        # ============================================================
        # 步骤5: 返回运行总览
        # ============================================================
        log("步骤5: 返回 '01 运行总览'")
        page.locator("button:has-text('运行总览')").first.click()
        time.sleep(5)
        ss(page, "05_dashboard")

        # ============================================================
        # 步骤6: 开始生产验证
        # ============================================================
        log("步骤6: 点击 '运行非提交验证'")

        try:
            run_btn = page.locator("button:has-text('运行非提交验证')").first
            run_btn.wait_for(state="visible", timeout=15000)
            run_btn.click()
            print("   ✅ 生产已启动")
        except Exception as e:
            print(f"   ⚠️ 启动失败: {e}")
            # 可能需要先点击其他地方
            try:
                page.locator("button:has-text('开始首次同步')").first.click()
                print("   ✅ 开始首次同步")
            except:
                pass

        time.sleep(10)
        ss(page, "06_running")

        # ============================================================
        # 步骤7: 等待生产进度
        # ============================================================
        log("步骤7: 等待生产进度（最多90秒）")
        for i in range(9):
            time.sleep(10)
            try:
                t = page.inner_text("body")
                if "完成" in t or "completed" in t.lower():
                    print(f"   ✅ 生产完成！")
                    break
                print(f"   ⏳ 已等待 {(i+1)*10}s...")
            except:
                pass
        ss(page, "07_done")

        # ============================================================
        # 步骤8-10: 候选发现 → 提交就绪
        # ============================================================
        log("步骤8: 查看 '候选发现'")
        try:
            page.locator("button:has-text('候选管理')").first.click()
            time.sleep(5)
            ss(page, "08_candidates")
            print("   ✅ 已进入候选管理")
        except:
            print("   ⚠️ 跳过候选管理")

        log("步骤9: 查看 '提交就绪'")
        try:
            page.locator("button:has-text('阻断复核')").first.click()
            time.sleep(5)
            ss(page, "09_submission")
            print("   ✅ 已进入阻断复核")
        except:
            print("   ⚠️ 跳过阻断复核")

        # ============================================================
        # 完成
        # ============================================================
        print("\n" + "="*70)
        print("   📊 测试完成")
        print("="*70)
        print(f"\n   完成时间: {time.strftime('%H:%M:%S')}")
        print(f"   截图: {OUT}/")
        print("\n" + "="*70)
        print("   ⏸️ 浏览器保持打开60秒...")
        time.sleep(60)
        browser.close()
        print("\n   ✅ 测试完成！")

if __name__ == "__main__":
    main()
