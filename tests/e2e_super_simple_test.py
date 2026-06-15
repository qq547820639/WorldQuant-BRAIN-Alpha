"""
BRAIN Alpha Ops - 超简单UI测试脚本

极简设计：
1. 直接使用简单的选择器
2. 使用固定的等待时间（不使用复杂的wait_for）
3. 每步都截图
4. 详细打印日志
"""

from playwright.sync_api import sync_playwright
import time
import os

# 配置
EMAIL = os.environ.get("BRAIN_USERNAME", "")
PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
URL = "http://127.0.0.1:8765"
OUTPUT = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/simple_test"

def screenshot(page, name):
    """保存截图"""
    os.makedirs(OUTPUT, exist_ok=True)
    path = f"{OUTPUT}/{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"   📸 {name}.png")

def main():
    print("=" * 70)
    print("🧪 BRAIN Alpha Ops - 超简单UI测试")
    print("=" * 70)
    print(f"开始时间: {time.strftime('%H:%M:%S')}")
    print("=" * 70)
    
    with sync_playwright() as p:
        # 启动浏览器
        print("\n[1/10] 启动浏览器...")
        browser = p.chromium.launch(
            headless=False,
            args=['--window-size=1600,900']
        )
        page = browser.new_page(viewport={'width': 1600, 'height': 900})
        
        # 步骤1: 访问页面
        print("\n[2/10] 访问页面...")
        page.goto(URL)
        time.sleep(8)  # 等待React渲染
        screenshot(page, "01_initial")
        print(f"   ✅ 标题: {page.title()}")
        print(f"   ✅ URL: {page.url}")
        
        # 步骤2: 清除存储
        print("\n[3/10] 清除浏览器存储...")
        page.evaluate("localStorage.clear()")
        page.evaluate("sessionStorage.clear()")
        page.reload()
        time.sleep(8)
        screenshot(page, "02_after_clear")
        print("   ✅ 存储已清除，页面已刷新")
        
        # 步骤3: 打印页面所有文本（调试）
        print("\n[4/10] 获取页面文本（前800字符）...")
        text = page.inner_text("body")
        print(f"   📝 页面文本:\n{text[:800]}")
        screenshot(page, "03_page_text")
        
        # 步骤4: 查找所有input
        print("\n[5/10] 查找所有input元素...")
        inputs = page.query_selector_all("input")
        print(f"   ✅ 找到 {len(inputs)} 个input")
        for i, inp in enumerate(inputs):
            try:
                t = inp.get_attribute("type") or "text"
                p = inp.get_attribute("placeholder") or ""
                print(f"      [{i}] type={t}, placeholder='{p}'")
            except:
                pass
        screenshot(page, "04_inputs")
        
        # 步骤5: 查找所有button
        print("\n[6/10] 查找所有button元素...")
        buttons = page.query_selector_all("button")
        print(f"   ✅ 找到 {len(buttons)} 个button")
        for i, btn in enumerate(buttons):
            try:
                t = btn.inner_text()
                print(f"      [{i}] '{t}'")
            except:
                pass
        screenshot(page, "05_buttons")
        
        # 步骤6: 尝试填写表单
        print("\n[7/10] 尝试填写登录表单...")
        if len(inputs) >= 2:
            try:
                inputs[0].fill(EMAIL)
                print(f"   ✅ 输入框[0] 已填写: {EMAIL}")
                time.sleep(1)
                inputs[1].fill(PASSWORD)
                print("   ✅ 输入框[1] 已填写密码")
                time.sleep(1)
                screenshot(page, "06_form_filled")
            except Exception as e:
                print(f"   ❌ 填写失败: {e}")
        else:
            print(f"   ⚠️  input数量不足: {len(inputs)}")
            print("   💡 尝试点击按钮展开表单...")
            # 尝试点击包含"准备"或"连接"的按钮
            for btn in buttons:
                try:
                    t = btn.inner_text()
                    if "准备" in t or "连接" in t or "Connect" in t:
                        print(f"   🖱️ 点击按钮: '{t}'")
                        btn.click()
                        time.sleep(3)
                        screenshot(page, "06_clicked_" + t[:5])
                        break
                except:
                    pass
        
        # 步骤7: 点击连接按钮
        print("\n[8/10] 点击连接按钮...")
        buttons_new = page.query_selector_all("button")
        for btn in buttons_new:
            try:
                t = btn.inner_text()
                if "连接" in t or "Connect" in t or "测试" in t:
                    print(f"   🖱️ 点击: '{t}'")
                    btn.click()
                    time.sleep(10)
                    screenshot(page, "07_after_connect")
                    break
            except:
                pass
        
        # 步骤8: 观察结果
        print("\n[9/10] 观察认证结果...")
        text_after = page.inner_text("body")
        print(f"   📝 页面文本（前500字符）:\n{text_after[:500]}")
        screenshot(page, "08_result")
        
        # 步骤9: 保持浏览器打开
        print("\n[10/10] 测试完成，保持浏览器打开30秒...")
        print(f"完成时间: {time.strftime('%H:%M:%S')}")
        print("=" * 70)
        print(f"\n📸 所有截图已保存至: {OUTPUT}/")
        print("\n" + "=" * 70)
        
        time.sleep(30)
        browser.close()

if __name__ == "__main__":
    main()
