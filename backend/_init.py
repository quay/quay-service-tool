import os


def _get_version_number():
    """
    Stub version function for Quay compatibility.
    Returns version from env var or a default.
    """
    return os.getenv("QUAY_VERSION", "3.13.0")
