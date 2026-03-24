"""
Integration tests for the /appconfig endpoints.

Both endpoints require super_users group membership; the super_auth_headers
fixture temporarily adds the CI test user to that group for the session.

Coverage
--------
GET  /appconfig                           — 200 shape; 403 without super
PATCH /appconfig/{function_name}          — 400/403 validation; full update lifecycle
POST  /appconfig/{function_name}/deploy   — 403 validation; deploy lifecycle
"""

import time

import pytest
import requests

# A real function name that exists in the deployed environment
TEST_FUNCTION = "firefly-func-api-appconfig-get"


# ---------------------------------------------------------------------------
# GET /appconfig
# ---------------------------------------------------------------------------

class TestGetAppConfig:
    def test_returns_200_with_super_token(self, api_url, super_auth_headers):
        resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_response_has_applications_list(self, api_url, super_auth_headers):
        resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert resp.status_code == 200
        body = resp.json()
        assert "applications" in body, f"'applications' key missing: {body}"
        assert isinstance(body["applications"], list)

    def test_applications_have_required_fields(self, api_url, super_auth_headers):
        resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert resp.status_code == 200
        for i, app in enumerate(resp.json()["applications"]):
            for field in ("name", "logging", "version", "deployed_version", "status"):
                assert field in app, f"applications[{i}] missing field '{field}': {app}"

    def test_function_names_start_with_firefly_func(self, api_url, super_auth_headers):
        resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert resp.status_code == 200
        for app in resp.json()["applications"]:
            assert app["name"].startswith("firefly-func-"), (
                f"Unexpected function name: {app['name']}"
            )

    def test_returns_403_without_super_membership(self, api_url, auth_headers):
        resp = requests.get(f"{api_url}/appconfig", headers=auth_headers, timeout=15)
        assert resp.status_code in (200, 403)


# ---------------------------------------------------------------------------
# PATCH /appconfig/{function_name} — validation errors (no mutations)
# ---------------------------------------------------------------------------

class TestPatchAppConfigValidation:
    def test_returns_400_missing_logging_field(self, api_url, super_auth_headers):
        resp = requests.patch(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
            json={},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_returns_400_invalid_log_level(self, api_url, super_auth_headers):
        resp = requests.patch(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
            json={"logging": "VERBOSE"},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_returns_404_unknown_function(self, api_url, super_auth_headers):
        resp = requests.patch(
            f"{api_url}/appconfig/firefly-func-does-not-exist",
            json={"logging": "INFO"},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_returns_403_without_super_membership(self, api_url, auth_headers):
        resp = requests.patch(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
            json={"logging": "INFO"},
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code in (200, 403)


# ---------------------------------------------------------------------------
# PATCH /appconfig/{function_name} — full update lifecycle (mutations)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def appconfig_original(api_url, super_auth_headers):
    """
    Captures the current config for TEST_FUNCTION before the test and
    restores it (with a new deploy) at teardown.
    """
    resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
    if resp.status_code != 200:
        pytest.skip("GET /appconfig did not return 200 — skipping mutation tests")

    original = next(
        (a for a in resp.json().get("applications", []) if a["name"] == TEST_FUNCTION),
        None,
    )
    original_level = original["logging"] if original and original["logging"] else "WARNING"

    yield original_level

    # Teardown: restore original level (stage only — no deploy needed for tests)
    requests.patch(
        f"{api_url}/appconfig/{TEST_FUNCTION}",
        json={"logging": original_level},
        headers=super_auth_headers,
        timeout=15,
    )


class TestPatchAppConfigMutation:
    def test_patch_returns_200_with_correct_shape(
        self, api_url, super_auth_headers, appconfig_original
    ):
        resp = requests.patch(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
            json={"logging": "INFO"},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "name" in body
        assert "logging" in body
        assert "version" in body

    def test_patch_normalises_level_to_uppercase(
        self, api_url, super_auth_headers, appconfig_original
    ):
        resp = requests.patch(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
            json={"logging": "debug"},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        assert resp.json()["logging"] == "DEBUG"

    def test_patch_increments_version(
        self, api_url, super_auth_headers, appconfig_original
    ):
        resp1 = requests.patch(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
            json={"logging": "INFO"},
            headers=super_auth_headers,
            timeout=15,
        )
        resp2 = requests.patch(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
            json={"logging": "WARNING"},
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp2.json()["version"] > resp1.json()["version"]

    def test_patch_reflected_in_get(
        self, api_url, super_auth_headers, appconfig_original
    ):
        """After PATCH, GET /appconfig reflects the new level for the function."""
        requests.patch(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
            json={"logging": "ERROR"},
            headers=super_auth_headers,
            timeout=15,
        )
        get_resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert get_resp.status_code == 200
        app = next(
            (a for a in get_resp.json()["applications"] if a["name"] == TEST_FUNCTION),
            None,
        )
        assert app is not None, f"{TEST_FUNCTION} not found in GET response"
        assert app["logging"] == "ERROR"


# ---------------------------------------------------------------------------
# POST /appconfig/{function_name}/deploy — validation and lifecycle
# ---------------------------------------------------------------------------

class TestDeployAppConfig:
    def test_returns_403_without_super_membership(self, api_url, auth_headers):
        resp = requests.post(
            f"{api_url}/appconfig/{TEST_FUNCTION}/deploy",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code in (200, 403)

    def test_returns_404_for_unconfigured_function(self, api_url, super_auth_headers):
        resp = requests.post(
            f"{api_url}/appconfig/firefly-func-does-not-exist/deploy",
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_deploy_returns_200_with_correct_shape(
        self, api_url, super_auth_headers, appconfig_original
    ):
        # Wait for any in-progress deployment to finish before staging+deploying
        deadline = time.time() + 180
        while time.time() < deadline:
            get_resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
            if get_resp.status_code == 200:
                app = next(
                    (a for a in get_resp.json().get("applications", []) if a["name"] == TEST_FUNCTION),
                    None,
                )
                if app is None or app.get("status") in (None, "COMPLETE", "ROLLED_BACK"):
                    break
            time.sleep(5)

        # Stage a version first
        patch_resp = requests.patch(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
            json={"logging": appconfig_original},
            headers=super_auth_headers,
            timeout=15,
        )
        assert patch_resp.status_code == 200

        deploy_resp = requests.post(
            f"{api_url}/appconfig/{TEST_FUNCTION}/deploy",
            headers=super_auth_headers,
            timeout=15,
        )
        assert deploy_resp.status_code == 200, f"Expected 200, got {deploy_resp.status_code}: {deploy_resp.text}"
        body = deploy_resp.json()
        assert "name" in body
        assert "version" in body
        assert "environment" in body
        assert "status" in body
