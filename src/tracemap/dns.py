"""
Reverse DNS resolution with caching and async support.

Author: gadwant
"""

from __future__ import annotations

import asyncio
import socket
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Dict, List, Optional, Tuple


@lru_cache(maxsize=10000)
def reverse_dns(ip: str, timeout: float = 2.0) -> Optional[str]:
    """
    Perform reverse DNS lookup for an IP address.

    Args:
        ip: IP address to look up
        timeout: Timeout in seconds

    Returns:
        Hostname if found, None otherwise
    """
    try:
        socket.setdefaulttimeout(timeout)
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, socket.timeout, OSError):
        return None


def reverse_dns_batch(
    ips: List[str], timeout: float = 2.0, max_workers: int = 10
) -> Dict[str, Optional[str]]:
    """
    Perform reverse DNS lookups for multiple IPs in parallel.

    Args:
        ips: List of IP addresses
        timeout: Timeout per lookup in seconds
        max_workers: Maximum parallel workers

    Returns:
        Dictionary mapping IP to hostname (or None)
    """
    results: Dict[str, Optional[str]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(reverse_dns, ip, timeout): ip for ip in ips}

        for future in futures:
            ip = futures[future]
            try:
                results[ip] = future.result()
            except Exception:
                results[ip] = None

    return results


async def reverse_dns_async(ip: str, timeout: float = 2.0) -> Optional[str]:
    """
    Async reverse DNS lookup.

    Args:
        ip: IP address to look up
        timeout: Timeout in seconds

    Returns:
        Hostname if found, None otherwise
    """
    loop = asyncio.get_event_loop()

    try:
        # Run blocking DNS lookup in thread pool
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: reverse_dns(ip, timeout)),
            timeout=timeout,
        )
        return result
    except (asyncio.TimeoutError, Exception):
        return None


async def reverse_dns_batch_async(
    ips: List[str], timeout: float = 2.0, concurrency: int = 20
) -> Dict[str, Optional[str]]:
    """
    Async batch reverse DNS lookup with concurrency limit.

    Args:
        ips: List of IP addresses
        timeout: Timeout per lookup in seconds
        concurrency: Maximum concurrent lookups

    Returns:
        Dictionary mapping IP to hostname (or None)
    """
    semaphore = asyncio.Semaphore(concurrency)
    results: Dict[str, Optional[str]] = {}

    async def lookup_with_semaphore(ip: str) -> Tuple[str, Optional[str]]:
        async with semaphore:
            hostname = await reverse_dns_async(ip, timeout)
            return ip, hostname

    tasks = [lookup_with_semaphore(ip) for ip in ips]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    for result in completed:
        if isinstance(result, tuple):
            ip, hostname = result
            results[ip] = hostname
        # Ignore exceptions, IP will be missing from results

    return results


class DNSCache:
    """
    DNS cache with TTL support.

    Note: For simplicity, we don't implement TTL expiry here.
    The lru_cache on reverse_dns provides basic caching.
    """

    def __init__(self, maxsize: int = 10000):
        self._cache: Dict[str, Optional[str]] = {}
        self._maxsize = maxsize

    def get(self, ip: str) -> Tuple[bool, Optional[str]]:
        """
        Get cached hostname.

        Returns:
            Tuple of (found, hostname)
        """
        if ip in self._cache:
            return True, self._cache[ip]
        return False, None

    def set(self, ip: str, hostname: Optional[str]) -> None:
        """Cache a hostname lookup result."""
        if len(self._cache) >= self._maxsize:
            # Simple FIFO eviction
            oldest = next(iter(self._cache))
            del self._cache[oldest]

        self._cache[ip] = hostname

    def lookup(self, ip: str, timeout: float = 2.0) -> Optional[str]:
        """Look up with caching."""
        found, hostname = self.get(ip)
        if found:
            return hostname

        hostname = reverse_dns(ip, timeout)
        self.set(ip, hostname)
        return hostname

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        # Also clear the lru_cache
        reverse_dns.cache_clear()

    def stats(self) -> Dict:
        """Cache statistics."""
        return {
            "size": len(self._cache),
            "maxsize": self._maxsize,
            "lru_info": reverse_dns.cache_info()._asdict(),
        }


# Global DNS cache instance
_dns_cache = DNSCache()


def get_dns_cache() -> DNSCache:
    """Get the global DNS cache instance."""
    return _dns_cache
