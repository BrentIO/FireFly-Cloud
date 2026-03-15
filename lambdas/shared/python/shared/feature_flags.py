from .app_config import get_appconfig

def is_enabled(flag_name, feature_config=None):
    """
    Returns True if the feature flag is enabled.
    Optionally pass in pre-fetched config to avoid extra fetch.

    Example Configuration:
    ```
    {
        "foo": "bar",
        "baz": true
    }
    ```
    """
    cfg = feature_config or get_appconfig(profile="features")
    return cfg.get(flag_name, False)