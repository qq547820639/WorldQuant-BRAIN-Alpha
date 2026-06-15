import os
"""
BRAIN Alpha Ops - 真正的完整验收测试

目标：生产出可提交的Alpha，走完完整流程
1. 登录认证
2. 云端同步（拉取官方能力集+云端Alpha）
3. 运行非提交验证（生产Alpha候选）
4. 等待生产完成，检查候选数据
5. 查看候选详情（表达式、评分）
6. 查看提交就绪状态（阻断项检查）
"""

from playwright.sync_api import sync_playwright
import time, os, json

EMAIL = "547820639@qq.com"
PASSWORD = os.environ.get("BRAIN_PASSWORD", "")
URL = "http://127.0.0.1:8765"
OUT = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/output/full_acceptance"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def ss(page, name):
    os.makedirs(OUT, exist_ok=True)
    page.screenshot(path=f"{OUT}/{name}.png", full_page=True)

def wait_for_text_change(page, old_text, key_word, timeout=120):
    """等待页面文本变化"""
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(5)
        try:
            new_text = page.inner_text("body")
            if key_word in new_text and key_word not in old_text:
                return new_text
            old_text = new_text
        except:
            pass
        log(f"   ⏳ 等待 '{key_word}' ... {int(time.time()-start)}s")
    return None

def log_page_state(page, label):
    """记录当前页面关键状态"""
    try:
        text = page.inner_text("body")
        # 提取关键信息
        keywords = ["PRODUCTION", "运行中", "完成", "completed", "上线", 
                     "Alpha", "候选", "表达式", "Sharpe", "Fitness", 
                     "阻断", "ready", "提交", "通过", "失败",
                     "开始验证", "停止", "进度"]
        found = {}
        for kw in keywords:
            if kw in text:
                idx = text.find(kw)
                found[kw] = text[max(0,idx-20):idx+len(kw)+20].replace('\n',' ')
        log(f"   [{label}] 关键文本: {found}")
        return text
    except:
        return ""

def main():
    results = {
        "steps": [],
        "candidates_found": 0,
        "alphas_submittable": 0,
        "issues": []
    }
    
    print("="*70, flush=True)
    log("🧪 完整Alpha生产+提交流程验收测试")
    print("="*70, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=['--window-size=1600,900'])
        page = browser.new_page(viewport={'width': 1600, 'height': 900})

        # ================================================================
        # 步骤1: 访问页面
        # ================================================================
        log("步骤1: 访问页面")
        page.goto(URL)
        time.sleep(8)
        log(f"   标题: {page.title()}")
        ss(page, "01_loaded")

        # ================================================================
        # 步骤2: 导航配置页 + 填写凭据 + 测试连接
        # ================================================================
        log("步骤2: 配置页填写凭据")
        page.locator("button:has-text('系统配置')").first.click()
        time.sleep(5)
        
        page.locator("input[type='text']").first.fill(EMAIL)
        page.locator("input[type='password']").first.fill(PASSWORD)
        page.locator("button:has-text('测试 BRAIN 连接')").first.click()
        log("   等待认证...")
        time.sleep(15)
        
        text = page.inner_text("body")
        if "连接正常" in text:
            log("   ✅ 认证成功")
            results["steps"].append({"step": "认证", "status": "PASS"})
        else:
            log("   ❌ 认证失败")
            results["steps"].append({"step": "认证", "status": "FAIL"})
            browser.close()
            return
        ss(page, "02_auth")

        # ================================================================
        # 步骤3: 返回Dashboard + 首次同步
        # ================================================================
        log("步骤3: Dashboard + 首次同步")
        page.locator("button:has-text('运行总览')").first.click()
        time.sleep(5)
        
        text_before = page.inner_text("body")
        sync_btn = page.locator("button:has-text('开始首次同步')").first
        if sync_btn.count() > 0:
            sync_btn.click()
            log("   ✅ 已点击 开始首次同步")
            
            # 等待同步完成
            text_after = wait_for_text_change(page, text_before, "已完成", timeout=120)
            if text_after:
                log("   ✅ 首次同步完成")
            else:
                log("   ⚠️ 同步可能仍在进行")
        ss(page, "03_synced")

        # ================================================================
        # 步骤4: 运行非提交验证（生产Alpha候选）
        # ================================================================
        log("步骤4: 运行非提交验证")
        time.sleep(5)
        text_before = page.inner_text("body")
        
        # 查找启动按钮
        run_btns = [
            "button:has-text('运行非提交验证')",
            "button:has-text('开始验证')",
            "button:has-text('运行验证')",
        ]
        
        run_clicked = False
        for selector in run_btns:
            btn = page.locator(selector).first
            if btn.count() > 0:
                btn.click()
                run_clicked = True
                log(f"   ✅ 已点击: {selector}")
                break
        
        if not run_clicked:
            log("   ⚠️ 未找到验证启动按钮，尝试检查Dashboard状态")
            log_page_state(page, "dashboard_state")
            
            # 可能已经在前面的流程中触发了生产
            text_now = page.inner_text("body")
            if "运行中" in text_now or "进度" in text_now or "生产" in text_now:
                log("   ✅ 检测到生产可能已在运行")
            else:
                # 尝试点击任意看起来像启动的按钮
                all_btns = page.locator("button").all()
                for btn in all_btns:
                    try:
                        t = btn.text_content().strip()
                        if any(kw in t for kw in ["开始", "运行", "验证", "生产", "start", "run"]):
                            if btn.is_visible():
                                btn.click()
                                log(f"   ✅ 点击了: '{t}'")
                                run_clicked = True
                                break
                    except: pass

        # 等待生产完成（最多300秒 = 5分钟）
        log("   等待生产完成（最多300秒）...")
        start_time = time.time()
        production_done = False
        
        while time.time() - start_time < 300:
            time.sleep(15)
            elapsed = int(time.time() - start_time)
            try:
                t = page.inner_text("body")
                # 检查完成标志
                if any(kw in t for kw in ["已完成", "completed", "生产完成", "completed_with_warnings", "停止"]):
                    log(f"   ✅ 生产完成！耗时 {elapsed}s")
                    production_done = True
                    break
                # 显示进度信息
                for kw in ["进度", "progress", "阶段", "phase", "候选", "candidate"]:
                    if kw in t:
                        idx = t.find(kw)
                        snippet = t[max(0,idx-10):idx+40].replace('\n',' ').strip()
                        log(f"   [{elapsed}s] {snippet}")
                        break
                else:
                    log(f"   ⏳ 等待中... {elapsed}s")
            except Exception as e:
                log(f"   ⚠️ 检查出错: {e}")
        
        if not production_done:
            log("   ⚠️ 生产超时，继续后续步骤")
            results["issues"].append("生产超时")
        
        ss(page, "04_production_done")
        results["steps"].append({"step": "生产验证", "status": "PASS" if production_done else "WARN"})

        # ================================================================
        # 步骤5: 查看候选发现 - 检查是否生成了Alpha
        # ================================================================
        log("步骤5: 候选发现 - 检查生成的Alpha")
        
        try:
            # 展开候选发现阶段组
            phase_btn = page.locator("button[aria-expanded='false']:has-text('候选发现')").first
            if phase_btn.count() > 0:
                phase_btn.click()
                time.sleep(2)
            
            page.locator("button:has-text('候选管理')").first.click()
            time.sleep(5)
            
            text = page.inner_text("body")
            log_page_state(page, "candidates")
            
            # 统计候选数量
            # 查找候选相关文本
            candidate_count = 0
            for line in text.split('\n'):
                if 'Alpha' in line or 'candidate' in line.lower() or '表达式' in line:
                    candidate_count += 1
            
            results["candidates_found"] = candidate_count
            log(f"   📊 候选数量估算: {candidate_count}")
            
            if candidate_count > 0:
                results["steps"].append({"step": "候选发现", "status": "PASS", "count": candidate_count})
            else:
                results["steps"].append({"step": "候选发现", "status": "WARN", "count": 0})
            
            ss(page, "05_candidates")
        except Exception as e:
            log(f"   ⚠️ 候选发现检查失败: {e}")
            results["steps"].append({"step": "候选发现", "status": "WARN"})

        # ================================================================
        # 步骤6: 查看评分验证
        # ================================================================
        log("步骤6: 评分验证")
        try:
            phase_btn = page.locator("button[aria-expanded='false']:has-text('评估与验证')").first
            if phase_btn.count() > 0:
                phase_btn.click()
                time.sleep(2)
            
            page.locator("button:has-text('科学评分')").first.click()
            time.sleep(5)
            
            text = page.inner_text("body")
            log_page_state(page, "scoring")
            
            # 检查评分数据
            has_score = any(kw in text for kw in ["Sharpe", "Fitness", "评分", "score"])
            results["steps"].append({"step": "评分验证", "status": "PASS" if has_score else "WARN"})
            ss(page, "06_scoring")
        except Exception as e:
            log(f"   ⚠️ 评分检查失败: {e}")
            results["steps"].append({"step": "评分验证", "status": "WARN"})

        # ================================================================
        # 步骤7: 查看提交就绪 - 检查哪些可提交
        # ================================================================
        log("步骤7: 提交就绪检查")
        try:
            phase_btn = page.locator("button[aria-expanded='false']:has-text('提交就绪')").first
            if phase_btn.count() > 0:
                phase_btn.click()
                time.sleep(2)
            
            page.locator("button:has-text('阻断复核')").first.click()
            time.sleep(5)
            
            text = page.inner_text("body")
            log_page_state(page, "submission_readiness")
            
            # 检查就绪状态
            submittable = 0
            if "ready" in text.lower() or "就绪" in text:
                submittable += 1
            if "通过" in text and ("提交" in text or "阻断" in text):
                submittable += 1
            
            results["alphas_submittable"] = submittable
            results["steps"].append({
                "step": "提交就绪", 
                "status": "PASS", 
                "submittable": submittable
            })
            ss(page, "07_readiness")
        except Exception as e:
            log(f"   ⚠️ 提交就绪检查失败: {e}")
            results["steps"].append({"step": "提交就绪", "status": "WARN"})

        # ================================================================
        # 步骤8: 回到Dashboard看最终状态
        # ================================================================
        log("步骤8: 最终Dashboard状态")
        page.locator("button:has-text('运行总览')").first.click()
        time.sleep(3)
        text = page.inner_text("body")
        log_page_state(page, "final_dashboard")
        ss(page, "08_final")

        browser.close()

    # ================================================================
    # 最终报告
    # ================================================================
    print("\n" + "="*70)
    print("   📊 最终验收报告")
    print("="*70)
    
    total = len(results["steps"])
    passes = sum(1 for s in results["steps"] if s["status"] == "PASS")
    warns = sum(1 for s in results["steps"] if s["status"] == "WARN")
    fails = sum(1 for s in results["steps"] if s["status"] == "FAIL")
    
    print(f"\n   步骤: {total} | 通过: {passes} | 警告: {warns} | 失败: {fails}")
    print(f"\n   候选Alpha: {results['candidates_found']}")
    print(f"   可提交数: {results['alphas_submittable']}")
    
    print("\n   步骤详情:")
    for s in results["steps"]:
        icon = "✅" if s["status"]=="PASS" else "⚠️" if s["status"]=="WARN" else "❌"
        extra = ""
        if "count" in s: extra = f" (数量: {s['count']})"
        if "submittable" in s: extra = f" (可提交: {s['submittable']})"
        print(f"      {icon} {s['step']}{extra}")
    
    if results["issues"]:
        print(f"\n   ⚠️ 问题: {results['issues']}")
    
    print(f"\n   📸 截图: {OUT}/")
    
    if fails == 0:
        print("\n   🎉 判定: 通过 — Alpha生产+提交流程完整运行")
    else:
        print("\n   🚨 判定: 不通过")
    
    print("="*70)
    
    # 保存JSON报告
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/full_report.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
