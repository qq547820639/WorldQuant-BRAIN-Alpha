"""Build the packaged Web console launcher with PyInstaller."""
import PyInstaller.__main__
import os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

PyInstaller.__main__.run([
    "--name=BrainAlphaConsole",
    "--onefile",
    "--windowed",
    "--clean",
    "--noconfirm",
    f"--add-data=config/run_config.json{os.pathsep}config",
    f"--add-data=data/official_fields.json{os.pathsep}data",
    f"--add-data=data/official_operators.json{os.pathsep}data",
    f"--add-data=data/official_datasets.json{os.pathsep}data",
    f"--add-data=brain_alpha_ops/web/react_app/dist{os.pathsep}brain_alpha_ops/web/react_app/dist",
    # Runtime-generated data files (official_context_refresh_status.json,
    # candidates.jsonl, etc.) are NOT bundled — they are created fresh on
    # first run in the configured storage directory.
    "--hidden-import=brain_alpha_ops",
    "--hidden-import=brain_alpha_ops.config",
    "--hidden-import=brain_alpha_ops.models",
    "--hidden-import=brain_alpha_ops.runner",
    "--hidden-import=brain_alpha_ops.web_http_handler",
    "--hidden-import=brain_alpha_ops.web_routes",
    "--hidden-import=brain_alpha_ops.web_handler_dispatch",
    "--hidden-import=brain_alpha_ops.research.pipeline",
    "--hidden-import=brain_alpha_ops.research.generator",
    "--hidden-import=brain_alpha_ops.research.scoring",
    "--hidden-import=brain_alpha_ops.research.safety",
    "--hidden-import=brain_alpha_ops.research.repository",
    "--hidden-import=brain_alpha_ops.research.convergence",
    "--hidden-import=brain_alpha_ops.brain_api",
    "--hidden-import=brain_alpha_ops.brain_api.official",
    "--hidden-import=brain_alpha_ops.brain_api.context_defaults",
    "--hidden-import=brain_alpha_ops.data",
    "--hidden-import=brain_alpha_ops.data.loader",
    "--hidden-import=brain_alpha_ops.data.schemas",
    "--hidden-import=yaml",
    "launch_web.py",
])

print("\nBuild complete. Output: dist/BrainAlphaConsole.exe")
