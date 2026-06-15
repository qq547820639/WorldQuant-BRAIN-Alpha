"""
BRAIN Alpha Ops - 正确的Alpha提交UI测试

关键修复：
1. 先点击"1. 账户/缓存"展开区域
2. 等待登录表单出现
3. 填写凭据并登录
"""

from playwright.sync_api import sync_playwright
import time
import os

EMAIL = "547820639@qq.com"
PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
URL = "http://127.0.0.1:8765"
OUTPUT = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/correct_test"

def screenshot(page, name):
    os.makedirs(OUTPUT, exist_ok=True)
    path = f"{OUTPUT}/{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"   📸 {name}.png")

def main():
    print("=" * 70)
    print("🧪 BRAIN Alpha Ops - 正确流程UI测试")
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
        print("\n[1/12] 访问页面...")
        page.goto(URL)
        time.sleep(8)  # 等待React完全渲染
        screenshot(page, "01_initial")
        
        # =====================================================================
        # 步骤2: 清除存储
        # =====================================================================
        print("\n[2/12] 清除存储...")
        page.evaluate("localStorage.clear()")
        page.evaluate("sessionStorage.clear()")
        page.context.clear_cookies()
        page.reload()
        time.sleep(8)
        screenshot(page, "02_after_clear")
        print("   ✅ 存储已清除")
        
        # =====================================================================
        # 步骤3: 点击"1. 账户/缓存"展开区域  ← 关键步骤！
        # =====================================================================
        print("\n[3/12] 点击'账户/缓存'展开区域...")
        
        # 尝试多种方式找到并点击这个区域
        clicked = False
        
        # 方式1: 通过文本查找
        try:
            elem = page.get_by_text("账户/缓存", exact=False)
            if elem.count() > 0:
                elem.first.click()
                print("   ✅ 通过文本点击了'账户/缓存'")
                clicked = True
                time.sleep(3)
        except Exception as e:
            print(f"   ⚠️  方式1失败: {e}")
        
        # 方式2: 通过"1."查找
        if not clicked:
            try:
                elem = page.get_by_text("1.", exact=False)
                if elem.count() > 0:
                    elem.first.click()
                    print("   ✅ 通过'1.'点击了展开区域")
                    clicked = True
                    time.sleep(3)
            except Exception as e:
                print(f"   ⚠️  方式2失败: {e}")
        
        # 方式3: 点击包含"账户"的元素
        if not clicked:
            try:
                elem = page.locator("*:has-text('账户')").first
                if elem.count() > 0:
                    elem.click()
                    print("   ✅ 点击了包含'账户'的元素")
                    clicked = True
                    time.sleep(3)
            except Exception as e:
                print(f"   ⚠️  方式3失败: {e}")
        
        screenshot(page, "03_section_expanded")
        
        # =====================================================================
        # 步骤4: 查找登录表单（展开后应该出现）
        # =====================================================================
        print("\n[4/12] 查找登录表单...")
        time.sleep(3)  # 等待展开动画
        
        # 获取所有input
        inputs = page.query_selector_all("input")
        print(f"   📊 找到 {len(inputs)} 个input")
        
        for i, inp in enumerate(inputs):
            try:
                t = inp.get_attribute("type") or "text"
                p = inp.get_attribute("placeholder") or ""
                print(f"      [{i}] type={t}, placeholder='{p}'")
            except:
                pass
        
        screenshot(page, "04_form_visible")
        
        # =====================================================================
        # 步骤5: 填写邮箱
        # =====================================================================
        print("\n[5/12] 填写邮箱...")
        
        if len(inputs) >= 1:
            try:
                inputs[0].fill(EMAIL)
                print(f"   ✅ 输入框[0] 已填写: {EMAIL}")
                time.sleep(1)
            except Exception as e:
                print(f"   ❌ 填写失败: {e}")
        else:
            print("   ❌ 未找到邮箱输入框！")
        
        screenshot(page, "05_email_filled")
        
        # =====================================================================
        # 步骤6: 填写密码
        # =====================================================================
        print("\n[6/12] 填写密码...")
        
        if len(inputs) >= 2:
            try:
                inputs[1].fill(PASSWORD)
                print("   ✅ 输入框[1] 已填写密码")
                time.sleep(1)
            except Exception as e:
                print(f"   ❌ 填写失败: {e}")
        else:
            print("   ❌ 未找到密码输入框！")
        
        screenshot(page, "06_password_filled")
        
        # =====================================================================
        # 步骤7: 点击连接按钮
        # =====================================================================
        print("\n[7/12] 查找并点击连接按钮...")
        
        # 重新获取所有按钮（页面可能已变化）
        buttons = page.query_selector_all("button")
        print(f"   📊 找到 {len(buttons)} 个button")
        
        for i, btn in enumerate(buttons):
            try:
                t = btn.inner_text()
                print(f"      [{i}] '{t}'")
            except:
                pass
        
        # 查找连接按钮
        connect_btn = None
        for btn in buttons:
            try:
                t = btn.inner_text()
                if t and any(kw in t for kw in ["连接", "Connect", "测试"]):
                    connect_btn = btn
                    print(f"   ✅ 找到连接按钮: '{t}'")
                    break
            except:
                pass
        
        if connect_btn:
            try:
                connect_btn.click()
                print("   ✅ 已点击连接按钮")
                time.sleep(10)  # 等待认证响应
            except Exception as e:
                print(f"   ❌ 点击失败: {e}")
        else:
            print("   ❌ 未找到连接按钮！")
        
        screenshot(page, "07_after_connect")
        
        # =====================================================================
        # 步骤8: 观察认证结果
        # =====================================================================
        print("\n[8/12] 观察认证结果...")
        
        text = page.inner_text("body")
        print(f"   📝 页面文本（前600字符）:\n{text[:600]}")
        
        if "成功" in text or "connected" in text.lower():
            print("   ✅ 认证成功！")
        elif "失败" in text or "error" in text.lower():
            print("   ❌ 认证失败！")
        else:
            print("   ⚠️  认证状态不明确")
        
        screenshot(page, "08_auth_result")
        
        # =====================================================================
        # 步骤9-12: 后续流程（如果认证成功）
        # =====================================================================
        print("\n[9/12+] 继续执行后续流程...")
        
        # 这里可以添加：
        # - 导航至生产模块
        # - 开始生成Alpha
        # - 评分验证
        # - 提交Alpha
        
        print("   ⚠️  后续步骤需要根据实际页面动态调整")
        print("   💡 建议：手动完成后续流程并观察")
        
        screenshot(page, "09_final")
        
        # =====================================================================
        # 完成
        # =====================================================================
        print("\n" + "=" * 70)
        print("📊 测试执行总结")
        print("=" * 70)
        print(f"\n✅ 完成时间: {time.strftime('%H:%M:%S')}")
        print(f"✅ 最终URL: {page.url}")
        print(f"✅ 截图已保存至: {OUTPUT}/")
        
        print("\n📸 截图清单:")
        print("   - 01_initial.png")
        print("   - 02_after_clear.png")
        print("   - 03_section_expanded.png")
        print("   - 04_form_visible.png")
        print("   - 05_email_filled.png")
        print("   - 06_password_filled.png")
        print("   - 07_after_connect.png")
        print("   - 08_auth_result.png")
        print("   - 09_final.png")
        
        print("\n" + "=" * 70)
        print("⏸️  浏览器将保持打开60秒，便于观察...")
        time.sleep(60)
        browser.close()
        print("\n✅ 测试完成！")
        print("=" * 70)

if __name__ == "__main__":
    main()
