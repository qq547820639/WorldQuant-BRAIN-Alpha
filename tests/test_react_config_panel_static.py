from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PANEL = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "components" / "ConfigPanel.tsx"


def test_config_panel_exposes_import_export_controls():
    source = CONFIG_PANEL.read_text(encoding="utf-8")

    assert 'aria-label="导入配置JSON"' in source
    assert 'accept="application/json,.json"' in source
    assert "importInputRef.current?.click()" in source
    assert "导入" in source
    assert "导出" in source


def test_config_panel_exposes_session_only_brain_connection_credentials():
    source = CONFIG_PANEL.read_text(encoding="utf-8")

    assert 'title="BRAIN 连接"' in source
    assert 'description="这些字段只保留在当前页面，用于本次连接测试和验证。"' in source
    assert 'label="账户邮箱"' in source
    assert 'label="密码"' in source
    assert 'label="Token"' in source
    assert 'type="password"' in source
    assert 'connectionApi.call("/api/test_connection"' in source
    assert "测试 BRAIN 连接" in source
    assert "BRAIN 连接测试通过" in source
    assert "payloadFromForm(form, credentials)" in source
    assert "hasSessionCredentials" in source
    assert "保存配置不会保存账号、密码或 token" in source


def test_config_panel_exports_current_edit_payload_without_saving():
    source = CONFIG_PANEL.read_text(encoding="utf-8")

    assert "const exportConfig = () =>" in source
    assert "JSON.stringify(payloadFromForm(form), null, 2)" in source
    assert "new Blob" in source
    assert "brain-alpha-config-" in source
    assert "link.click()" in source
    assert "URL.revokeObjectURL(url)" in source


def test_config_panel_imports_and_validates_json_before_save():
    source = CONFIG_PANEL.read_text(encoding="utf-8")

    assert "const importConfig = async" in source
    assert "JSON.parse(await file.text())" in source
    assert "formFromImport" in source
    assert "const error = validateForm(imported, schema)" in source
    assert "setForm(imported)" in source
    assert "配置已导入" in source


def test_config_panel_import_accepts_export_payload_and_public_config_shapes():
    source = CONFIG_PANEL.read_text(encoding="utf-8")

    assert "const source = asRecord(root.config) || root" in source
    assert "if (asRecord(source.ops))" in source
    assert 'return formFromConfig({' in source
    assert 'environment: String(source.environment || "production")' in source
    assert "autoSubmit: false" in source
    assert '<CheckboxField label="自动提交"' not in source
    assert 'value="关闭（Web 保存强制）"' in source
    assert "instrumentType: stringValue(settings.instrumentType" in source
    assert "region: stringValue(settings.region" in source
    assert "alphaType: stringValue(settings.type ?? settings.alphaType" in source
    assert "maxWeightConcentration: numberValue(source.maxWeightConcentration" in source


def test_config_panel_validates_canonical_settings_and_dataset_options():
    source = CONFIG_PANEL.read_text(encoding="utf-8")

    assert "const MAX_CONFIG_TEXT_LENGTH = 128;" in source
    assert "const CONFIG_TEXT_PATTERN = /^[A-Za-z0-9_.:-]*$/;" in source
    assert 'const DEFAULT_REGION_OPTIONS = ["USA", "CHN", "EUR", "GLB"];' in source
    assert 'const DEFAULT_UNIVERSE_OPTIONS = ["TOP3000", "TOP1000", "TOP500"];' in source
    assert 'const DEFAULT_INSTRUMENT_TYPE_OPTIONS = ["EQUITY"];' in source
    assert 'const DEFAULT_NEUTRALIZATION_OPTIONS = ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET", "NONE"];' in source
    assert 'const DEFAULT_ALPHA_TYPE_OPTIONS = ["REGULAR", "POWER_POOL", "ATOM", "PYRAMID"];' in source
    assert "validateForm(form, schema)" in source
    assert "datasetSelectOptions(schema, form.dataset)" in source
    assert 'placeholder="自动选择"' in source
    assert 'return "不支持的区域。"' in source
    assert 'return "不支持的股票池。"' in source
    assert 'return "不支持的中性化方式。"' in source
    assert 'return "不支持的数据集，请从下拉列表选择。";' in source
    assert "数据集长度不能超过 ${MAX_CONFIG_TEXT_LENGTH} 个字符。" in source
    assert "数据集只能包含字母、数字、下划线、短横线、点或冒号。" in source


def test_config_panel_sanitizes_user_editable_text_inputs():
    source = CONFIG_PANEL.read_text(encoding="utf-8")

    assert "function sanitizeConfigText(value: string)" in source
    assert 'value.replace(/[\\x00-\\x1F\\x7F]/g, "").slice(0, MAX_CONFIG_TEXT_LENGTH)' in source
    assert 'maxLength={MAX_CONFIG_TEXT_LENGTH}' in source
    assert 'onChange={(value) => update("dataset", sanitizeConfigText(value))}' in source
