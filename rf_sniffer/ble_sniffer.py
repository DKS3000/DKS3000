"""Passive Bluetooth Low Energy (BLE) advertisement capture via bleak.

Requires:
  - Linux BlueZ (built into Raspberry Pi OS) for the built-in adapter,
    or a USB BLE dongle. A high-gain external BLE/BT dongle with its own
    antenna extends effective range well beyond the Pi's onboard chip.
  - Usually no root privileges needed (unlike raw WiFi monitor mode),
    though some BlueZ setups require the user to be in the `bluetooth`
    group or need `sudo setcap` on the Python interpreter.

Only use against devices you own or are explicitly authorized to assess.
"""

import asyncio
from typing import Optional

from .models import BleObservation
from .oui import lookup_ble_company


def parse_advertisement(device, advertisement_data) -> BleObservation:
    """Turn one bleak (device, advertisement_data) pair into an observation."""
    manufacturer_ids = list(advertisement_data.manufacturer_data.keys())
    vendor = None
    for company_id in manufacturer_ids:
        vendor = lookup_ble_company(company_id)
        if vendor:
            break

    return BleObservation(
        address=device.address,
        name=advertisement_data.local_name or device.name,
        rssi=advertisement_data.rssi,
        tx_power=advertisement_data.tx_power,
        manufacturer_ids=manufacturer_ids,
        service_uuids=list(advertisement_data.service_uuids),
        vendor=vendor,
    )


async def _scan(logger, duration: Optional[float]) -> int:
    from bleak import BleakScanner

    count = 0

    def _on_detect(device, advertisement_data):
        nonlocal count
        logger.write(parse_advertisement(device, advertisement_data))
        count += 1

    async with BleakScanner(_on_detect):
        if duration is not None:
            await asyncio.sleep(duration)
        else:
            # Run until interrupted (Ctrl-C).
            try:
                while True:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass

    return count


def run_ble_sniffer(logger, duration: Optional[float] = None) -> int:
    """Scan for BLE advertisements, logging each via `logger.write(...)`."""
    return asyncio.run(_scan(logger, duration))
