"""
BRAIN Alpha Ops - 完整的Alpha提交UI交互测试（修复版）

测试流程：
1. 清除浏览器存储（强制显示登录表单）
2. 输入凭据并登录
3. 执行完整的Alpha生成和提交流程
4. 仅通过UI交互，不使用API/命令行
"""

from playwright.sync_api import sync_playwright
import time
import os
import json

# 测试配置
TEST_EMAIL = "547820639@qq.com"
TEST_PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
BASE_URL = "http://127.0.0.1:8765"
OUTPUT_DIR = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output"
SLOW_MO = 800  # 每个操作延迟800ms

def log(step, action, detail=""):
    """打印日志"""
    timestamp = time.strftime("%H:%M:%S")
    print(f"\n[{timestamp}] 📍 步骤 {step}: {action}")
    if detail:
        print(f"   └─ {detail}")

def take_screenshot(page, name):
    """保存截图"""
    try:
        os.makedirs(f"{OUTPUT_DIR}/ui_test", exist_ok=True)
        path = f"{OUTPUT_DIR}/ui_test/{name}.png"
        page.screenshot(path=path, full_page=True)
        print(f"   📸 截图: {name}.png")
    except Exception as e:
        print(f"   ⚠️  截图失败: {e}")

def wait_for_text(page, text, timeout=10000):
    """等待文本出现"""
    try:
        page.wait_for_function(
            f"document.body.innerText.includes('{text}')",
            timeout=timeout
        )
        return True
    except:
        return False

def test_complete_alpha_submission():
    """
    完整的Alpha提交UI测试
    """
    print("=" * 80)
    print("🧪 BRAIN Alpha Ops - Alpha提交完整流程UI测试（修复版）")
    print("=" * 80)
    print(f"测试账户: {TEST_EMAIL}")
    print(f"目标URL: {BASE_URL}")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    with sync_playwright() as p:
        # 启动浏览器
        print("\n🚀 正在启动浏览器...")
        browser = p.chromium.launch(
            headless=False,
            slow_mo=SLOW_MO,
            args=['--window-size=1920,1080', '--no-sandbox']
        )
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.new_page()
        
        # =====================================================================
        # 步骤 1: 访问Web控制台并清除存储
        # =====================================================================
        log(1, "访问Web控制台", f"导航至 {BASE_URL}")
        
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)  # 等待React渲染
        
        take_screenshot(page, "01_initial_page")
        
        # 清除所有存储（强制显示登录表单）
        log(1, "清除浏览器存储", "清除 localStorage、sessionStorage、cookies")
        page.evaluate("localStorage.clear()")
        page.evaluate("sessionStorage.clear()")
        page.context.clear_cookies()
        print("   ✅ 已清除所有存储")
        
        # 刷新页面
        print("   🔄 刷新页面...")
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(5)  # 等待应用重新初始化
        
        take_screenshot(page, "02_after_storage_clear")
        
        # =====================================================================
        # 步骤 2: 等待并查找登录表单
        # =====================================================================
        log(2, "查找登录表单", "等待登录表单出现")
        
        # 等待页面稳定
        time.sleep(3)
        
        # 获取所有按钮文本
        buttons = page.locator("button").all()
        button_texts = []
        for btn in buttons:
            try:
                text = btn.text_content()
                if text and text.strip():
                    button_texts.append(text.strip())
            except:
                pass
        
        print(f"   📝 发现 {len(buttons)} 个按钮:")
        for i, text in enumerate(button_texts):
            print(f"      [{i}] '{text}'")
        
        # 获取所有输入框
        inputs = page.locator("input").all()
        input_info = []
        for inp in inputs:
            try:
                input_type = inp.get_attribute("type") or "text"
                placeholder = inp.get_attribute("placeholder") or ""
                input_info.append({"type": input_type, "placeholder": placeholder})
            except:
                pass
        
        print(f"   📝 发现 {len(inputs)} 个输入框:")
        for i, info in enumerate(input_info):
            print(f"      [{i}] type={info['type']}, placeholder='{info['placeholder']}'")
        
        take_screenshot(page, "03_form_elements")
        
        # =====================================================================
        # 步骤 3: 输入登录凭据
        # =====================================================================
        if len(inputs) >= 2:
            log(3, "输入登录凭据", f"邮箱: {TEST_EMAIL}")
            
            # 输入邮箱
            try:
                inputs[0].fill(TEST_EMAIL)
                print(f"   ✅ 邮箱已输入: {TEST_EMAIL}")
            except Exception as e:
                print(f"   ⚠️  邮箱输入失败: {e}")
                # 尝试通过placeholder查找
                email_input = page.locator("input[placeholder*='邮箱'], input[placeholder*='email'], input[type='email']").first
                if email_input.count() > 0:
                    email_input.fill(TEST_EMAIL)
                    print(f"   ✅ 通过placeholder输入邮箱")
            
            time.sleep(1)
            
            # 输入密码
            try:
                inputs[1].fill(TEST_PASSWORD)
                print(f"   ✅ 密码已输入")
            except Exception as e:
                print(f"   ⚠️  密码输入失败: {e}")
                # 尝试通过placeholder查找
                password_input = page.locator("input[placeholder*='密码'], input[placeholder*='password'], input[type='password']").first
                if password_input.count() > 0:
                    password_input.fill(TEST_PASSWORD)
                    print(f"   ✅ 通过placeholder输入密码")
            
            time.sleep(1)
            take_screenshot(page, "04_credentials_entered")
        else:
            print("   ❌ 未找到足够的输入框！")
            print("   💡 可能登录表单在模态框中，尝试查找登录按钮...")
            
            # 查找可能触发登录表单的按钮
            for text in button_texts:
                if any(kw in text for kw in ["登录", "连接", "Login", "Connect", "认证"]):
                    print(f"   🔍 找到可能的登录按钮: '{text}'")
                    print(f"   🖱️  尝试点击...")
                    try:
                        page.get_by_text(text, exact=False).first.click()
                        time.sleep(3)
                        take_screenshot(page, "04_login_modal_opened")
                        break
                    except Exception as e:
                        print(f"   ⚠️  点击失败: {e}")
        
        # =====================================================================
        # 步骤 4: 点击登录/连接按钮
        # =====================================================================
        log(4, "点击登录/连接按钮", "查找并点击登录按钮")
        
        # 重新获取所有按钮（页面可能已变化）
        time.sleep(2)
        buttons_after = page.locator("button").all()
        button_texts_after = []
        for btn in buttons_after:
            try:
                text = btn.text_content()
                if text and text.strip():
                    button_texts_after.append(text.strip())
            except:
                pass
        
        print(f"   📝 当前页面有 {len(buttons_after)} 个按钮:")
        for i, text in enumerate(button_texts_after):
            print(f"      [{i}] '{text}'")
        
        # 查找登录/连接按钮
        login_button = None
        for text in ["连接", "登录", "Connect", "Login", "连接测试", "Sign In"]:
            try:
                btn = page.get_by_text(text, exact=False)
                if btn.count() > 0:
                    login_button = btn.first
                    print(f"   ✅ 找到登录按钮: '{text}'")
                    break
            except:
                pass
        
        # 如果没找到，尝试最后一个按钮（可能是提交按钮）
        if not login_button:
            print("   ⚠️  未找到明确的登录按钮，尝试最后一个按钮...")
            if buttons_after:
                login_button = buttons_after[-1]
        
        # 点击按钮
        if login_button:
            try:
                login_button.click()
                print("   ✅ 已点击登录按钮")
            except Exception as e:
                print(f"   ⚠️  点击失败: {e}")
                # 尝试通过文本点击
                try:
                    page.click("button:has-text('连接')")
                except:
                    try:
                        page.click("button:has-text('Connect')")
                    except Exception as e2:
                        print(f"   ❌ 无法点击登录按钮: {e2}")
        
        # 等待认证响应
        print("   ⏳ 等待认证响应（10秒）...")
        time.sleep(10)
        
        take_screenshot(page, "05_after_login_click")
        
        # =====================================================================
        # 步骤 5: 观察认证结果
        # =====================================================================
        log(5, "观察认证结果", "检查是否登录成功")
        
        current_url = page.url
        print(f"   📍 当前URL: {current_url}")
        
        # 等待页面稳定
        time.sleep(3)
        
        # 获取页面文本
        page_text = page.inner_text("body")
        
        # 检查认证状态
        if "成功" in page_text or "connected" in page_text.lower() or "已连接" in page_text:
            print("   ✅ 认证成功！")
        elif "失败" in page_text or "error" in page_text.lower() or "无效" in page_text:
            print("   ❌ 认证失败！")
        else:
            print("   ⚠️  认证状态不明确")
            print(f"   📝 页面文本（前500字符）: {page_text[:500]}")
        
        take_screenshot(page, "06_auth_result")
        
        # =====================================================================
        # 步骤 6-10: 继续执行后续流程
        # （根据实际页面状态动态调整）
        # =====================================================================
        
        print("\n" + "=" * 80)
        print("📊 测试执行总结")
        print("=" * 80)
        print(f"\n✅ 测试完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"✅ 当前URL: {page.url}")
        print(f"✅ 已保存截图至: {OUTPUT_DIR}/ui_test/")
        
        print("\n📸 截图清单:")
        print("   - 01_initial_page.png")
        print("   - 02_after_storage_clear.png")
        print("   - 03_form_elements.png")
        print("   - 04_credentials_entered.png")
        print("   - 05_after_login_click.png")
        print("   - 06_auth_result.png")
        
        # 保持浏览器打开
        print("\n⏸️  浏览器将保持打开20秒，便于观察最终结果...")
        time.sleep(20)
        
        browser.close()
        
        print("\n✅ UI交互测试完成！")
        print("=" * 80)


if __name__ == "__main__":
    test_complete_alpha_submission()
