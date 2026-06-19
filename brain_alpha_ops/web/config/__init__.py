"""Configuration, capability registry, and config schema modules."""
from __future__ import annotations


def __getattr__(name: str):
    if name in _CONFIG_LAZY:
        module_name, attr = _CONFIG_LAZY[name]
        import importlib
        mod = importlib.import_module(module_name, __package__)
        result = getattr(mod, attr)
        globals()[name] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_CONFIG_LAZY: dict[str, tuple[str, str]] = {
    # web_config.py
    "config_from_payload": (".web_config", "config_from_payload"),
    "public_run_config_dict": (".web_config", "public_run_config_dict"),
    "managed_credentials_available": (".web_config", "managed_credentials_available"),
    "save_run_config_payload": (".web_config", "save_run_config_payload"),
    "payload_truthy": (".web_config", "payload_truthy"),
    "payload_bool": (".web_config", "payload_bool"),
    "payload_web_environment": (".web_config", "payload_web_environment"),
    "payload_string_list": (".web_config", "payload_string_list"),
    "bounded_query_int": (".web_config", "bounded_query_int"),
    "bounded_query_float": (".web_config", "bounded_query_float"),
    "run_config_from_payload": (".web_config", "run_config_from_payload"),
    "payload_int": (".web_config", "payload_int"),
    "payload_float": (".web_config", "payload_float"),
    "validate_settings_enums": (".web_config", "validate_settings_enums"),
}

__all__ = list(_CONFIG_LAZY.keys())
