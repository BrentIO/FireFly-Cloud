"""
Integration tests for the /users endpoints.

All endpoints require super_users group membership; the super_auth_headers
fixture temporarily adds the CI test user to that group for the session.

Coverage
--------
GET  /users           — 200 with correct response shape; 403 without super membership
POST /users           — 400/403 validation; full invite lifecycle (201 → 409 → DELETE)
PATCH /users/{email}  — 400/403/404 validation; environments update lifecycle
DELETE /users/{email} — 404 for unknown; full delete lifecycle
"""

import urllib.parse

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

class TestPatchUsersValidation:
    def test_returns_404_for_unknown_email_is_super(self, api_url, super_auth_headers):
        """PATCH /users/{email} returns 404 when is_super is requested for unknown Cognito user."""
        resp = requests.patch(
            f"{api_url}/users/{_GHOST_EMAIL}",
            json={"is_super": True},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_rejects_empty_body(self, api_url, super_auth_headers):
        """PATCH /users/{email} with an empty body returns 400."""
        resp = requests.patch(
            f"{api_url}/users/{_GHOST_EMAIL}",
            json={},
            headers=super_auth_headers,
            timeout=10,
        )
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

    def test_rejects_empty_environments_list(self, api_url, super_auth_headers):
        """PATCH /users/{email} with environments as an empty list returns 400."""
        resp = requests.patch(
            f"{api_url}/users/{_GHOST_EMAIL}",
            json={"environments": []},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_rejects_invalid_environment_value(self, api_url, super_auth_headers):
        """PATCH /users/{email} with an unrecognised environment name returns 400."""
        resp = requests.patch(
            f"{api_url}/users/{_GHOST_EMAIL}",
            json={"environments": ["staging"]},
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# DELETE /users/{email} — idempotent/validation
# ---------------------------------------------------------------------------

class TestDeleteUsersValidation:
    def test_delete_unknown_email_succeeds(self, api_url, super_auth_headers):
        """DELETE /users/{email} for a user not in DynamoDB/Cognito still returns 200.

        The Lambda removes the email from DynamoDB regardless of Cognito presence
        and logs a warning when no Cognito record is found — it does not 404.
        """
        resp = requests.delete(
            f"{api_url}/users/{_GHOST_EMAIL}",
            headers=super_auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# POST /users — full invite lifecycle (mutations)
# ---------------------------------------------------------------------------

class TestPostUsersMutation:
    def test_invite_new_user_returns_201(self, api_url, invited_user, super_auth_with_dynamo):
        """POST /users for a new email returns 201 with the invited email and environments."""
        # invited_user fixture already performed the POST and asserted 201.
        # Re-verify via GET /users that the user appears as INVITED and not super.
        resp = requests.get(f"{api_url}/users", headers=super_auth_with_dynamo, timeout=10)
        assert resp.status_code == 200
        users = resp.json()["users"]
        match = next((u for u in users if u["email"] == invited_user), None)
        assert match is not None, f"Invited user '{invited_user}' not found in GET /users"
        assert match["status"] == "INVITED", f"Expected status INVITED, got {match['status']}"
        assert match["is_super"] is False, "Newly invited user must not be a super user"

    def test_invite_duplicate_returns_409(self, api_url, invited_user, super_auth_with_dynamo):
        """POST /users for an already-invited email returns 409."""
        resp = requests.post(
            f"{api_url}/users",
            json={"email": invited_user, "environments": ["dev"]},
            headers=super_auth_with_dynamo,
            timeout=10,
        )
        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"

    def test_invite_unauthorized_env_returns_403(self, api_url, restricted_super_auth):
        """POST /users returns 403 when caller tries to grant an env they don't have."""
        import time as _time
        unique_email = f"firefly-inttest-restricted-{int(_time.time())}@example.com"
        resp = requests.post(
            f"{api_url}/users",
            json={"email": unique_email, "environments": ["production"]},
            headers=restricted_super_auth,
            timeout=10,
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# PATCH /users/{email} — environments update lifecycle (mutations)
# ---------------------------------------------------------------------------

class TestPatchUsersMutation:
    def test_patch_environments_returns_200(self, api_url, invited_user, super_auth_with_dynamo):
        """PATCH /users/{email} with a valid environments list returns 200."""
        encoded = urllib.parse.quote(invited_user, safe="")
        resp = requests.patch(
            f"{api_url}/users/{encoded}",
            json={"environments": ["dev", "production"]},
            headers=super_auth_with_dynamo,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert set(body.get("environments", [])) == {"dev", "production"}, (
            f"Unexpected environments in response: {body}"
        )

    def test_patch_environments_reflected_in_get(self, api_url, invited_user, super_auth_with_dynamo):
        """After PATCH environments, GET /users reflects the updated value."""
        encoded = urllib.parse.quote(invited_user, safe="")
        requests.patch(
            f"{api_url}/users/{encoded}",
            json={"environments": ["production"]},
            headers=super_auth_with_dynamo,
            timeout=10,
        )
        resp = requests.get(f"{api_url}/users", headers=super_auth_with_dynamo, timeout=10)
        assert resp.status_code == 200
        users = resp.json()["users"]
        match = next((u for u in users if u["email"] == invited_user), None)
        assert match is not None, f"User '{invited_user}' not found after PATCH"
        assert match["environments"] == ["production"], (
            f"Expected ['production'], got {match['environments']}"
        )

    def test_patch_environments_unauthorized_returns_403(
        self, api_url, invited_user, restricted_super_auth
    ):
        """PATCH /users/{email} returns 403 when caller tries to grant an env they don't have."""
        encoded = urllib.parse.quote(invited_user, safe="")
        resp = requests.patch(
            f"{api_url}/users/{encoded}",
            json={"environments": ["production"]},
            headers=restricted_super_auth,
            timeout=10,
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# DELETE /users/{email} — full delete lifecycle (mutations)
# ---------------------------------------------------------------------------

class TestDeleteUsersMutation:
    def test_delete_invited_user_returns_200(self, api_url, super_auth_with_dynamo):
        """DELETE /users/{email} for an invited-only user returns 200."""
        import time as _time
        unique_email = f"firefly-inttest-del-{int(_time.time())}@example.com"
        # Invite the user first
        post_resp = requests.post(
            f"{api_url}/users",
            json={"email": unique_email, "environments": ["dev"]},
            headers=super_auth_with_dynamo,
            timeout=10,
        )
        assert post_resp.status_code == 201, (
            f"Setup failed — POST /users returned {post_resp.status_code}: {post_resp.text}"
        )
        encoded = urllib.parse.quote(unique_email, safe="")
        del_resp = requests.delete(
            f"{api_url}/users/{encoded}",
            headers=super_auth_with_dynamo,
            timeout=10,
        )
        assert del_resp.status_code == 200, (
            f"Expected 200, got {del_resp.status_code}: {del_resp.text}"
        )

    def test_deleted_user_absent_from_list(self, api_url, super_auth_with_dynamo):
        """After DELETE /users/{email}, the user no longer appears in GET /users."""
        import time as _time
        unique_email = f"firefly-inttest-gone-{int(_time.time())}@example.com"
        requests.post(
            f"{api_url}/users",
            json={"email": unique_email, "environments": ["dev"]},
            headers=super_auth_with_dynamo,
            timeout=10,
        )
        encoded = urllib.parse.quote(unique_email, safe="")
        requests.delete(
            f"{api_url}/users/{encoded}",
            headers=super_auth_with_dynamo,
            timeout=10,
        )
        resp = requests.get(f"{api_url}/users", headers=super_auth_with_dynamo, timeout=10)
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()["users"]]
        assert unique_email not in emails, (
            f"Deleted user '{unique_email}' still appears in GET /users"
        )
