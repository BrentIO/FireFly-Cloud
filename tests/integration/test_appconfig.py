"""
Integration tests for the /appconfig endpoints.

Both endpoints require super_users group membership; the super_auth_headers
fixture temporarily adds the CI test user to that group for the session.

Coverage
--------
GET  /appconfig                  — 200 with correct response shape; 403 without super
PATCH /appconfig/{application}   — 400/403/404 validation; full update lifecycle
"""

import urllib.parse

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

    def test_response_has_applications_list(self, api_url, super_auth_headers):
        """Response body contains a top-level 'applications' array."""
        resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert resp.status_code == 200
        body = resp.json()
        assert "applications" in body, f"'applications' key missing from response: {body}"
        assert isinstance(body["applications"], list)

    def test_application_objects_have_required_fields(self, api_url, super_auth_headers):
        """Every entry in the applications list has the expected fields."""
        resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert resp.status_code == 200
        applications = resp.json()["applications"]
        required = {"id", "name", "environment_id", "profile_id", "logging"}
        for app in applications:
            missing = required - app.keys()
            assert not missing, f"Application entry missing fields {missing}: {app}"

    def test_logging_field_is_list_or_null(self, api_url, super_auth_headers):
        """The 'logging' field on each application is either a list or null."""
        resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert resp.status_code == 200
        for app in resp.json()["applications"]:
            assert app["logging"] is None or isinstance(app["logging"], list), (
                f"Expected 'logging' to be list or null for {app['name']}, got {type(app['logging'])}"
            )

    def test_applications_sorted_by_name(self, api_url, super_auth_headers):
        """Applications are returned in alphabetical order by name."""
        resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert resp.status_code == 200
        names = [a["name"] for a in resp.json()["applications"]]
        assert names == sorted(names), f"Applications not sorted: {names}"

    def test_returns_403_without_super_membership(self, api_url, auth_headers):
        """GET /appconfig returns 403 when the caller is not in super_users."""
        resp = requests.get(f"{api_url}/appconfig", headers=auth_headers, timeout=15)
        assert resp.status_code in (200, 403), (
            f"GET /appconfig returned unexpected {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# PATCH /appconfig/{application} — validation errors (no mutations)
# ---------------------------------------------------------------------------

class TestPatchAppConfigValidation:
    def test_returns_404_for_unknown_application(self, api_url, super_auth_headers):
        """PATCH /appconfig/{application} returns 404 for a non-existent application."""
        resp = requests.patch(
            f"{api_url}/appconfig/firefly-func-does-not-exist",
            json={"logging": []},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_returns_400_missing_logging_field(self, api_url, super_auth_headers):
        """PATCH /appconfig/{application} without a 'logging' field returns 400."""
        resp = requests.patch(
            f"{api_url}/appconfig/firefly-func-does-not-exist",
            json={},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_returns_400_logging_not_array(self, api_url, super_auth_headers):
        """PATCH /appconfig/{application} with 'logging' as a string returns 400."""
        resp = requests.patch(
            f"{api_url}/appconfig/firefly-func-does-not-exist",
            json={"logging": "INFO"},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_returns_400_invalid_log_level(self, api_url, super_auth_headers):
        """PATCH /appconfig/{application} with an invalid log level returns 400."""
        resp = requests.patch(
            f"{api_url}/appconfig/firefly-func-does-not-exist",
            json={"logging": [{"firefly-func": "VERBOSE"}]},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_returns_400_multi_key_entry(self, api_url, super_auth_headers):
        """PATCH /appconfig/{application} with a multi-key rule object returns 400."""
        resp = requests.patch(
            f"{api_url}/appconfig/firefly-func-does-not-exist",
            json={"logging": [{"prefix-a": "INFO", "prefix-b": "DEBUG"}]},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_returns_403_without_super_membership(self, api_url, auth_headers):
        """PATCH /appconfig/{application} returns 403 when caller is not in super_users."""
        resp = requests.patch(
            f"{api_url}/appconfig/firefly-func-does-not-exist",
            json={"logging": []},
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code in (400, 403), (
            f"PATCH /appconfig returned unexpected {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# PATCH /appconfig/{application} — full update lifecycle (mutations)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def appconfig_application(api_url, super_auth_headers):
    """
    Yields the name and original logging config of the first available AppConfig
    application. Restores the original config at teardown.

    Skipped when no applications are found or Cognito env vars are not set.
    """
    resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
    if resp.status_code != 200:
        pytest.skip("GET /appconfig did not return 200 — skipping mutation tests")

    applications = resp.json().get("applications", [])
    if not applications:
        pytest.skip("No AppConfig applications found — skipping mutation tests")

    app = applications[0]
    original_logging = app.get("logging") or []

    yield app["name"], original_logging

    # Teardown: restore original logging config
    encoded = urllib.parse.quote(app["name"], safe="")
    requests.patch(
        f"{api_url}/appconfig/{encoded}",
        json={"logging": original_logging},
        headers=super_auth_headers,
        timeout=15,
    )


class TestPatchAppConfigMutation:
    def test_patch_returns_200_with_correct_shape(
        self, api_url, super_auth_headers, appconfig_application
    ):
        """PATCH /appconfig/{application} returns 200 with application, version, and logging."""
        app_name, original_logging = appconfig_application
        encoded = urllib.parse.quote(app_name, safe="")
        resp = requests.patch(
            f"{api_url}/appconfig/{encoded}",
            json={"logging": original_logging},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "application" in body, f"'application' missing from response: {body}"
        assert "version" in body, f"'version' missing from response: {body}"
        assert "logging" in body, f"'logging' missing from response: {body}"
        assert body["application"] == app_name

    def test_patch_updates_logging_reflected_in_get(
        self, api_url, super_auth_headers, appconfig_application
    ):
        """After PATCH, GET /appconfig reflects the updated logging rules."""
        app_name, _ = appconfig_application
        new_logging = [{"firefly-func": "WARNING"}]
        encoded = urllib.parse.quote(app_name, safe="")

        patch_resp = requests.patch(
            f"{api_url}/appconfig/{encoded}",
            json={"logging": new_logging},
            headers=super_auth_headers,
            timeout=15,
        )
        assert patch_resp.status_code == 200, (
            f"PATCH failed: {patch_resp.status_code}: {patch_resp.text}"
        )

        get_resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert get_resp.status_code == 200
        applications = get_resp.json()["applications"]
        match = next((a for a in applications if a["name"] == app_name), None)
        assert match is not None, f"Application '{app_name}' not found in GET /appconfig after PATCH"
        assert match["logging"] == new_logging, (
            f"Expected logging {new_logging}, got {match['logging']}"
        )

    def test_patch_levels_normalized_to_uppercase(
        self, api_url, super_auth_headers, appconfig_application
    ):
        """PATCH normalizes log levels to uppercase in the response."""
        app_name, _ = appconfig_application
        encoded = urllib.parse.quote(app_name, safe="")
        resp = requests.patch(
            f"{api_url}/appconfig/{encoded}",
            json={"logging": [{"firefly-func": "info"}]},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        rules = resp.json()["logging"]
        assert rules == [{"firefly-func": "INFO"}], (
            f"Expected level normalized to 'INFO', got {rules}"
        )

    def test_patch_empty_logging_clears_rules(
        self, api_url, super_auth_headers, appconfig_application
    ):
        """PATCH with an empty logging array is accepted and clears all rules."""
        app_name, _ = appconfig_application
        encoded = urllib.parse.quote(app_name, safe="")
        resp = requests.patch(
            f"{api_url}/appconfig/{encoded}",
            json={"logging": []},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["logging"] == []

    def test_patch_increments_version(
        self, api_url, super_auth_headers, appconfig_application
    ):
        """Each PATCH creates a new hosted configuration version (monotonically increasing)."""
        app_name, original_logging = appconfig_application
        encoded = urllib.parse.quote(app_name, safe="")

        resp1 = requests.patch(
            f"{api_url}/appconfig/{encoded}",
            json={"logging": original_logging},
            headers=super_auth_headers,
            timeout=15,
        )
        resp2 = requests.patch(
            f"{api_url}/appconfig/{encoded}",
            json={"logging": original_logging},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp2.json()["version"] > resp1.json()["version"], (
            f"Expected version to increment: v1={resp1.json()['version']}, v2={resp2.json()['version']}"
        )
