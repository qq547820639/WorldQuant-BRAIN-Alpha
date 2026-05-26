from brain_alpha_ops.research.alerting import AlertDeliveryService, AlertRouter


def test_alert_delivery_service_persists_alerts(tmp_path):
    service = AlertDeliveryService(storage_dir=tmp_path)

    payload = service.alert("cache stale", "refresh required", severity="warning", channel="local")
    recent = service.recent()

    assert payload["ok"] is True
    assert payload["transport"]["delivered"] is False
    assert recent["count"] == 1
    assert recent["alerts"][0]["title"] == "cache stale"


def test_alert_router_deduplicates_channels_and_persists_each_delivery(tmp_path):
    payload = AlertRouter(storage_dir=tmp_path).route(
        "batch complete",
        "planned jobs ready",
        severity="info",
        channels=["local", "local", "ops"],
    )

    assert payload["ok"] is True
    assert payload["channels"] == ["local", "ops"]
    assert len(payload["deliveries"]) == 2
    assert AlertDeliveryService(storage_dir=tmp_path).recent()["count"] == 2
