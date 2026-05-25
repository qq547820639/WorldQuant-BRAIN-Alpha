from pathlib import Path

from brain_alpha_ops.data.loader import PACKAGED_OFFICIAL_CONTEXT_FILES
from brain_alpha_ops.research.hypothesis_library import PACKAGED_HYPOTHESIS_LIBRARY_FILES


def test_pyinstaller_spec_bundles_all_official_context_release_files():
    spec_text = Path("BrainAlphaOps.spec").read_text(encoding="utf-8")

    for filename in PACKAGED_OFFICIAL_CONTEXT_FILES:
        assert f"data\\\\{filename}" in spec_text


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

    assert "brain_alpha_ops\\\\research\\\\hypotheses" in spec_text
    assert len(PACKAGED_HYPOTHESIS_LIBRARY_FILES) >= 8


def test_pyinstaller_spec_bundles_assistant_prompt_templates():
    spec_text = Path("BrainAlphaOps.spec").read_text(encoding="utf-8")

    assert "brain_alpha_ops\\\\research\\\\prompts" in spec_text


def test_windows_build_copies_assistant_prompt_templates_to_dist_runtime_path():
    script_text = Path("scripts/build_windows.ps1").read_text(encoding="utf-8")

    assert "brain_alpha_ops\\research\\prompts" in script_text
    assert "dist\\brain_alpha_ops\\research\\prompts" in script_text
