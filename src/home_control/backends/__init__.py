"""Device backends."""

from home_control.backends.base import Backend, BackendError
from home_control.backends.tuya_lan import TuyaLanBackend
from home_control.backends.zigbee2mqtt import Zigbee2MqttBackend


def default_backends() -> dict[str, Backend]:
    """Backends this version can drive, by config name."""
    return {"tuya_lan": TuyaLanBackend(), "zigbee2mqtt": Zigbee2MqttBackend()}


__all__ = ["Backend", "BackendError", "TuyaLanBackend", "Zigbee2MqttBackend", "default_backends"]
