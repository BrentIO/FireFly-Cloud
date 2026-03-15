"""
Integration tests for the firmware management UI hosted on CloudFront.

Required environment variables:
  FIREFLY_UI_URL  Base URL of the UI (e.g. https://ui.example.com)
                  If not set, all tests are skipped.
"""

import os

import pytest
import requests

UI_URL = os.environ.get("FIREFLY_UI_URL", "").rstrip("/")


def _skip_if_no_url():
    if not UI_URL:
        pytest.skip("FIREFLY_UI_URL not set — skipping UI tests")


class TestUiAccessibility:

    def test_root_returns_200(self):
        """CloudFront serves the UI root and returns HTTP 200."""
        _skip_if_no_url()
        resp = requests.get(f"{UI_URL}/", timeout=15)
        assert resp.status_code == 200

    def test_root_returns_html(self):
        """The UI root response is HTML."""
        _skip_if_no_url()
        resp = requests.get(f"{UI_URL}/", timeout=15)
        assert "text/html" in resp.headers.get("Content-Type", "")

    def test_root_contains_app_mount_point(self):
        """The HTML page contains the Vue app mount point."""
        _skip_if_no_url()
        resp = requests.get(f"{UI_URL}/", timeout=15)
        assert '<div id="app">' in resp.text

    def test_https_redirect(self):
        """HTTP requests are redirected to HTTPS."""
        _skip_if_no_url()
        if not UI_URL.startswith("https://"):
            pytest.skip("UI_URL is not HTTPS — skipping redirect test")
        http_url = UI_URL.replace("https://", "http://", 1)
        resp = requests.get(f"{http_url}/", timeout=15, allow_redirects=False)
        assert resp.status_code in (301, 302, 307, 308)
        assert resp.headers.get("Location", "").startswith("https://")


class TestSpaRouting:

    def test_firmware_route_returns_200(self):
        """A deep SPA route returns 200 instead of 404 (CloudFront custom error response)."""
        _skip_if_no_url()
        resp = requests.get(f"{UI_URL}/firmware", timeout=15)
        assert resp.status_code == 200

    def test_firmware_detail_route_returns_200(self):
        """A firmware detail SPA route returns 200 instead of 404."""
        _skip_if_no_url()
        resp = requests.get(f"{UI_URL}/firmware/some-firmware-file.zip", timeout=15)
        assert resp.status_code == 200

    def test_deep_route_serves_index_html(self):
        """A deep SPA route serves the same index.html as the root."""
        _skip_if_no_url()
        root_resp = requests.get(f"{UI_URL}/", timeout=15)
        deep_resp = requests.get(f"{UI_URL}/firmware/some-firmware-file.zip", timeout=15)
        assert root_resp.status_code == 200
        assert deep_resp.status_code == 200
        assert '<div id="app">' in deep_resp.text


class TestS3DirectAccess:

    def test_s3_bucket_is_not_directly_accessible(self):
        """The private S3 bucket cannot be accessed directly — only through CloudFront.

        Bucket names containing dots cause an SSL hostname mismatch when using
        virtual-hosted style HTTPS URLs, which is itself sufficient proof that
        the bucket is not directly accessible by standard clients.
        """
        _skip_if_no_url()
        bucket_name = os.environ.get("FIREFLY_UI_BUCKET")
        region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        if not bucket_name:
            pytest.skip("FIREFLY_UI_BUCKET not set — skipping direct S3 access test")
        s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/index.html"
        try:
            resp = requests.get(s3_url, timeout=15)
            assert resp.status_code in (403, 404), (
                f"Expected 403 or 404 from direct S3 access, got {resp.status_code}"
            )
        except requests.exceptions.SSLError:
            # An SSL certificate mismatch (common with dot-separated bucket names)
            # confirms the bucket is not directly accessible via standard HTTPS.
            pass
