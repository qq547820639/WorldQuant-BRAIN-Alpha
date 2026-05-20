"""Build production .exe with PyInstaller."""
import PyInstaller.__main__
import os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

PyInstaller.__main__.run([
    "--name=BrainAlphaProd",
    "--onefile",
    "--console",
    "--clean",
    "--noconfirm",
    "--add-data=config/run_config.json;config",
    "--add-data=data/official_fields.json;data",
    "--add-data=data/official_operators.json;data",
    "--add-data=data/official_datasets.json;data",
    "--hidden-import=brain_alpha_ops",
    "--hidden-import=brain_alpha_ops.config",
    "--hidden-import=brain_alpha_ops.models",
    "--hidden-import=brain_alpha_ops.runner",
    "--hidden-import=brain_alpha_ops.research.pipeline",
    "--hidden-import=brain_alpha_ops.research.generator",
    "--hidden-import=brain_alpha_ops.research.scoring",
    "--hidden-import=brain_alpha_ops.research.safety",
    "--hidden-import=brain_alpha_ops.research.repository",
    "--hidden-import=brain_alpha_ops.research.convergence",
    "--hidden-import=brain_alpha_ops.brain_api",
    "--hidden-import=brain_alpha_ops.brain_api.mock",
    "--hidden-import=brain_alpha_ops.brain_api.official",
    "--hidden-import=brain_alpha_ops.brain_api.context_defaults",
    "--hidden-import=brain_alpha_ops.data",
    "--hidden-import=brain_alpha_ops.data.loader",
    "--hidden-import=brain_alpha_ops.data.schemas",
    "--hidden-import=yaml",
    "run_pipeline.py",
])

print("\nBuild complete. Output: dist/BrainAlphaProd.exe")
