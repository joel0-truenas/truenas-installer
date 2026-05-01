import dataclasses
import ipaddress
import logging
import socket

from truenas_pynetif.address import get_addresses, get_links, netlink_route
from truenas_pynetif.netlink import DumpInterrupted

logger = logging.getLogger(__name__)


__all__ = ["list_network_interfaces", "get_available_ip_addresses"]


@dataclasses.dataclass
class NetworkInterface:
    name: str


async def list_network_interfaces():
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            with netlink_route() as sock:
                links = get_links(sock)
            break
        except DumpInterrupted:
            if attempt < max_retries:
                continue
            raise

    return [NetworkInterface(name) for name in links if name != "lo"]


async def _get_ip_addresses_with_filter(interface_filter=None):
    """
    Get IP addresses with optional interface filtering.

    Args:
        interface_filter: None to get all interfaces, or a list of interface names to filter

    Returns:
        dict: {"ipv4": [...], "ipv6": [...]}
    """
    result = {"ipv4": [], "ipv6": []}

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            with netlink_route() as sock:
                addresses = get_addresses(sock)
            break
        except DumpInterrupted:
            if attempt < max_retries:
                continue
            logger.error("Failed to get IP addresses after %d retries due to DumpInterrupted", max_retries)
            return result
        except Exception as e:
            if interface_filter:
                logger.error("Error getting IP addresses for interfaces %s: %s", interface_filter, e, exc_info=True)
            else:
                logger.error("Error getting IP addresses: %s", e, exc_info=True)
            return result

    all_ipv4 = ipaddress.ip_address("0.0.0.0")
    all_ipv6 = ipaddress.ip_address("::")
    for addr in addresses:
        if not addr.ifname:
            continue

        if interface_filter is None:
            if addr.ifname == "lo":
                continue
        elif addr.ifname not in interface_filter:
            continue

        try:
            ip_obj = ipaddress.ip_address(addr.address)
        except ValueError:
            continue

        if any(
            (
                (ip_obj == all_ipv4),  # 0.0.0.0 invalid
                (ip_obj == all_ipv6),  # :: invalid
                (ip_obj.is_loopback),
                (ip_obj.is_link_local),
                (ip_obj.is_multicast),
            )
        ):
            if addr.family == socket.AF_INET:
                if addr.address not in result["ipv4"]:
                    result["ipv4"].append(addr.address)
            if addr.family == socket.AF_INET6:
                if addr.address not in result["ipv6"]:
                    result["ipv6"].append(addr.address)

    return result


async def get_available_ip_addresses():
    """
    Get all available IP addresses on the system that can be used to connect from another machine.
    Excludes loopback, link-local, and wildcard addresses.

    Returns:
        dict: {"ipv4": [...], "ipv6": [...]}
    """
    return await _get_ip_addresses_with_filter(interface_filter=None)
