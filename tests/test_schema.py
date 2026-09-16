import pytest
from conftest import document
from pydantic import ValidationError

from harness_sync.config import parse_config, parse_yaml
from harness_sync.errors import HarnessSyncError
from harness_sync.schema import Config


def test_roles_and_provider_local_identity():
    doc = document()
    doc["providers"][0]["models"][1]["overrides"] = {"fake": {"id": "other/Exact-ID"}}
    config = Config.model_validate(doc)
    model = config.providers[0].model_for("daily")
    assert model.upstream_id("fake") == "other/Exact-ID"
    assert model.upstream_id("pi") == "vendor/one-daily"
    del doc["providers"][0]["models"][0]["id"]
    assert Config.model_validate(doc).providers[0].models[0].upstream_id("pi") == "same-label"


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(watch={}),
        lambda d: d.update(harnesses={"fake": {"enabled": True}}),
        lambda d: d["providers"][0]["models"].pop(),
        lambda d: d["providers"][0].update(api_key="raw-key"),
        lambda d: d["providers"][0].update(base_url="https://user:key@host/v1"),
        lambda d: d["providers"][0].update(headers={"Authorization": "raw-key"}),
        lambda d: d["providers"][0]["models"][0].update(context_window="128000"),
        lambda d: d["providers"][0]["models"][0].update(context_window=10, max_output_tokens=20),
    ],
)
def test_strict_schema(change):
    doc = document()
    change(doc)
    with pytest.raises(ValidationError):
        Config.model_validate(doc)


@pytest.mark.parametrize(
    "source",
    [
        b"version: 1\nversion: 2\n",
        b"!!python/object/apply:os.system ['echo bad']",
        b"version: [",
    ],
)
def test_unsafe_or_ambiguous_yaml_rejected(source):
    with pytest.raises(HarnessSyncError):
        parse_yaml(source)


def test_error_does_not_echo_secret():
    with pytest.raises(HarnessSyncError) as error:
        parse_config(b"version: 1\nproviders: raw-secret-value")
    assert "raw-secret-value" not in str(error.value)


def test_alias_and_env_collisions():
    doc = document("alpha", "a-b")
    second = document("beta", "a_b")["providers"][0]
    doc["providers"].append(second)
    with pytest.raises(ValidationError):
        Config.model_validate(doc)
    second["api_key"] = {"secret": "other"}
    second["alias"] = "alpha"
    with pytest.raises(ValidationError):
        Config.model_validate(doc)
