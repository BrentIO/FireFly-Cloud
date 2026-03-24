import os
import json
import urllib3

_http = urllib3.PoolManager()

def get_appconfig(profile=None):
    """
    Fetch AppConfig JSON via Lambda AppConfig Extension.
    Returns empty dict/list if unavailable.
    """
    app = "firefly"
    env = os.environ.get("APP_CONFIG_ENV", "")

    url = (
        f"http://localhost:2772/applications/{app}/environments/{env}/configurations/{profile}"
    )

    try:
        response = _http.request(
            "GET",
            url,
            timeout=urllib3.Timeout(connect=1.0, read=2.0)
        )

        if response.status != 200:
            return {}

        data = response.data.decode("utf-8")
        return json.loads(data) if data else {}

    except Exception:
        return {}
