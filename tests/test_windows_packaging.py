from pathlib import Path

from brain_alpha_ops.data.loader import PACKAGED_OFFICIAL_CONTEXT_FILES
from brain_alpha_ops.research.hypothesis_library import PACKAGED_HYPOTHESIS_LIBRARY_FILES


def test_pyinstaller_spec_bundles_all_official_context_release_files():
    spec_text = Path("BrainAlphaOps.spec").read_text(encoding="utf-8")

    for filename in PACKAGED_OFFICIAL_CONTEXT_FILES:
        assert f"data\\/{filename}" in spec_text


def test_windows_build_copies_official_context_files_to_dist_data():
    script_text = Path("scripts/build_windows.ps1").read_text(encoding="utf-8")

    assert 'Join-Path $Root "dist\\data"' in script_text
    for filename in PACKAGED_OFFICIAL_CONTEXT_FILES:
        assert f'"{filename}"' in script_text


def test_windows_build_copies_hypothesis_library_to_dist_runtime_path():
    script_text = Path("scripts/build_windows.ps1").read_text(encoding="utf-8")

    assert 'brain_alpha_ops\\research\\hypotheses' in script_text
    assert 'dist\\brain_alpha_ops\\research\\hypotheses' in script_text
    assert "Copy-Item" in script_text


def test_pyinstaller_spec_bundles_hypothesis_library_directory():
    spec_text = Path("BrainAlphaOps.spec").read_text(encoding="utf-8")

    assert "brain_alpha_ops/research/hypotheses" in spec_text
    assert len(PACKAGED_HYPOTHESIS_LIBRARY_FILES) >= 8


def test_pyinstaller_spec_bundles_assistant_prompt_templates():
    spec_text = Path("BrainAlphaOps.spec").read_text(encoding="utf-8")

    assert "brain_alpha_ops/research/prompts" in spec_text


def test_pyinstaller_spec_bundles_react_web_console_dist():
    spec_text = Path("BrainAlphaOps.spec").read_text(encoding="utf-8")

    assert "brain_alpha_ops/web/react_app/dist" in spec_text
    assert "brain_alpha_ops/web/index.html" not in spec_text


def test_windows_build_copies_assistant_prompt_templates_to_dist_runtime_path():
    script_text = Path("scripts/build_windows.ps1").read_text(encoding="utf-8")

    assert "brain_alpha_ops\\research\\prompts" in script_text
    assert "dist\\brain_alpha_ops\\research\\prompts" in script_text


def test_windows_build_copies_react_web_console_dist_to_runtime_path():
    script_text = Path("scripts/build_windows.ps1").read_text(encoding="utf-8")

    assert "brain_alpha_ops\\web\\react_app\\dist" in script_text
    assert "dist\\brain_alpha_ops\\web\\react_app\\dist" in script_text
    assert "Missing required React Web console artifact" in script_text


def test_build_prod_uses_platform_path_separator_for_add_data():
    build_text = Path("build_prod.py").read_text(encoding="utf-8")

    assert "os.pathsep" in build_text
    assert "--add-data=config/run_config.json;config" not in build_text
    assert "brain_alpha_ops/web/react_app/dist" in build_text
    assert "launch_web.py" in build_text
    assert "run_pipeline.py" not in build_text
    assert "--windowed" in build_text
    assert "--console" not in build_text


def test_pyinstaller_spec_is_web_console_launcher_not_cli_surface():
    spec_text = Path("BrainAlphaOps.spec").read_text(encoding="utf-8")

    assert "launch_web.py" in spec_text
    assert "brain_alpha_ops.cli" not in spec_text
    assert "console=False" in spec_text


def test_windows_build_does_not_embed_user_specific_python_path():
    script_text = Path("scripts/build_windows.ps1").read_text(encoding="utf-8")

    assert "54782" not in script_text
    assert '$Python = "python"' in script_text
