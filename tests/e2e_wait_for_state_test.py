"""
BRAIN Alpha Ops - 等待"读取本地状态"完成后再登录

关键修复：
1. 等待"状态读取中"消失
2. 等待登录表单出现
3. 然后填写凭据
"""

from playwright.sync_api import sync_playwright
import time
import os

EMAIL = "547820639@qq.com"
PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
URL = "http://127.0.0.1:8765"
OUTPUT = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/wait_test"

def screenshot(page, name):
    os.makedirs(OUTPUT, exist_ok=True)
    path = f"{OUTPUT}/{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"   📸 {name}.png")

def wait_for_state_read_complete(page, timeout=60000):
    """等待'读取本地状态'完成"""
    print("   ⏳ 等待'读取本地状态'完成...")
    
    try:
        # 方式1: 等待"状态读取中"消失
        page.wait_for_function("""
            () => {
                const elem = document.querySelector('.topbar-connection.loading');
                return !elem || !elem.classList.contains('loading');
            }
        """, timeout=timeout)
        print("   ✅ '状态读取中'已消失")
        return True
    except Exception as e:
        print(f"   ⚠️  方式1超时: {e}")
    
    try:
        # 方式2: 等待"状态读取失败"或"已连接"出现
        page.wait_for_function("""
            () => {
                const text = document.body.innerText;
                return text.includes('状态读取失败') || 
                       text.includes('已连接') || 
                       text.includes('connected') ||
                       text.includes('成功');
            }
        """, timeout=timeout)
        print("   ✅ 状态读取已完成（失败或成功）")
        return True
    except Exception as e:
        print(f"   ⚠️  方式2超时: {e}")
    
    # 方式3: 强制等待10秒
    print("   ⚠️  超时，强制等待10秒...")
    time.sleep(10)
    return False

def main():
    print("=" * 70)
    print("🧪 BRAIN Alpha Ops - 等待后登录")
    print("=" * 70)
    print(f"开始: {time.strftime('%H:%M:%S')}")
    print("=" * 70)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=['--window-size=1600,900']
        )
        page = browser.new_page(viewport={'width': 1600, 'height': 900})
        
        # =====================================================================
        # 步骤1: 访问页面
        # =====================================================================
        print("\n[1/10] 访问页面...")
        page.goto(URL)
        time.sleep(8)  # 等待React渲染
        screenshot(page, "01_initial")
        
        # =====================================================================
        # 步骤2: 清除存储
        # =====================================================================
        print("\n[2/10] 清除存储...")
        page.evaluate("localStorage.clear()")
        page.evaluate("sessionStorage.clear()")
        page.context.clear_cookies()
        page.reload()
        time.sleep(8)
        screenshot(page, "02_after_clear")
        print("   ✅ 存储已清除")
        
        # =====================================================================
        # 步骤3: 等待"读取本地状态"完成  ← 关键步骤！
        # =====================================================================
        print("\n[3/10] 等待'读取本地状态'完成...")
        wait_for_state_read_complete(page, timeout=60000)
        time.sleep(3)  # 额外等待渲染
        screenshot(page, "03_state_read_complete")
        
        # 检查当前状态
        page_text = page.inner_text("body")
        print(f"   📝 当前页面文本（前400字符）:\n{page_text[:400]}")
        
        # =====================================================================
        # 步骤4: 查找登录表单（现在应该出现了）
        # =====================================================================
        print("\n[4/10] 查找登录表单...")
        
        # 等待登录表单出现（最多30秒）
        try:
            print("   ⏳ 等待登录表单出现（最多30秒）...")
            page.wait_for_selector("input", timeout=30000)
            print("   ✅ 找到 input 元素！")
        except Exception as e:
            print(f"   ⚠️  等待超时: {e}")
        
        time.sleep(3)
        
        # 现在查找所有input
        inputs = page.query_selector_all("input")
        print(f"   📊 找到 {len(inputs)} 个 input 元素")
        
        for i, inp in enumerate(inputs):
            try:
                t = inp.get_attribute("type") or "text"
                p = inp.get_attribute("placeholder") or ""
                print(f"      [{i}] type={t}, placeholder='{p}'")
            except:
                pass
        
        screenshot(page, "04_login_form")
        
        # =====================================================================
        # 步骤5: 填写邮箱
        # =====================================================================
        if len(inputs) >= 1:
            print(f"\n[5/10] 填写邮箱...")
            try:
                inputs[0].fill(EMAIL)
                print(f"   ✅ 输入框[0] 已填写: {EMAIL}")
                time.sleep(1)
            except Exception as e:
                print(f"   ❌ 填写失败: {e}")
            screenshot(page, "05_email_filled")
        else:
            print(f"\n[5/10] ❌ 未找到邮箱输入框！")
        
        # =====================================================================
        # 步骤6: 填写密码
        # =====================================================================
        if len(inputs) >= 2:
            print(f"\n[6/10] 填写密码...")
            try:
                inputs[1].fill(PASSWORD)
                print("   ✅ 输入框[1] 已填写密码")
                time.sleep(1)
            except Exception as e:
                print(f"   ❌ 填写失败: {e}")
            screenshot(page, "06_password_filled")
        else:
            print(f"\n[6/10] ❌ 未找到密码输入框！")
        
        # =====================================================================
        # 步骤7: 点击连接按钮
        # =====================================================================
        print("\n[7/10] 查找并点击连接按钮...")
        
        # 重新获取所有按钮
        time.sleep(2)
        buttons = page.query_selector_all("button")
        print(f"   📊 找到 {len(buttons)} 个 button 元素")
        
        connect_button = None
        for btn in buttons:
            try:
                text = btn.inner_text()
                if text and any(kw in text for kw in ["连接", "Connect", "测试"]):
                    connect_button = btn
                    print(f"   ✅ 找到连接按钮: '{text}'")
                    break
            except:
                pass
        
        if connect_button:
            try:
                connect_button.click()
                print("   ✅ 已点击连接按钮")
            except Exception as e:
                print(f"   ❌ 点击失败: {e}")
        else:
            print("   ❌ 未找到连接按钮！")
        
        # 等待认证响应
        print("   ⏳ 等待认证响应（15秒）...")
        time.sleep(15)
        screenshot(page, "07_after_connect")
        
        # =====================================================================
        # 步骤8: 观察认证结果
        # =====================================================================
        print("\n[8/10] 观察认证结果...")
        
        page_text_after = page.inner_text("body")
        
        if any(kw in page_text_after for kw in ["成功", "connected", "已连接"]):
            print("   ✅ 认证成功！")
        elif any(kw in page_text_after for kw in ["失败", "error", "无效"]):
            print("   ❌ 认证失败！")
        else:
            print("   ⚠️  认证状态不明确")
            print(f"   📝 页面文本（前400字符）:\n{page_text_after[:400]}")
        
        screenshot(page, "08_auth_result")
        
        # =====================================================================
        # 步骤9-10: 后续流程
        # =====================================================================
        print("\n[9/10] 继续执行后续流程...")
        print("   ⚠️  后续步骤需要根据实际页面动态调整")
        
        screenshot(page, "09_final")
        
        # =====================================================================
        # 完成
        # =====================================================================
        print("\n" + "=" * 70)
        print("📊 测试执行总结")
        print("=" * 70)
        print(f"\n✅ 测试完成时间: {time.strftime('%H:%M:%S')}")
        print(f"✅ 最终URL: {page.url}")
        print(f"✅ 已保存截图至: {OUTPUT}/")
        
        print("\n📸 截图清单:")
        print("   - 01_initial.png")
        print("   - 02_after_clear.png")
        print("   - 03_state_read_complete.png")
        print("   - 04_login_form.png")
        print("   - 05_email_filled.png")
        print("   - 06_password_filled.png")
        print("   - 07_after_connect.png")
        print("   - 08_auth_result.png")
        print("   - 09_final.png")
        
        print("\n" + "=" * 70)
        print("⏸️  浏览器将保持打开60秒，便于观察...")
        time.sleep(60)
        browser.close()
        
        print("\n✅ UI交互测试完成！")
        print("=" * 70)

if __name__ == "__main__":
    main()
