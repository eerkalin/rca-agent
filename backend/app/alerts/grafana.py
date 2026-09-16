from typing import Any

from app.alerts.models import AlertEnvelope


class GrafanaAlertNormalizer:

    @staticmethod
    def normalize(payload: dict[str, Any]) -> list[AlertEnvelope]:
        alerts = payload.get("alerts", [])

        normalized_alerts: list[AlertEnvelope] = []

        for alert in alerts:
            labels = alert.get("labels", {}) or {}
            annotations = alert.get("annotations", {}) or {}

            title = (
                annotations.get("summary")
                or labels.get("alertname")
                or payload.get("title")
                or "Grafana Alert"
            )

            description = (
                annotations.get("description")
                or annotations.get("message")
            )

            external_id = (
                alert.get("fingerprint")
                or alert.get("generatorURL")
            )

            normalized_alerts.append(
                AlertEnvelope(
                    source="grafana",
                    external_id=external_id,
                    title=title,
                    description=description,
                    status=alert.get("status"),
                    labels=labels,
                    annotations=annotations,
                    starts_at=alert.get("startsAt"),
                    ends_at=alert.get("endsAt"),
                    raw_payload=alert,
                )
            )

        return normalized_alerts