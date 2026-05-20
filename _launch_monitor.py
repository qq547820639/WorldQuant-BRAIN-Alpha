"""Launch BrainAlphaProd.exe and monitor output."""
import subprocess, os, time, sys

exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "BrainAlphaProd.exe")
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "prod_monitor.log")

env = os.environ.copy()
# 凭证通过环境变量传入，不要把真实账号密码写进文件
# 用法: $env:BRAIN_USERNAME="your@email.com"; $env:BRAIN_PASSWORD="your_password"; python _launch_monitor.py
if not env.get("BRAIN_USERNAME") or not env.get("BRAIN_PASSWORD"):
    if not env.get("BRAIN_TOKEN"):
        print("[MONITOR] ERROR: Set BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN environment variables.")
        sys.exit(1)

print(f"[MONITOR] Launching: {exe_path}")
print(f"[MONITOR] Log: {log_path}")

with open(log_path, "w", encoding="utf-8") as log:
    log.write(f"=== BRAIN Alpha Production Run ===\n")
    log.write(f"=== Started: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
    log.flush()
    
    proc = subprocess.Popen(
        [exe_path],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    
    print(f"[MONITOR] PID: {proc.pid}")
    
    last_report = time.time()
    line_count = 0
    
    try:
        for line in proc.stdout:
            line_count += 1
            log.write(line)
            log.flush()
            
            now = time.time()
            if now - last_report > 10:
                elapsed = now - last_report
                print(f"[MONITOR] Running... {line_count} lines, last: {line.rstrip()[:100]}")
                last_report = now
            
            # Check for key events
            if "DONE" in line or "run_completed" in line.lower():
                print(f"[MONITOR] PIPELINE COMPLETED!")
                break
            if "FAILED" in line or "error" in line.lower():
                print(f"[MONITOR] ALERT: {line.rstrip()[:150]}")
    
    except KeyboardInterrupt:
        print(f"[MONITOR] Interrupted. Terminating...")
        proc.terminate()
    
    proc.wait()
    print(f"[MONITOR] Exit code: {proc.returncode}")
    print(f"[MONITOR] Total lines: {line_count}")
    print(f"[MONITOR] Full log: {log_path}")

if __name__ == "__main__":
    import subprocess, os, time, sys
    exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "BrainAlphaProd.exe")
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "prod_monitor.log")
    env = os.environ.copy()
    # 凭证通过环境变量传入，不要把真实账号密码写进文件
    if not env.get("BRAIN_USERNAME") or not env.get("BRAIN_PASSWORD"):
        if not env.get("BRAIN_TOKEN"):
            print("[MONITOR] ERROR: Set BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN environment variables.")
            sys.exit(1)
    print(f"[MONITOR] Launching: {exe_path}")
    print(f"[MONITOR] Log: {log_path}")
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"=== BRAIN Alpha Production Run ===\n")
        log.write(f"=== Started: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
        log.flush()
        proc = subprocess.Popen([exe_path], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", cwd=os.path.dirname(os.path.abspath(__file__)))
        print(f"[MONITOR] PID: {proc.pid}")
        last_report = time.time()
        line_count = 0
        try:
            for line in proc.stdout:
                line_count += 1
                log.write(line)
                log.flush()
                now = time.time()
                if now - last_report > 10:
                    print(f"[MONITOR] Running... {line_count} lines, last: {line.rstrip()[:100]}")
                    last_report = now
                if "DONE" in line or "run_completed" in line.lower():
                    print(f"[MONITOR] PIPELINE COMPLETED!")
                    break
                if "FAILED" in line or "error" in line.lower():
                    print(f"[MONITOR] ALERT: {line.rstrip()[:150]}")
        except KeyboardInterrupt:
            print(f"[MONITOR] Interrupted.")
            proc.terminate()
        proc.wait()
        print(f"[MONITOR] Exit: {proc.returncode} | Lines: {line_count} | Log: {log_path}")
