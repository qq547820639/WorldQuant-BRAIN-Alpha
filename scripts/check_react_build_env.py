"""Check whether the optional React console can run its production build.

The shipped production surface is the inline HTML/JS console, but the React
mirror still needs a clear readiness check so a missing Node toolchain is not
mistaken for a passing build.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_DIR = PROJECT_ROOT / "brain_alpha_ops" / "web" / "react_app"
LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock")
REQUIRED_PACKAGES = ("react", "react-dom", "typescript", "vite", "@vitejs/plugin-react")

Runner = Callable[[list[str], Path, float], tuple[int, str, str, float]]


def check_react_build_env(
    app_dir: Path = DEFAULT_APP_DIR,
    *,
    strict: bool = False,
    run_build: bool = False,
    runner: Runner | None = None,
) -> dict:
    app_dir = app_dir.resolve()
    package_json = app_dir / "package.json"
    lockfiles = [name for name in LOCKFILES if (app_dir / name).is_file()]
    npm_path = shutil.which("npm")
    node_path = shutil.which("node")
    node_modules = app_dir / "node_modules"
    installed = _installed_packages(node_modules)

    findings: list[dict] = []
    _require(findings, package_json.is_file(), "missing_package_json", f"{package_json} does not exist")
    _require(findings, bool(node_path), "missing_node", "node executable was not found on PATH")
    _require(findings, bool(npm_path), "missing_npm", "npm executable was not found on PATH")
    _require(findings, bool(lockfiles), "missing_lockfile", "React app has no package manager lockfile")
    _require(findings, node_modules.is_dir(), "missing_node_modules", "React app dependencies are not installed")

    missing_packages = [name for name in REQUIRED_PACKAGES if name not in installed]
    if missing_packages:
        findings.append({
            "code": "missing_react_dependencies",
            "severity": "blocking",
            "message": "React app node_modules is missing required packages",
            "packages": missing_packages,
        })

    build_result = None
    ready = not findings
    if run_build and ready:
        build_result = _run_build(app_dir, runner=runner)
        if not build_result["ok"]:
            findings.append({
                "code": "react_build_failed",
                "severity": "blocking",
                "message": "npm run build returned a non-zero exit code",
                "exit_code": build_result["exit_code"],
            })

    ok = not findings if strict or run_build else True
    return {
        "ok": ok,
        "schema_version": "react_build_env.v1",
        "strict": bool(strict),
        "run_build": bool(run_build),
        "app_dir": str(app_dir),
        "production_surface": "inline_html_js",
        "react_surface": "mirror",
        "ready": ready and (build_result is None or build_result["ok"]),
        "tooling": {
            "node": node_path or "",
            "npm": npm_path or "",
            "lockfiles": lockfiles,
            "node_modules": str(node_modules) if node_modules.is_dir() else "",
            "installed_required_packages": sorted(installed),
        },
        "build": build_result,
        "findings": findings,
        "recommendation": _recommendation(findings),
    }


def _installed_packages(node_modules: Path) -> set[str]:
    if not node_modules.is_dir():
        return set()
    installed: set[str] = set()
    for name in REQUIRED_PACKAGES:
        package_path = node_modules / name
        if package_path.is_dir():
            installed.add(name)
    return installed


def _require(findings: list[dict], condition: bool, code: str, message: str) -> None:
    if not condition:
        findings.append({"code": code, "severity": "blocking", "message": message})


def _run_build(app_dir: Path, *, runner: Runner | None = None) -> dict:
    started = time.perf_counter()
    command = ["npm", "run", "build"]
    active_runner = runner or _subprocess_runner
    exit_code, stdout, stderr, duration = active_runner(command, app_dir, 120.0)
    return {
        "ok": exit_code == 0,
        "command": command,
        "exit_code": exit_code,
        "duration_seconds": round(duration or (time.perf_counter() - started), 3),
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
    }


def _subprocess_runner(command: list[str], cwd: Path, timeout: float) -> tuple[int, str, str, float]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return 127, "", str(exc), time.perf_counter() - started
    except subprocess.TimeoutExpired as exc:
        return 124, _text(exc.stdout), _text(exc.stderr, "npm run build timed out"), time.perf_counter() - started
    return proc.returncode, proc.stdout, proc.stderr, time.perf_counter() - started


def _text(value: str | bytes | None, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _recommendation(findings: list[dict]) -> str:
    if not findings:
        return "React build tooling is ready; run with --run-build to execute npm run build."
    codes = {finding["code"] for finding in findings}
    actions = []
    if "missing_npm" in codes:
        actions.append("install Node.js with npm available on PATH")
    if "missing_lockfile" in codes:
        actions.append("commit a package manager lockfile")
    if "missing_node_modules" in codes or "missing_react_dependencies" in codes:
        actions.append("install React app dependencies from the lockfile")
    if not actions:
        actions.append("inspect the build failure above")
    return "; ".join(actions) + "."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check React Web console build readiness.")
    parser.add_argument("--app-dir", default=str(DEFAULT_APP_DIR))
    parser.add_argument("--strict", action="store_true", help="exit non-zero when React build prerequisites are missing")
    parser.add_argument("--run-build", action="store_true", help="run npm run build after prerequisites are available")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    result = check_react_build_env(Path(args.app_dir), strict=args.strict, run_build=args.run_build)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "READY" if result["ready"] else "NOT READY"
        print(f"{status}: React build environment")
        for finding in result["findings"]:
            print(f"- {finding['code']}: {finding['message']}")
        print(result["recommendation"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
