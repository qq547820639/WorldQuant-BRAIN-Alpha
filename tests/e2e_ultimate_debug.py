"""
BRAIN Alpha Ops - 终极调试脚本

目标：
1. 获取完整的页面HTML
2. 查找登录表单的真实位置
3. 检查是否有iframe或Shadow DOM
4. 找到真正的登录表单并填写
"""

from playwright.sync_api import sync_playwright
import time
import os
import re

EMAIL = os.environ.get("BRAIN_USERNAME", "")
PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
URL = "http://127.0.0.1:8765"
OUTPUT = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/ultimate_debug"

def screenshot(page, name):
    os.makedirs(OUTPUT, exist_ok=True)
    path = f"{OUTPUT}/{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"   📸 {name}.png")

def main():
    print("=" * 70)
    print("🔬 BRAIN Alpha Ops - 终极调试脚本")
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
        print("\n[1/15] 访问页面...")
        page.goto(URL)
        time.sleep(10)  # 等待React完全渲染
        screenshot(page, "01_initial")
        
        # =====================================================================
        # 步骤2: 清除存储
        # =====================================================================
        print("\n[2/15] 清除存储...")
        page.evaluate("localStorage.clear()")
        page.evaluate("sessionStorage.clear()")
        page.context.clear_cookies()
        page.reload()
        time.sleep(10)
        screenshot(page, "02_after_clear")
        print("   ✅ 存储已清除")
        
        # =====================================================================
        # 步骤3: 获取完整的页面HTML
        # =====================================================================
        print("\n[3/15] 获取完整的页面HTML...")
        html = page.content()
        html_path = f"{OUTPUT}/page_html.html"
        os.makedirs(OUTPUT, exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"   ✅ HTML已保存: {html_path}")
        print(f"   📊 HTML大小: {len(html)} 字符")
        
        # 在HTML中查找input标签
        input_matches = re.findall(r'<input[^>]*>', html)
        print(f"   📝 在HTML中找到 {len(input_matches)} 个 <input> 标签")
        for i, match in enumerate(input_matches[:10]):
            print(f"      [{i}] {match}")
        
        # 在HTML中查找"账户邮箱"
        if "账户邮箱" in html:
            print("   ✅ HTML中包含 '账户邮箱'")
            # 找到上下文
            idx = html.find("账户邮箱")
            print(f"   📍 位置: {idx}")
            print(f"   📄 上下文: ...{html[max(0,idx-100):idx+100]}...")
        
        # =====================================================================
        # 步骤4: 检查iframe
        # =====================================================================
        print("\n[4/15] 检查iframe...")
        frames = page.frames
        print(f"   📊 页面共有 {len(frames)} 个frame")
        for i, frame in enumerate(frames):
            print(f"   🖼️  Frame [{i}]: {frame.url} (name: {frame.name})")
        
            # 在每个frame中查找input
            try:
                frame_inputs = frame.query_selector_all("input")
                if frame_inputs:
                    print(f"      ✅ 在此frame中找到 {len(frame_inputs)} 个input!")
                    for j, inp in enumerate(frame_inputs):
                        try:
                            t = inp.get_attribute("type") or "text"
                            p = inp.get_attribute("placeholder") or ""
                            print(f"         [{j}] type={t}, placeholder='{p}'")
                        except:
                            pass
            except:
                pass
        
        # =====================================================================
        # 步骤5: 检查Shadow DOM
        # =====================================================================
        print("\n[5/15] 检查Shadow DOM...")
        shadow_elements = page.evaluate("""
            () => {
                const results = [];
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_ELEMENT,
                    null,
                    false
                );
                
                let node;
                while (node = walker.nextNode()) {
                    if (node.shadowRoot) {
                        results.push({
                            tag: node.tagName,
                            id: node.id,
                            class: node.className,
                            shadowHTML: node.shadowRoot.innerHTML.substring(0, 200)
                        });
                    }
                }
                return results;
            }
        """)
        
        if shadow_elements:
            print(f"   ✅ 找到 {len(shadow_elements)} 个Shadow DOM元素")
            for elem in shadow_elements:
                print(f"      - <{elem['tag']}> id={elem['id']} class={elem['class']}")
                # 在shadow DOM中查找input
                # （这需要更复杂的处理）
        else:
            print("   ⚠️  未找到Shadow DOM元素")
        
        # =====================================================================
        # 步骤6: 使用Playwright的locator API（更强大）
        # =====================================================================
        print("\n[6/15] 使用locator API查找元素...")
        
        # 方式1: 通过文本查找（不区分可见性）
        print("   🔍 查找包含'账户邮箱'的元素...")
        elem = page.locator("text=账户邮箱").first
        if elem.count() > 0:
            print("   ✅ 找到包含'账户邮箱'的元素")
            # 获取这个元素的HTML
            try:
                parent_html = elem.evaluate("el => el.outerHTML")
                print(f"   📄 父元素HTML: {parent_html[:200]}")
            except:
                pass
        
        # 方式2: 通过placeholder查找
        print("   🔍 查找placeholder包含'邮箱'的input...")
        email_input = page.locator("input[placeholder*='邮箱']").first
        if email_input.count() > 0:
            print("   ✅ 找到邮箱输入框（通过placeholder）")
        
        # 方式3: 通过name属性查找
        print("   🔍 查找name='email'或name='username'的input...")
        for name in ["email", "username", "account", "邮箱"]:
            inp = page.locator(f"input[name*='{name}']").first
            if inp.count() > 0:
                print(f"   ✅ 找到input (name='{name}')")
        
        screenshot(page, "03_locator_api")
        
        # =====================================================================
        # 步骤7: 尝试点击"准备"按钮（可能展开表单）
        # =====================================================================
        print("\n[7/15] 尝试点击'准备'按钮...")
        
        prepare_btn = page.locator("button:has-text('准备')").first
        if prepare_btn.count() > 0:
            print("   🖱️ 点击'准备'按钮...")
            prepare_btn.click()
            time.sleep(5)
            screenshot(page, "04_after_click_prepare")
            
            # 再次查找input
            inputs = page.query_selector_all("input")
            print(f"   📊 点击后找到 {len(inputs)} 个input")
        
        # =====================================================================
        # 步骤8: 尝试点击"1. 账户/缓存"（可能是可点击的step）
        # =====================================================================
        print("\n[8/15] 尝试点击'1. 账户/缓存'...")
        
        # 查找包含"1."的元素
        step1 = page.locator("text=1.").first
        if step1.count() > 0:
            print("   🖱️ 点击'1.'...")
            try:
                step1.click()
                time.sleep(5)
                screenshot(page, "05_after_click_step1")
                
                # 再次查找input
                inputs = page.query_selector_all("input")
                print(f"   📊 点击后找到 {len(inputs)} 个input")
            except Exception as e:
                print(f"   ⚠️  点击失败: {e}")
        
        # =====================================================================
        # 步骤9: 查找所有表单相关的元素
        # =====================================================================
        print("\n[9/15] 查找所有表单相关元素...")
        
        form_elements = page.evaluate("""
            () => {
                const elements = [];
                
                // 查找所有input
                document.querySelectorAll('input').forEach((inp, i) => {
                    elements.push({
                        type: 'input',
                        index: i,
                        inputType: inp.type,
                        placeholder: inp.placeholder,
                        name: inp.name,
                        id: inp.id,
                        className: inp.className,
                        visible: inp.offsetParent !== null,
                        value: inp.value
                    });
                });
                
                // 查找所有button
                document.querySelectorAll('button').forEach((btn, i) => {
                    elements.push({
                        type: 'button',
                        index: i,
                        text: btn.innerText,
                        className: btn.className,
                        visible: btn.offsetParent !== null
                    });
                });
                
                return elements;
            }
        """)
        
        print(f"   📊 找到 {len(form_elements)} 个表单相关元素:")
        for elem in form_elements:
            if elem['type'] == 'input':
                print(f"      [input {elem['index']}] type={elem['inputType']}, placeholder='{elem['placeholder']}', visible={elem['visible']}")
            else:
                print(f"      [button {elem['index']}] text='{elem['text']}', visible={elem['visible']}")
        
        # 保存为JSON
        import json
        with open(f"{OUTPUT}/form_elements.json", "w", encoding="utf-8") as f:
            json.dump(form_elements, f, indent=2, ensure_ascii=False)
        print(f"   ✅ 表单元素已保存: {OUTPUT}/form_elements.json")
        
        # =====================================================================
        # 步骤10-15: 如果找到了input，尝试填写
        # =====================================================================
        
        inputs = [e for e in form_elements if e['type'] == 'input']
        
        if len(inputs) >= 2:
            print(f"\n[10/15] 找到 {len(inputs)} 个input，尝试填写...")
            
            # 找到邮箱和密码输入框
            email_input = None
            password_input = None
            
            for inp in inputs:
                if inp['inputType'] == 'email' or 'email' in inp.get('name', '').lower() or '邮箱' in inp.get('placeholder', ''):
                    email_input = inp
                if inp['inputType'] == 'password' or 'password' in inp.get('name', '').lower() or '密码' in inp.get('placeholder', ''):
                    password_input = inp
            
            if email_input:
                print(f"   ✅ 找到邮箱输入框 (index={email_input['index']})")
                # 通过JavaScript填写
                page.evaluate(f"""
                    () => {{
                        const inputs = document.querySelectorAll('input');
                        inputs[{email_input['index']}].value = '{EMAIL}';
                        inputs[{email_input['index']}].dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                """)
                print(f"   ✅ 邮箱已填写: {EMAIL}")
                time.sleep(1)
            
            if password_input:
                print(f"   ✅ 找到密码输入框 (index={password_input['index']})")
                # 通过JavaScript填写
                page.evaluate(f"""
                    () => {{
                        const inputs = document.querySelectorAll('input');
                        inputs[{password_input['index']}].value = '{PASSWORD}';
                        inputs[{password_input['index']}].dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                """)
                print("   ✅ 密码已填写")
                time.sleep(1)
            
            screenshot(page, "06_form_filled")
            
            # 查找并点击连接按钮
            print("\n[11/15] 查找连接按钮...")
            buttons = [e for e in form_elements if e['type'] == 'button']
            for btn in buttons:
                if '连接' in btn['text'] or 'Connect' in btn['text'] or '测试' in btn['text']:
                    print(f"   🖱️ 点击按钮: '{btn['text']}'")
                    try:
                        page.evaluate(f"""
                            () => {{
                                const buttons = document.querySelectorAll('button');
                                buttons[{btn['index']}].click();
                            }}
                        """)
                        print("   ✅ 已点击连接按钮")
                        break
                    except Exception as e:
                        print(f"   ⚠️  点击失败: {e}")
            
            time.sleep(10)
            screenshot(page, "07_after_connect")
            
            # 观察结果
            print("\n[12/15] 观察认证结果...")
            text = page.inner_text("body")
            print(f"   📝 页面文本（前500字符）:\n{text[:500]}")
        
        # =====================================================================
        # 完成
        # =====================================================================
        print("\n" + "=" * 70)
        print("📊 调试完成")
        print("=" * 70)
        print(f"\n✅ 完成时间: {time.strftime('%H:%M:%S')}")
        print(f"✅ 所有输出已保存至: {OUTPUT}/")
        print("\n📸 截图清单:")
        print("   - 01_initial.png")
        print("   - 02_after_clear.png")
        print("   - 03_locator_api.png")
        print("   - 04_after_click_prepare.png")
        print("   - 05_after_click_step1.png")
        print("   - 06_form_filled.png")
        print("   - 07_after_connect.png")
        
        print("\n⏸️  浏览器将保持打开60秒...")
        time.sleep(60)
        browser.close()
        
        print("\n✅ 调试脚本执行完成！")
        print("=" * 70)

if __name__ == "__main__":
    main()
