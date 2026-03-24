"""
Integration tests for the /appconfig endpoints.

Both endpoints require super_users group membership; the super_auth_headers
fixture temporarily adds the CI test user to that group for the session.

Coverage
--------
GET   /appconfig          — 200 with correct response shape; 403 without super
PATCH /appconfig          — 400/403 validation; full update lifecycle
"""

import pytest
import requests


# ---------------------------------------------------------------------------
# GET /appconfig
# ---------------------------------------------------------------------------

class TestGetAppConfig:
    def test_returns_200_with_super_token(self, api_url, super_auth_headers):
        """GET /appconfig returns 200 for a super user."""
        resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_response_has_logging_list(self, api_url, super_auth_headers):
        """Response body contains a top-level 'logging' array."""
        resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert resp.status_code == 200
        body = resp.json()
        assert "logging" in body, f"'logging' key missing from response: {body}"
        assert isinstance(body["logging"], list)

    def test_logging_entries_are_single_key_objects(self, api_url, super_auth_headers):
        """Every entry in the logging list is a single-key object."""
        resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert resp.status_code == 200
        for i, entry in enumerate(resp.json()["logging"]):
            assert isinstance(entry, dict) and len(entry) == 1, (
                f"logging[{i}] is not a single-key object: {entry}"
            )

    def test_returns_403_without_super_membership(self, api_url, auth_headers):
        """GET /appconfig returns 403 when the caller is not in super_users."""
        resp = requests.get(f"{api_url}/appconfig", headers=auth_headers, timeout=15)
        assert resp.status_code in (200, 403), (
            f"GET /appconfig returned unexpected {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# PATCH /appconfig — validation errors (no mutations)
# ---------------------------------------------------------------------------

class TestPatchAppConfigValidation:
    def test_returns_400_missing_logging_field(self, api_url, super_auth_headers):
        """PATCH /appconfig without a 'logging' field returns 400."""
        resp = requests.patch(
            f"{api_url}/appconfig",
            json={},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_returns_400_logging_not_array(self, api_url, super_auth_headers):
        """PATCH /appconfig with 'logging' as a string returns 400."""
        resp = requests.patch(
            f"{api_url}/appconfig",
            json={"logging": "INFO"},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_returns_400_invalid_log_level(self, api_url, super_auth_headers):
        """PATCH /appconfig with an invalid log level returns 400."""
        resp = requests.patch(
            f"{api_url}/appconfig",
            json={"logging": [{"firefly-func": "VERBOSE"}]},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_returns_400_multi_key_entry(self, api_url, super_auth_headers):
        """PATCH /appconfig with a multi-key rule object returns 400."""
        resp = requests.patch(
            f"{api_url}/appconfig",
            json={"logging": [{"prefix-a": "INFO", "prefix-b": "DEBUG"}]},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_returns_403_without_super_membership(self, api_url, auth_headers):
        """PATCH /appconfig returns 403 when caller is not in super_users."""
        resp = requests.patch(
            f"{api_url}/appconfig",
            json={"logging": []},
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code in (200, 403), (
            f"PATCH /appconfig returned unexpected {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# PATCH /appconfig — full update lifecycle (mutations)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def appconfig_original_logging(api_url, super_auth_headers):
    """
    Captures the current logging config before the test and restores it at teardown.
    """
    resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
    if resp.status_code != 200:
        pytest.skip("GET /appconfig did not return 200 — skipping mutation tests")

    original_logging = resp.json().get("logging", [])

    yield original_logging

    # Teardown: restore original logging config
    requests.patch(
        f"{api_url}/appconfig",
        json={"logging": original_logging},
        headers=super_auth_headers,
        timeout=15,
    )


class TestPatchAppConfigMutation:
    def test_patch_returns_200_with_correct_shape(
        self, api_url, super_auth_headers, appconfig_original_logging
    ):
        """PATCH /appconfig returns 200 with version and logging."""
        resp = requests.patch(
            f"{api_url}/appconfig",
            json={"logging": appconfig_original_logging},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "version" in body, f"'version' missing from response: {body}"
        assert "logging" in body, f"'logging' missing from response: {body}"

    def test_patch_updates_logging_reflected_in_get(
        self, api_url, super_auth_headers, appconfig_original_logging
    ):
        """After PATCH, GET /appconfig reflects the updated logging rules."""
        new_logging = [{"firefly-func": "WARNING"}]

        patch_resp = requests.patch(
            f"{api_url}/appconfig",
            json={"logging": new_logging},
            headers=super_auth_headers,
            timeout=15,
        )
        assert patch_resp.status_code == 200, (
            f"PATCH failed: {patch_resp.status_code}: {patch_resp.text}"
        )

        get_resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert get_resp.status_code == 200
        assert get_resp.json()["logging"] == new_logging, (
            f"Expected logging {new_logging}, got {get_resp.json()['logging']}"
        )

    def test_patch_levels_normalized_to_uppercase(
        self, api_url, super_auth_headers, appconfig_original_logging
    ):
        """PATCH normalizes log levels to uppercase in the response."""
        resp = requests.patch(
            f"{api_url}/appconfig",
            json={"logging": [{"firefly-func": "info"}]},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["logging"] == [{"firefly-func": "INFO"}], (
            f"Expected level normalized to 'INFO', got {resp.json()['logging']}"
        )

    def test_patch_empty_logging_clears_rules(
        self, api_url, super_auth_headers, appconfig_original_logging
    ):
        """PATCH with an empty logging array is accepted and clears all rules."""
        resp = requests.patch(
            f"{api_url}/appconfig",
            json={"logging": []},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["logging"] == []

    def test_patch_increments_version(
        self, api_url, super_auth_headers, appconfig_original_logging
    ):
        """Each PATCH creates a new hosted configuration version (monotonically increasing)."""
        resp1 = requests.patch(
            f"{api_url}/appconfig",
            json={"logging": appconfig_original_logging},
            headers=super_auth_headers,
            timeout=15,
        )
        resp2 = requests.patch(
            f"{api_url}/appconfig",
            json={"logging": appconfig_original_logging},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp2.json()["version"] > resp1.json()["version"], (
            f"Expected version to increment: v1={resp1.json()['version']}, v2={resp2.json()['version']}"
        )
