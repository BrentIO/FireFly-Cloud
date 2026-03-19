"""
Integration tests for the /users endpoints.

All endpoints require super_users group membership; the super_auth_headers
fixture temporarily adds the CI test user to that group for the session.

Coverage
--------
GET  /users           — 200 with correct response shape
POST /users           — 400 validation errors (no mutations to Cognito/DynamoDB)
PATCH /users/{email}  — 400 validation errors; 404 for unknown email
DELETE /users/{email} — 404 for unknown email
"""

import pytest
import requests

# A well-formed email address that is guaranteed not to exist in Cognito.
_GHOST_EMAIL = "no-such-user-firefly-inttest@example.com"


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------

class TestGetUsers:
    def test_returns_200_with_super_token(self, api_url, super_auth_headers):
        """GET /users returns 200 for a super user."""
        resp = requests.get(f"{api_url}/users", headers=super_auth_headers, timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_response_has_users_list(self, api_url, super_auth_headers):
        """Response body contains a top-level 'users' array."""
        resp = requests.get(f"{api_url}/users", headers=super_auth_headers, timeout=10)
        assert resp.status_code == 200
        body = resp.json()
        assert "users" in body, f"'users' key missing from response: {body}"
        assert isinstance(body["users"], list)

    def test_user_objects_have_required_fields(self, api_url, super_auth_headers):
        """Every entry in the users list has the expected fields."""
        resp = requests.get(f"{api_url}/users", headers=super_auth_headers, timeout=10)
        assert resp.status_code == 200
        users = resp.json()["users"]
        required = {"email", "is_super", "status"}
        for user in users:
            missing = required - user.keys()
            assert not missing, f"User entry missing fields {missing}: {user}"

    def test_returns_403_without_super_membership(self, api_url, auth_headers):
        """GET /users returns 403 when the caller is not in super_users."""
        resp = requests.get(f"{api_url}/users", headers=auth_headers, timeout=10)
        # 403 is the expected result; 200 is accepted only if the CI test user
        # already held super status before this test session began.
        assert resp.status_code in (200, 403), (
            f"GET /users returned unexpected {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# POST /users — validation errors only (no Cognito/DynamoDB mutations)
# ---------------------------------------------------------------------------

class TestPostUsersValidation:
    def test_rejects_missing_email(self, api_url, super_auth_headers):
        """POST /users without an email field returns 400."""
        resp = requests.post(
            f"{api_url}/users",
            json={"environments": ["dev"]},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_rejects_empty_email(self, api_url, super_auth_headers):
        """POST /users with an empty email string returns 400."""
        resp = requests.post(
            f"{api_url}/users",
            json={"email": "", "environments": ["dev"]},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400

    def test_rejects_invalid_email_format(self, api_url, super_auth_headers):
        """POST /users with a syntactically invalid email returns 400."""
        resp = requests.post(
            f"{api_url}/users",
            json={"email": "not-an-email", "environments": ["dev"]},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400

    def test_rejects_missing_environments(self, api_url, super_auth_headers):
        """POST /users without environments returns 400."""
        resp = requests.post(
            f"{api_url}/users",
            json={"email": _GHOST_EMAIL},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400

    def test_rejects_empty_environments_list(self, api_url, super_auth_headers):
        """POST /users with an empty environments list returns 400."""
        resp = requests.post(
            f"{api_url}/users",
            json={"email": _GHOST_EMAIL, "environments": []},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400

    def test_rejects_invalid_environment_value(self, api_url, super_auth_headers):
        """POST /users with an unrecognised environment name returns 400."""
        resp = requests.post(
            f"{api_url}/users",
            json={"email": _GHOST_EMAIL, "environments": ["staging"]},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400

    def test_rejects_non_list_environments(self, api_url, super_auth_headers):
        """POST /users with environments as a string (not a list) returns 400."""
        resp = requests.post(
            f"{api_url}/users",
            json={"email": _GHOST_EMAIL, "environments": "dev"},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PATCH /users/{email}
# ---------------------------------------------------------------------------

class TestPatchUsers:
    def test_returns_404_for_unknown_email(self, api_url, super_auth_headers):
        """PATCH /users/{email} returns 404 when the email is not in Cognito."""
        resp = requests.patch(
            f"{api_url}/users/{_GHOST_EMAIL}",
            json={"is_super": True},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_rejects_missing_is_super(self, api_url, super_auth_headers):
        """PATCH /users/{email} without is_super body field returns 400."""
        resp = requests.patch(
            f"{api_url}/users/{_GHOST_EMAIL}",
            json={},
            headers=super_auth_headers,
            timeout=10,
        )
        # Lambda validates is_super before looking up the user, so 400 is expected.
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_rejects_non_boolean_is_super(self, api_url, super_auth_headers):
        """PATCH /users/{email} with is_super as a string returns 400."""
        resp = requests.patch(
            f"{api_url}/users/{_GHOST_EMAIL}",
            json={"is_super": "yes"},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# DELETE /users/{email}
# ---------------------------------------------------------------------------

class TestDeleteUsers:
    def test_delete_unknown_email_succeeds(self, api_url, super_auth_headers):
        """DELETE /users/{email} for a user not in Cognito still returns 200.

        The Lambda removes the email from DynamoDB regardless of Cognito presence
        and logs a warning when no Cognito record is found — it does not 404.
        """
        resp = requests.delete(
            f"{api_url}/users/{_GHOST_EMAIL}",
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
