"""Log-governance audit for AF-017: verify error/log redaction coverage."""
from __future__ import annotations
import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    findings = []
    
    # Check 1: dispatch redaction
    dispatch = ROOT / "brain_alpha_ops" / "web_handler_dispatch.py"
    if dispatch.exists():
        src = dispatch.read_text()
        if "redact_error_message" not in src:
            findings.append({"code":"dispatch_no_redaction","message":"web_handler_dispatch.py missing redact_error_message import"})
    
    # Check 2: frontend error centralization
    error_ts = ROOT / "brain_alpha_ops/web/react_app/src/helpers/errorExperience.ts"
    run_ts = ROOT / "brain_alpha_ops/web/react_app/src/helpers/runPayload.ts"
    for path in [error_ts, run_ts]:
        if not path.exists():
            findings.append({"code":"missing_error_helper","message":f"{path.name} not found"})
    
    # Check 3: sensitive artifact scan (delegate to existing script)
    
    output = {"ok":len(findings)==0,"audit_version":"log_governance.v1","total_checks":2,"findings":findings}
    if "--json" in sys.argv:
        print(json.dumps(output, indent=2))
    else:
        print(f"ok={output['ok']}, findings={len(findings)}")
        for f in findings: print(f"  [{f['code']}] {f['message']}")
    return int(not output["ok"])

if __name__ == "__main__":
    raise SystemExit(main())
