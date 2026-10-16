"""Device backends."""

from home_control.backends.base import Backend, BackendError
from home_control.backends.tuya_lan import TuyaLanBackend


def default_backends() -> dict[str, Backend]:
    """Backends this version can drive, by config name."""
    return {"tuya_lan": TuyaLanBackend()}


__all__ = ["Backend", "BackendError", "TuyaLanBackend", "default_backends"]
