from __future__ import annotations

import os
from ipaddress import ip_address, ip_network
from typing import Iterable

_DEFAULT_TRUSTED_PROXY_CIDRS = ("127.0.0.1/32", "::1/128")


def _normalize_cidr_values(values: Iterable[str]) -> tuple:
    networks = []
    for raw in values:
        candidate = str(raw or "").strip()
        if not candidate:
            continue
        try:
            networks.append(ip_network(candidate, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def trusted_proxy_networks(
    env_name: str = "CODE_PLATFORM_TRUSTED_PROXY_CIDRS",
    *,
    default: tuple[str, ...] = _DEFAULT_TRUSTED_PROXY_CIDRS,
) -> tuple:
    raw = os.getenv(env_name)
    if raw is None:
        return _normalize_cidr_values(default)
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    return _normalize_cidr_values(values or default)


def is_trusted_forwarded_for_source(host: str, *, networks: tuple | None = None) -> bool:
    normalized = str(host or "").strip()
    if not normalized:
        return False
    if normalized.lower() == "localhost":
        return True
    try:
        address = ip_address(normalized)
    except ValueError:
        return False
    trusted_networks = networks if networks is not None else trusted_proxy_networks()
    return any(address in network for network in trusted_networks)


def extract_forwarded_client_ip(
    *,
    client_host: str,
    x_forwarded_for: str | None = None,
    x_real_ip: str | None = None,
    networks: tuple | None = None,
) -> str | None:
    if not is_trusted_forwarded_for_source(client_host, networks=networks):
        return None

    first_forwarded = (x_forwarded_for or "").split(",", 1)[0].strip()
    real_ip = str(x_real_ip or "").strip()
    for candidate in (first_forwarded, real_ip):
        if not candidate:
            continue
        try:
            ip_address(candidate)
        except ValueError:
            continue
        return candidate
    return None
