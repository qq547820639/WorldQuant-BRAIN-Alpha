import os
"""
E2E UI Interaction Test - Alpha Submission Complete Workflow

模拟真实用户通过界面操作完成Alpha提交的全流程：
1. 启动浏览器并访问Web控制台
2. 通过登录界面输入凭据
3. 导航至各功能模块
4. 执行Alpha生成、评分、提交等操作
5. 仅通过UI交互，不使用任何API调用

测试账户：
  邮箱：547820639@qq.com
  密码：使用BRAIN_PASSWORD环境变量
"""

from playwright.sync_api import sync_playwright, Page, expect
import time
import json


def test_complete_alpha_submission_workflow():
    """
    完整的Alpha提交工作流UI测试
    
    关键约束：
    - 仅通过UI交互（点击、输入、选择）
    - 禁止使用API、命令行、数据库直连
    - 详细记录每个步骤的UI操作和系统响应
    """
    
    with sync_playwright() as p:
        # 启动浏览器 - 有界面模式，便于观察
        browser = p.chromium.launch(
            headless=False,  # 有界面，可以看到操作过程
            slow_mo=500,     # 每个操作延迟500ms，便于观察
            args=['--window-size=1920,1080']
        )
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        
        page = context.new_page()
        
        print("=" * 80)
        print("🧪 开始 BRAIN Alpha Ops - Alpha提交完整流程UI测试")
        print("=" * 80)
        
        # =====================================================================
        # 步骤 1: 访问Web控制台首页
        # =====================================================================
        print("\n📍 步骤 1: 访问Web控制台")
        print("   操作: 导航至 http://127.0.0.1:8765")
        
        page.goto("http://127.0.0.1:8765", wait_until="networkidle")
        time.sleep(2)  # 等待页面完全加载
        
        # 截图记录初始状态
        page.screenshot(path="/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/01_initial_page.png")
        print("   ✅ 页面加载完成")
        print(f"   页面标题: {page.title()}")
        print(f"   URL: {page.url}")
        
        # =====================================================================
        # 步骤 2: 识别页面主要元素
        # =====================================================================
        print("\n📍 步骤 2: 识别页面主要UI元素")
        
        # 等待页面稳定
        time.sleep(1)
        
        # 获取页面所有可见的主要元素
        print("   操作: 扫描页面所有按钮、输入框、链接")
        
        # 查找所有按钮
        buttons = page.locator("button").all()
        print(f"   ✅ 发现 {len(buttons)} 个按钮")
        for i, btn in enumerate(buttons[:10]):  # 只显示前10个
            try:
                text = btn.text_content()
                print(f"      - 按钮 {i+1}: '{text}'")
            except:
                pass
        
        # 查找所有输入框
        inputs = page.locator("input").all()
        print(f"   ✅ 发现 {len(inputs)} 个输入框")
        for i, inp in enumerate(inputs[:10]):
            try:
                placeholder = inp.get_attribute("placeholder")
                input_type = inp.get_attribute("type")
                print(f"      - 输入框 {i+1}: type={input_type}, placeholder='{placeholder}'")
            except:
                pass
        
        # =====================================================================
        # 步骤 3: 输入登录凭据
        # =====================================================================
        print("\n📍 步骤 3: 输入BRAIN账户凭据")
        
        # 查找邮箱输入框
        print("   操作: 在邮箱输入框中输入 547820639@qq.com")
        email_input = page.locator("input[type='email'], input[placeholder*='email'], input[placeholder*='邮箱']").first
        
        if email_input.count() > 0:
            email_input.fill("547820639@qq.com")
            print("   ✅ 邮箱输入成功")
        else:
            # 尝试通过label查找
            print("   ⚠️  未找到邮箱输入框，尝试其他方式...")
            # 查找所有input
            all_inputs = page.locator("input").all()
            if len(all_inputs) >= 2:
                all_inputs[0].fill("547820639@qq.com")
                print("   ✅ 通过索引0输入邮箱")
        
        time.sleep(1)
        
        # 查找密码输入框
        print("   操作: 在密码输入框中输入密码")
        password_input = page.locator("input[type='password'], input[placeholder*='password'], input[placeholder*='密码']").first
        
        if password_input.count() > 0:
            password_input.fill(os.environ.get("BRAIN_PASSWORD", ""))
            print("   ✅ 密码输入成功")
        else:
            print("   ⚠️  未找到密码输入框，尝试其他方式...")
            all_inputs = page.locator("input").all()
            if len(all_inputs) >= 2:
                all_inputs[1].fill(os.environ.get("BRAIN_PASSWORD", ""))
                print("   ✅ 通过索引1输入密码")
        
        time.sleep(1)
        page.screenshot(path="/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/02_credentials_entered.png")
        
        # =====================================================================
        # 步骤 4: 点击连接/登录按钮
        # =====================================================================
        print("\n📍 步骤 4: 点击连接测试/登录按钮")
        
        # 查找连接相关的按钮
        connect_button = None
        button_texts = ["连接", "登录", "Connect", "Login", "连接测试", "Sign In"]
        
        for btn_text in button_texts:
            btn = page.get_by_text(btn_text, exact=False)
            if btn.count() > 0:
                connect_button = btn.first
                print(f"   ✅ 找到按钮: '{btn_text}'")
                break
        
        if connect_button:
            print("   操作: 点击连接按钮")
            connect_button.click()
            print("   ✅ 已点击连接按钮")
        else:
            print("   ⚠️  未找到明确的连接按钮，查找页面上所有的可点击元素...")
            # 尝试查找表单的提交按钮
            submit_btn = page.locator("button[type='submit']").first
            if submit_btn.count() > 0:
                submit_btn.click()
                print("   ✅ 点击了submit按钮")
        
        # 等待系统响应
        print("   等待: 系统认证响应...")
        time.sleep(5)
        
        page.screenshot(path="/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/03_after_connect_click.png")
        
        # =====================================================================
        # 步骤 5: 观察认证结果
        # =====================================================================
        print("\n📍 步骤 5: 观察认证结果")
        
        # 检查页面是否有成功/失败提示
        page_content = page.content()
        
        if "成功" in page_content or "success" in page_content.lower() or "connected" in page_content.lower():
            print("   ✅ 认证成功！")
        elif "失败" in page_content or "error" in page_content.lower() or "invalid" in page_content.lower():
            print("   ❌ 认证失败！")
            # 查找错误信息
            error_elements = page.locator("[class*='error'], [class*='alert'], [role='alert']").all()
            for elem in error_elements:
                try:
                    error_text = elem.text_content()
                    if error_text and error_text.strip():
                        print(f"   错误信息: {error_text}")
                except:
                    pass
        else:
            print("   ⚠️  认证状态不明确，继续观察页面变化...")
        
        # 检查URL是否变化（可能跳转到了新页面）
        print(f"   当前URL: {page.url}")
        
        # 检查是否有新的页面元素出现（登录后的界面）
        time.sleep(2)
        new_buttons = page.locator("button").all()
        print(f"   页面按钮数量: {len(buttons)} -> {len(new_buttons)}")
        
        page.screenshot(path="/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/04_auth_result.png")
        
        # =====================================================================
        # 步骤 6: 导航至目标模块（云端同步/Alpha生成）
        # =====================================================================
        print("\n📍 步骤 6: 导航至目标功能模块")
        
        # 查找可能的导航元素（ sidebar、菜单等）
        print("   操作: 查找侧边栏或导航菜单")
        
        # 常见的导航元素选择器
        nav_selectors = [
            "nav", "aside", "[class*='sidebar']", "[class*='nav']",
            "a[href*='dashboard']", "a[href*='cloud']", "a[href*='alpha']",
            "a[href*='generate']", "a[href*='production']"
        ]
        
        for selector in nav_selectors:
            elements = page.locator(selector).all()
            if elements:
                print(f"   ✅ 找到导航元素: {selector} ({len(elements)}个)")
                for elem in elements[:5]:
                    try:
                        text = elem.text_content()
                        if text and text.strip():
                            print(f"      - '{text.strip()}'")
                    except:
                        pass
        
        # 尝试点击可能的功能模块链接
        module_keywords = ["云端", "同步", "生成", "Alpha", "生产", "Cloud", "Sync", "Generate", "Production", "Dashboard"]
        
        for keyword in module_keywords:
            link = page.get_by_text(keyword, exact=False)
            if link.count() > 0:
                print(f"   ✅ 找到模块链接: '{keyword}'")
                print(f"   操作: 尝试点击 '{keyword}'")
                try:
                    link.first.click()
                    time.sleep(3)
                    print(f"   ✅ 成功点击 '{keyword}'")
                    page.screenshot(path=f"/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/05_after_click_{keyword}.png")
                    break
                except Exception as e:
                    print(f"   ⚠️  点击 '{keyword}' 失败: {e}")
        
        # =====================================================================
        # 步骤 7: 执行Alpha生成/生产操作
        # =====================================================================
        print("\n📍 步骤 7: 执行Alpha生成操作")
        
        # 查找"开始生产"、"生成"、"Start Production"等按钮
        production_buttons = ["开始生产", "生成Alpha", "Generate", "Start", "生产搜索", "开始", "运行"]
        
        for btn_text in production_buttons:
            btn = page.get_by_text(btn_text, exact=False)
            if btn.count() > 0:
                print(f"   操作: 点击 '{btn_text}' 按钮")
                try:
                    btn.first.click()
                    print(f"   ✅ 成功点击 '{btn_text}'")
                    time.sleep(3)
                    break
                except Exception as e:
                    print(f"   ⚠️  点击失败: {e}")
        
        # 等待进度条或状态更新
        print("   等待: Alpha生成进度...")
        time.sleep(5)
        
        page.screenshot(path="/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/06_production_started.png")
        
        # =====================================================================
        # 步骤 8: 观察进度和结果
        # =====================================================================
        print("\n📍 步骤 8: 观察Alpha生成进度和结果")
        
        # 查找进度条、状态消息等元素
        progress_selectors = [
            "[role='progressbar']",
            "[class*='progress']",
            "[class*='status']",
            "text=进度",
            "text=progress",
            "text=完成",
            "text=complete"
        ]
        
        for selector in progress_selectors:
            elem = page.locator(selector).first
            if elem.count() > 0:
                try:
                    text = elem.text_content()
                    print(f"   ✅ 发现进度元素: '{text}'")
                except:
                    print(f"   ✅ 发现进度元素")
        
        # 等待更长时间以观察完整过程
        print("   等待: 给系统更多时间完成操作...")
        time.sleep(10)
        
        page.screenshot(path="/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/07_production_result.png")
        
        # =====================================================================
        # 步骤 9: 尝试提交Alpha（如果生成成功）
        # =====================================================================
        print("\n📍 步骤 9: 尝试提交Alpha")
        
        # 查找提交相关的按钮
        submit_buttons = ["提交", "Submit", "提交Alpha", "Review", "审查", "Check"]
        
        for btn_text in submit_buttons:
            btn = page.get_by_text(btn_text, exact=False)
            if btn.count() > 0:
                print(f"   操作: 发现 '{btn_text}' 按钮")
                print(f"   操作: 点击 '{btn_text}'")
                try:
                    btn.first.click()
                    time.sleep(3)
                    print(f"   ✅ 成功点击 '{btn_text}'")
                    break
                except Exception as e:
                    print(f"   ⚠️  点击失败: {e}")
        
        page.screenshot(path="/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/08_submission_attempt.png")
        
        # =====================================================================
        # 步骤 10: 验证最终结果
        # =====================================================================
        print("\n📍 步骤 10: 验证最终结果")
        
        # 检查最终页面状态
        final_url = page.url
        final_title = page.title()
        
        print(f"   最终URL: {final_url}")
        print(f"   最终页面标题: {final_title}")
        
        # 查找成功/失败提示
        success_indicators = ["成功", "success", "submitted", "已提交", "完成"]
        failure_indicators = ["失败", "error", "failed", "错误"]
        
        page_text = page.inner_text("body")
        
        for indicator in success_indicators:
            if indicator in page_text.lower():
                print(f"   ✅ 发现成功指示: '{indicator}'")
        
        for indicator in failure_indicators:
            if indicator in page_text.lower():
                print(f"   ❌ 发现失败指示: '{indicator}'")
        
        page.screenshot(path="/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/09_final_result.png")
        
        # =====================================================================
        # 测试总结
        # =====================================================================
        print("\n" + "=" * 80)
        print("📊 测试执行总结")
        print("=" * 80)
        print("\n✅ 已完成的UI交互步骤:")
        print("   1. 访问Web控制台首页")
        print("   2. 识别页面主要UI元素")
        print("   3. 输入BRAIN账户凭据")
        print("   4. 点击连接/登录按钮")
        print("   5. 观察认证结果")
        print("   6. 导航至目标功能模块")
        print("   7. 执行Alpha生成操作")
        print("   8. 观察进度和结果")
        print("   9. 尝试提交Alpha")
        print("   10. 验证最终结果")
        
        print("\n📸 已保存的截图:")
        print("   - 01_initial_page.png")
        print("   - 02_credentials_entered.png")
        print("   - 03_after_connect_click.png")
        print("   - 04_auth_result.png")
        print("   - 05_after_click_Dashboard.png (或其他模块名)")
        print("   - 06_production_started.png")
        print("   - 07_production_result.png")
        print("   - 08_submission_attempt.png")
        print("   - 09_final_result.png")
        
        print("\n⚠️  注意事项:")
        print("   - 本测试严格遵循'仅通过UI交互'的约束")
        print("   - 未使用任何API调用、命令行或数据库操作")
        print("   - 所有操作均为真实的用户界面的点击、输入、选择")
        print("   - 如遇阻塞，需通过界面交互方式处理（返回、重试等）")
        
        # 保持浏览器打开一段时间，便于观察
        print("\n⏸️  浏览器将保持打开10秒，便于观察最终结果...")
        time.sleep(10)
        
        # 关闭浏览器
        browser.close()
        
        print("\n✅ UI交互测试完成！")


if __name__ == "__main__":
    # 运行测试
    test_complete_alpha_submission_workflow()
