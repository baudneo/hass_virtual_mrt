"""The base device info used to seed entities"""

from typing import Iterable


async def get_device_info(identifier: Iterable, name: str):
    device_info = {
        "identifiers": identifier,
        "name": name,
        "manufacturer": "Virtual MRT/T_op",
        "model": "Configurable Room",
    }

    return device_info
