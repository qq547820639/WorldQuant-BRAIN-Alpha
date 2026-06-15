"""
深度UI探索脚本 - 查找BRAIN Alpha Ops的真实登录入口和交互元素

探索目标：
1. 检查当前认证状态
2. 查找隐藏的登录表单（模态框、对话框）
3. 查找登出/切换账户功能
4. 获取完整的页面DOM结构
5. 识别所有可交互元素
"""

from playwright.sync_api import sync_playwright
import time
import json
import os

OUTPUT_DIR = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output"
SCREENSHOT_DIR = f"{OUTPUT_DIR}/ui_exploration"

def log(msg):
    """打印日志"""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")

def take_screenshot(page, name):
    """保存截图"""
    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        path = f"{SCREENSHOT_DIR}/{name}.png"
        page.screenshot(path=path, full_page=True)
        log(f"📸 截图已保存: {path}")
    except Exception as e:
        log(f"⚠️ 截图失败: {e}")

def explore_page_structure(page):
    """深度探索页面结构"""
    log("=" * 80)
    log("🔬 开始深度探索页面结构")
    log("=" * 80)
    
    # =====================================================================
    # 1. 获取页面基本信息
    # =====================================================================
    log("\n📍 步骤1: 获取页面基本信息")
    
    url = page.url
    title = page.title()
    
    log(f"   URL: {url}")
    log(f"   标题: {title}")
    
    # =====================================================================
    # 2. 获取完整的可访问性树
    # =====================================================================
    log("\n📍 步骤2: 获取完整的可访问性树")
    
    try:
        # 获取页面的完整可访问性树
        accessibility_tree = page.accessibility.snapshot()
        log(f"   ✅ 可访问性树已获取")
        
        # 保存到文件（格式化JSON）
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(f"{OUTPUT_DIR}/accessibility_tree.json", "w", encoding="utf-8") as f:
            json.dump(accessibility_tree, f, indent=2, ensure_ascii=False)
        log(f"   ✅ 可访问性树已保存至: {OUTPUT_DIR}/accessibility_tree.json")
    except Exception as e:
        log(f"   ⚠️ 获取可访问性树失败: {e}")
    
    # =====================================================================
    # 3. 查找所有可交互元素
    # =====================================================================
    log("\n📍 步骤3: 查找所有可交互元素")
    
    # 查找所有按钮
    buttons = page.locator("button").all()
    log(f"   ✅ 发现 {len(buttons)} 个 <button> 元素")
    
    button_info = []
    for i, btn in enumerate(buttons):
        try:
            text = btn.text_content()
            is_visible = btn.is_visible()
            is_enabled = btn.is_enabled()
            button_info.append({
                "index": i,
                "text": text.strip() if text else "(无文本)",
                "visible": is_visible,
                "enabled": is_enabled
            })
            if text and text.strip() and is_visible:
                log(f"      [{i}] '{text.strip()}' (可见:{is_visible}, 启用:{is_enabled})")
        except Exception as e:
            log(f"      [{i}] ❌ 无法读取: {e}")
    
    # 查找所有输入框
    inputs = page.locator("input").all()
    log(f"   ✅ 发现 {len(inputs)} 个 <input> 元素")
    
    input_info = []
    for i, inp in enumerate(inputs):
        try:
            input_type = inp.get_attribute("type") or "text"
            placeholder = inp.get_attribute("placeholder") or ""
            is_visible = inp.is_visible()
            input_info.append({
                "index": i,
                "type": input_type,
                "placeholder": placeholder,
                "visible": is_visible
            })
            if is_visible:
                log(f"      [{i}] type={input_type}, placeholder='{placeholder}' (可见:{is_visible})")
        except Exception as e:
            log(f"      [{i}] ❌ 无法读取: {e}")
    
    # 查找所有链接
    links = page.locator("a").all()
    log(f"   ✅ 发现 {len(links)} 个 <a> 链接")
    
    link_info = []
    for i, link in enumerate(links[:20]):  # 只显示前20个
        try:
            text = link.text_content()
            href = link.get_attribute("href")
            is_visible = link.is_visible()
            link_info.append({
                "index": i,
                "text": text.strip() if text else "(无文本)",
                "href": href,
                "visible": is_visible
            })
            if text and text.strip() and is_visible:
                log(f"      [{i}] '{text.strip()}' -> {href}")
        except Exception as e:
            pass
    
    # =====================================================================
    # 4. 查找模态框、对话框、下拉菜单
    # =====================================================================
    log("\n📍 步骤4: 查找模态框、对话框、下拉菜单")
    
    # 常见的模态框/对话框选择器
    modal_selectors = [
        "[role='dialog']",
        "[role='modal']",
        ".modal",
        ".dialog",
        ".popup",
        "[class*='modal']",
        "[class*='dialog']",
        "[class*='popup']",
        "div[style*='display: block']",
        "div[style*='visibility: visible']"
    ]
    
    for selector in modal_selectors:
        try:
            elements = page.locator(selector).all()
            visible_elements = [e for e in elements if e.is_visible()]
            if visible_elements:
                log(f"   ✅ 找到 {len(visible_elements)} 个可见的 '{selector}' 元素")
        except:
            pass
    
    # =====================================================================
    # 5. 检查页面文本内容（判断认证状态）
    # =====================================================================
    log("\n📍 步骤5: 检查页面文本内容（判断认证状态）")
    
    page_text = page.inner_text("body")
    
    # 检查认证相关关键词
    auth_keywords = {
        "已认证": ["已认证", "认证成功", "connected", "authenticated"],
        "未认证": ["未认证", "请登录", "请连接", "login", "connect"],
        "凭证": ["凭证", "凭据", "credential"],
        "账户": ["账户", "account", "profile"]
    }
    
    for category, keywords in auth_keywords.items():
        found = [kw for kw in keywords if kw in page_text.lower()]
        if found:
            log(f"   📝 {category}: 发现关键词 {found}")
    
    # =====================================================================
    # 6. 尝试查找"登出"或"切换账户"按钮
    # =====================================================================
    log("\n📍 步骤6: 查找'登出'或'切换账户'按钮")
    
    logout_keywords = ["登出", "退出", "Logout", "Sign Out", "切换账户", "Switch Account", "更换", "Change"]
    
    for keyword in logout_keywords:
        try:
            elem = page.get_by_text(keyword, exact=False)
            if elem.count() > 0:
                log(f"   ✅ 找到包含 '{keyword}' 的元素")
                # 尝试点击（可能会打开一个菜单或对话框）
                try:
                    elem.first.click()
                    log(f"   ✅ 已点击 '{keyword}'")
                    time.sleep(2)
                    take_screenshot(page, f"after_click_{keyword}")
                    break
                except Exception as e:
                    log(f"   ⚠️ 点击 '{keyword}' 失败: {e}")
        except Exception as e:
            pass
    
    # =====================================================================
    # 7. 如果已认证，尝试清除会话并重新访问
    # =====================================================================
    log("\n📍 步骤7: 检查是否需要清除会话重新登录")
    
    # 检查是否有"凭证与账户"相关的绿色勾选标记
    if "凭证与账户" in page_text or "connected" in page_text.lower():
        log("   ⚠️ 检测到可能已认证状态")
        log("   💡 建议: 清除浏览器存储并刷新页面以测试登录流程")
        
        # 尝试清除localStorage和sessionStorage
        log("   🧹 正在清除浏览器存储...")
        page.evaluate("localStorage.clear()")
        page.evaluate("sessionStorage.clear()")
        log("   ✅ 已清除 localStorage 和 sessionStorage")
        
        # 刷新页面
        log("   🔄 正在刷新页面...")
        page.reload(wait_until="networkidle")
        time.sleep(3)
        log("   ✅ 页面已刷新")
        
        take_screenshot(page, "after_storage_clear")
    
    # =====================================================================
    # 8. 再次检查页面状态（清除存储后）
    # =====================================================================
    log("\n📍 步骤8: 再次检查页面状态（清除存储后）")
    
    # 重新获取页面文本
    page_text_after = page.inner_text("body")
    
    # 检查是否出现登录表单
    has_email_input = page.locator("input[type='email'], input[placeholder*='email'], input[placeholder*='邮箱']").count() > 0
    has_password_input = page.locator("input[type='password']").count() > 0
    
    log(f"   📝 邮箱输入框存在: {has_email_input}")
    log(f"   📝 密码输入框存在: {has_password_input}")
    
    if has_email_input and has_password_input:
        log("   ✅ 登录表单已出现！")
    else:
        log("   ⚠️ 登录表单仍未出现，可能需要点击某个按钮触发")
        
        # 查找可能触发登录表单的按钮
        all_buttons = page.locator("button").all()
        for i, btn in enumerate(all_buttons):
            try:
                text = btn.text_content()
                if text and any(kw in text.lower() for kw in ["连接", "登录", "connect", "login", "认证", "auth"]):
                    log(f"   💡 可能触发登录的按钮 [{i}]: '{text.strip()}'")
            except:
                pass
    
    # =====================================================================
    # 9. 保存探索结果
    # =====================================================================
    log("\n📍 步骤9: 保存探索结果")
    
    exploration_result = {
        "url": url,
        "title": title,
        "buttons": button_info,
        "inputs": input_info,
        "links": link_info[:20],  # 只保存前20个
        "has_email_input": has_email_input,
        "has_password_input": has_password_input,
        "page_text_length": len(page_text)
    }
    
    with open(f"{OUTPUT_DIR}/ui_exploration_result.json", "w", encoding="utf-8") as f:
        json.dump(exploration_result, f, indent=2, ensure_ascii=False)
    
    log(f"   ✅ 探索结果已保存至: {OUTPUT_DIR}/ui_exploration_result.json")
    
    # =====================================================================
    # 10. 最终截图
    # =====================================================================
    log("\n📍 步骤10: 最终截图")
    take_screenshot(page, "final_exploration")
    
    log("\n" + "=" * 80)
    log("✅ 深度探索完成！")
    log("=" * 80)
    
    return exploration_result


def main():
    """主函数"""
    log("🚀 启动深度UI探索...")
    
    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(
            headless=False,
            slow_mo=500,
            args=['--window-size=1920,1080']
        )
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.new_page()
        
        # 访问目标URL - 使用更可靠的等待策略
        log(f"\n🌐 正在访问: http://127.0.0.1:8765")
        try:
            # 先尝试简单的页面加载（不等待networkidle）
            page.goto("http://127.0.0.1:8765", timeout=10000)
            log("   ✅ 页面初始加载完成")
            
            # 等待页面稳定（等待特定元素出现）
            log("   ⏳ 等待页面稳定（最多30秒）...")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)  # 额外等待React渲染
            log("   ✅ 页面已稳定")
        except Exception as e:
            log(f"   ⚠️ 页面加载超时: {e}")
            log("   💡 尝试继续（可能页面已部分加载）...")
        
        take_screenshot(page, "01_initial_visit")
        
        # 执行深度探索
        result = explore_page_structure(page)
        
        # 保持浏览器打开一段时间
        log("\n⏸️ 浏览器将保持打开15秒，便于观察...")
        time.sleep(15)
        
        # 关闭浏览器
        browser.close()
        
        log("\n✅ 深度探索脚本执行完成！")
        
        return result


if __name__ == "__main__":
    main()
