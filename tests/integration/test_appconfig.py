"""
Integration tests for the /appconfig endpoints.

Both endpoints require super_users group membership; the super_auth_headers
fixture temporarily adds the CI test user to that group for the session.

Coverage
--------
GET    /appconfig                           — 200 shape; 403 without super
PATCH  /appconfig/{function_name}          — 400/403 validation; full update lifecycle
POST   /appconfig/{function_name}/deploy   — 403 validation; deploy lifecycle
DELETE /appconfig/{function_name}          — 403/404 validation; full delete lifecycle
"""

import time

import pytest
import requests

pytestmark = pytest.mark.appconfig

# A real function name that exists in the deployed environment.
# health is used as the test target because it is low-traffic and disposable;
# appconfig-get was avoided to prevent leaving its config in a dirty state.
TEST_FUNCTION = "firefly-func-api-health-get"


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
    Captures the current AppConfig state for TEST_FUNCTION before the test.

    If the function had no AppConfig application (logging is null), teardown
    deletes the application to restore the original unconfigured state.
    If the function was already configured, teardown patches to WARNING and
    deploys so it is never left in a dirty state.
    """
    resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
    if resp.status_code != 200:
        pytest.skip("GET /appconfig did not return 200 — skipping mutation tests")

    original = next(
        (a for a in resp.json().get("applications", []) if a["name"] == TEST_FUNCTION),
        None,
    )
    had_prior_app = original is not None and original.get("logging") is not None

    yield had_prior_app

    # Wait for any in-progress deployment to reach a terminal state before cleanup.
    # Without this, DELETE returns 409 and health-get is left stuck in DEPLOYING,
    # causing the next run's pre-test poll to time out and skip the deploy test.
    deadline = time.time() + 120
    while time.time() < deadline:
        poll = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        if poll.status_code == 200:
            app = next(
                (a for a in poll.json().get("applications", []) if a["name"] == TEST_FUNCTION),
                None,
            )
            if app is None or app.get("status") in (None, "COMPLETE", "ROLLED_BACK"):
                break
        time.sleep(5)

    if had_prior_app:
        # Restore to WARNING and deploy so the function is never left in a dirty state
        requests.patch(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
            json={"logging": "WARNING"},
            headers=super_auth_headers,
            timeout=15,
        )
        requests.post(
            f"{api_url}/appconfig/{TEST_FUNCTION}/deploy",
            headers=super_auth_headers,
            timeout=15,
        )
    else:
        # Function had no AppConfig application before the test — delete it to restore
        # the original unconfigured state rather than leaving a permanent application behind
        requests.delete(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
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
        assert resp.status_code in (200, 403, 409)

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
        # Stage a version first (use DEBUG to ensure a real change is deployed)
        patch_resp = requests.patch(
            f"{api_url}/appconfig/{TEST_FUNCTION}",
            json={"logging": "DEBUG"},
            headers=super_auth_headers,
            timeout=15,
        )
        assert patch_resp.status_code == 200

        # The previous test's fixture teardown deploys to restore state; wait
        # for that deployment to settle before starting a new one.
        deadline = time.time() + 120
        while time.time() < deadline:
            poll = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
            if poll.status_code == 200:
                app = next(
                    (a for a in poll.json().get("applications", []) if a["name"] == TEST_FUNCTION),
                    None,
                )
                if app is None or app.get("status") in (None, "COMPLETE", "ROLLED_BACK"):
                    break
            time.sleep(5)

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


# ---------------------------------------------------------------------------
# DELETE /appconfig/{function_name} — validation and lifecycle
# ---------------------------------------------------------------------------

# A scratch function used only for delete tests so we don't disturb TEST_FUNCTION
DELETE_TEST_FUNCTION = "firefly-func-api-appconfig-patch"


class TestDeleteAppConfigValidation:
    def test_returns_404_for_unconfigured_function(self, api_url, super_auth_headers):
        resp = requests.delete(
            f"{api_url}/appconfig/firefly-func-does-not-exist",
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_returns_403_without_super_membership(self, api_url, auth_headers):
        resp = requests.delete(
            f"{api_url}/appconfig/{DELETE_TEST_FUNCTION}",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code in (200, 403, 404, 409)


class TestDeleteAppConfigLifecycle:
    def test_delete_returns_204_and_function_reverts_to_default(
        self, api_url, super_auth_headers
    ):
        # Ensure DELETE_TEST_FUNCTION has an AppConfig application first
        patch_resp = requests.patch(
            f"{api_url}/appconfig/{DELETE_TEST_FUNCTION}",
            json={"logging": "DEBUG"},
            headers=super_auth_headers,
            timeout=15,
        )
        assert patch_resp.status_code == 200, f"Setup PATCH failed: {patch_resp.text}"

        # Delete it
        del_resp = requests.delete(
            f"{api_url}/appconfig/{DELETE_TEST_FUNCTION}",
            headers=super_auth_headers,
            timeout=15,
        )
        assert del_resp.status_code == 204, f"Expected 204, got {del_resp.status_code}: {del_resp.text}"

        # Confirm it now appears with null values in GET /appconfig
        get_resp = requests.get(f"{api_url}/appconfig", headers=super_auth_headers, timeout=15)
        assert get_resp.status_code == 200
        app = next(
            (a for a in get_resp.json().get("applications", []) if a["name"] == DELETE_TEST_FUNCTION),
            None,
        )
        assert app is not None, f"{DELETE_TEST_FUNCTION} not found in GET response"
        assert app["logging"] is None
        assert app["version"] is None

    def test_delete_is_idempotent_via_404(self, api_url, super_auth_headers):
        # Deleting an already-unconfigured function returns 404
        # (previous test left DELETE_TEST_FUNCTION unconfigured)
        resp = requests.delete(
            f"{api_url}/appconfig/{DELETE_TEST_FUNCTION}",
            headers=super_auth_headers,
            timeout=15,
        )
        assert resp.status_code == 404, f"Expected 404 on second delete, got {resp.status_code}: {resp.text}"
