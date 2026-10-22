from __future__ import annotations

from pathlib import Path

from app.core.config import Settings

BOOTSTRAP_ENV_KEYS = (
    "OPPORTUNITY_RETENTION_TREATED_DAYS",
    "OPPORTUNITY_RETENTION_REJECTED_DAYS",
    "OPPORTUNITY_RETENTION_RESOLVED_EXTERNALLY_DAYS",
    "NUVEMIQ_OPPORTUNITY_OBSERVATION_RETENTION_DAYS",
)


def _without_policy_bootstrap_env(monkeypatch) -> Settings:
    for name in BOOTSTRAP_ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    return Settings(_env_file=None)


def test_settings_defaults_match_persisted_policy_defaults(monkeypatch):
    settings = _without_policy_bootstrap_env(monkeypatch)

    assert settings.opportunity_retention_treated_days == 30
    assert settings.opportunity_retention_rejected_days == 30
    assert settings.opportunity_retention_resolved_externally_days == 30
    assert settings.opportunity_observation_retention_days == 400


def test_env_example_bootstrap_defaults_match_persisted_policy_defaults():
    repository_root = Path(__file__).resolve().parents[3]
    values = {}
    for raw_line in (repository_root / ".env.example").read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name] = value

    assert values["OPPORTUNITY_RETENTION_TREATED_DAYS"] == "30"
    assert values["OPPORTUNITY_RETENTION_REJECTED_DAYS"] == "30"
    assert values["OPPORTUNITY_RETENTION_RESOLVED_EXTERNALLY_DAYS"] == "30"
    assert values["NUVEMIQ_OPPORTUNITY_OBSERVATION_RETENTION_DAYS"] == "400"
