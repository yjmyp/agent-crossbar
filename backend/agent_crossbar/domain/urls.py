from __future__ import annotations

import ipaddress


def is_loopback_host(hostname: str | None) -> bool:
    """Return True for localhost and any IPv4/IPv6 loopback address."""
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback
