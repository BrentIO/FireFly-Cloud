import requests


def test_health_returns_200(api_url):
    resp = requests.get(f"{api_url}/health", timeout=10)
    assert resp.status_code == 200


def test_health_response_body(api_url):
    resp = requests.get(f"{api_url}/health", timeout=10)
    assert resp.json() == {"status": "OK"}


def test_health_content_type(api_url):
    resp = requests.get(f"{api_url}/health", timeout=10)
    assert "application/json" in resp.headers.get("Content-Type", "")
