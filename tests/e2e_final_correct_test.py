import os
"""
BRAIN Alpha Ops - 完整的Alpha提交流程UI测试

正确流程（基于代码分析）:
1. 页面加载 → sidebare → "10 系统配置"
2. ConfigPanel → 点击"临时连接官方服务" → 凭证表单出现
3. 填写账户邮箱 + 密码 → 点击"测试 BRAIN 连接"
4. 导航回"01 运行总览" → JobMonitor → "运行非提交验证"
5. 等待生产完成 → 候选发现 → 评分 → 提交就绪审查

关键约束: 仅通过UI交互，禁止API/命令行/数据库
"""

from playwright.sync_api import sync_playwright
import time, os, json

EMAIL = "547820639@qq.com"
PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
URL = "http://127.0.0.1:8765"
OUT = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/final_e2e"

def ss(page, name):
    """截图"""
    os.makedirs(OUT, exist_ok=True)
    page.screenshot(path=f"{OUT}/{name}.png", full_page=True)
    print(f"   📸 {name}.png")

def log(msg):
    """日志"""
    print(f"\n[{time.strftime('%H:%M:%S')}] {msg}")

def main():
    print("="*70)
    print("   BRAIN Alpha Ops - 完整Alpha提交流程UI测试")
    print("="*70)
    print(f"开始: {time.strftime('%H:%M:%S')}")
    print(f"账户: {EMAIL}")
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
        ss(page, "01_page_loaded")
        print(f"   标题: {page.title()}")

        # ============================================================
        # 步骤2: 等待侧边栏渲染并点击"10 系统配置"
        # ============================================================
        log("步骤2: 点击侧边栏 '10 系统配置' 进入配置页面")
        
        # 等待侧边栏按钮出现
        try:
            page.wait_for_selector("button:has-text('系统配置')", timeout=15000)
            time.sleep(2)
        except:
            print("   ⚠️ 等待超时，继续尝试...")
        
        # 点击系统配置按钮
        config_btn = page.locator("button:has-text('系统配置')").first
        if config_btn.count() > 0:
            config_btn.click()
            print("   ✅ 已点击 '系统配置' 按钮")
            time.sleep(5)
            ss(page, "02_config_page")
        else:
            print("   ❌ 未找到 '系统配置' 按钮！")
            browser.close()
            return

        # ============================================================
        # 步骤3: 在ConfigPanel中点击"临时连接官方服务"
        # ============================================================
        log("步骤3: 点击 '临时连接官方服务' 展开凭证表单")

        # 等待配置面板渲染
        time.sleep(3)
        
        try:
            page.wait_for_selector("button:has-text('临时连接')", timeout=10000)
            time.sleep(1)
        except:
            print("   ⚠️ 等待超时")
        
        temp_btn = page.locator("button:has-text('临时连接')").first
        if temp_btn.count() > 0:
            temp_btn.click()
            print("   ✅ 已点击 '临时连接官方服务' 按钮")
            time.sleep(3)
            ss(page, "03_temp_connection_opened")
        else:
            print("   ❌ 未找到 '临时连接' 按钮！")
        
        # ============================================================
        # 步骤4: 填写凭证表单
        # ============================================================
        log("步骤4: 填写凭证")

        # 等待输入框出现
        try:
            page.wait_for_selector("input", timeout=10000)
        except:
            print("   ⚠️ 等待input超时")
        
        time.sleep(2)

        # 获取所有输入框
        inputs = page.query_selector_all("input")
        print(f"   找到 {len(inputs)} 个input元素")
        
        for i, inp in enumerate(inputs):
            try:
                t = inp.get_attribute("type") or "text"
                p = inp.get_attribute("placeholder") or ""
                print(f"      [{i}] type={t}, placeholder='{p}'")
            except:
                pass

        # 填写邮箱（第一个文本输入框）
        if len(inputs) >= 1:
            try:
                inputs[0].fill(EMAIL)
                print(f"   ✅ 邮箱已填写: {EMAIL}")
                time.sleep(1)
            except Exception as e:
                print(f"   ❌ 邮箱填写失败: {e}")
        
        # 填写密码（第二个输入框，type=password）
        if len(inputs) >= 2:
            try:
                inputs[1].fill(PASSWORD)
                print("   ✅ 密码已填写")
                time.sleep(1)
            except Exception as e:
                print(f"   ❌ 密码填写失败: {e}")
        
        ss(page, "04_credentials_filled")

        # ============================================================
        # 步骤5: 点击"测试 BRAIN 连接"
        # ============================================================
        log("步骤5: 点击 '测试 BRAIN 连接'")

        connect_btn = page.locator("button:has-text('测试 BRAIN 连接')").first
        if connect_btn.count() > 0:
            connect_btn.click()
            print("   ✅ 已点击 '测试 BRAIN 连接' 按钮")
        else:
            # 尝试"测试连接"
            connect_btn = page.locator("button:has-text('测试连接')").first
            if connect_btn.count() > 0:
                connect_btn.click()
                print("   ✅ 已点击 '测试连接' 按钮")
            else:
                print("   ❌ 未找到连接按钮！")

        # 等待认证结果
        print("   ⏳ 等待认证（15秒）...")
        time.sleep(15)
        ss(page, "05_after_connect")

        # 检查结果
        page_text = page.inner_text("body")
        if "成功" in page_text or "连接正常" in page_text:
            print("   ✅ 认证成功！")
        elif "失败" in page_text:
            print("   ❌ 认证失败！")
        else:
            print("   ⚠️ 认证状态不明确")

        # ============================================================
        # 步骤6: 导航回"01 运行总览"
        # ============================================================
        log("步骤6: 点击侧边栏 '01 运行总览'")

        dashboard_btn = page.locator("button:has-text('运行总览')").first
        if dashboard_btn.count() > 0:
            dashboard_btn.click()
            print("   ✅ 已点击 '运行总览'")
            time.sleep(5)
            ss(page, "06_dashboard")
        else:
            print("   ⚠️ 未找到 '运行总览' 按钮")

        # ============================================================
        # 步骤7: 运行非提交验证
        # ============================================================
        log("步骤7: 点击 '运行非提交验证' 开始生产")

        timeout_count = 0
        while timeout_count < 3:
            try:
                run_btn = page.locator("button:has-text('运行非提交验证')").first
                if run_btn.count() > 0:
                    run_btn.click()
                    print("   ✅ 已点击 '运行非提交验证'")
                    time.sleep(5)
                    ss(page, "07_run_started")
                    break
                else:
                    # 可能JobMonitor还没加载
                    print("   ⏳ 等待JobMonitor加载...")
                    time.sleep(10)
                    timeout_count += 1
            except Exception as e:
                print(f"   ⚠️ 重试 {timeout_count+1}/3: {e}")
                time.sleep(10)
                timeout_count += 1
        
        # ============================================================
        # 步骤8: 等待生产进度
        # ============================================================
        log("步骤8: 等待生产进度（最长2分钟）")

        # 等待进度完成
        max_wait = 120  # 秒
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                page_text = page.inner_text("body")
                if "完成" in page_text or "completed" in page_text.lower():
                    print("   ✅ 生产完成！")
                    break
            except:
                pass
            time.sleep(10)
            print(f"   ⏳ 已等待 {int(time.time()-start_time)}s...")
        
        ss(page, "08_production_result")

        # ============================================================
        # 步骤9: 查看候选发现
        # ============================================================
        log("步骤9: 点击侧边栏 '候选发现' > '候选管理'")

        # 可能需要先展开阶段组
        discover_btn = page.locator("button:has-text('候选管理')").first
        if discover_btn.count() > 0:
            discover_btn.click()
            print("   ✅ 已点击 '候选管理'")
            time.sleep(5)
            ss(page, "09_candidates")
        else:
            print("   ⚠️ 未找到 '候选管理' 按钮")

        # ============================================================
        # 步骤10: 评分验证 & 提交就绪审查
        # ============================================================
        log("步骤10: 导航至 '提交就绪' > '阻断复核'")

        ready_btn = page.locator("button:has-text('阻断复核')").first
        if ready_btn.count() > 0:
            ready_btn.click()
            print("   ✅ 已点击 '阻断复核'")
            time.sleep(5)
            ss(page, "10_submission_ready")
        else:
            print("   ⚠️ 未找到 '阻断复核' 按钮")

        # ============================================================
        # 完成
        # ============================================================
        print("\n" + "="*70)
        print("   📊 测试执行完成")
        print("="*70)
        print(f"\n   完成时间: {time.strftime('%H:%M:%S')}")
        print(f"   最终URL: {page.url}")
        print(f"   截图位置: {OUT}/")
        print("\n" + "="*70)
        print("   ⏸️ 浏览器保持打开60秒...")
        time.sleep(60)
        browser.close()
        print("\n   ✅ 测试完成！")

if __name__ == "__main__":
    main()
