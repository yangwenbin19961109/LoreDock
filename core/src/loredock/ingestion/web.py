"""Bounded URL snapshots with public-network-only, DNS-pinned connections."""

from __future__ import annotations

import ipaddress
import json
import socket
import ssl
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from pathlib import PurePosixPath
from typing import cast
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

MAX_WEB_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_URL_LENGTH = 2048
WEB_TIMEOUT_SECONDS = 10.0
_ALLOWED_MEDIA_TYPES = {
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "text/plain": ".txt",
}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")
_DOH_HOST = "cloudflare-dns.com"
_DOH_ADDRESS = "1.1.1.1"
_DOH_RESPONSE_LIMIT = 64 * 1024


class WebFetchError(ValueError):
    """Raised when a URL or response violates the safe snapshot contract."""


@dataclass(frozen=True, slots=True)
class ResolvedWebUrl:
    url: str
    scheme: str
    hostname: str
    port: int
    target: str


@dataclass(frozen=True, slots=True)
class WebResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class WebSnapshot:
    requested_url: str
    final_url: str
    filename: str
    media_type: str
    content: bytes


Resolver = Callable[[str, int], Sequence[str]]
Transport = Callable[[ResolvedWebUrl, str, int], WebResponse]


def _parse_url(url: str) -> ResolvedWebUrl:
    if len(url) > MAX_URL_LENGTH:
        raise WebFetchError("URL is longer than 2048 characters.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise WebFetchError("URL is malformed.") from error
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise WebFetchError("Only absolute HTTP and HTTPS URLs are supported.")
    if parsed.username is not None or parsed.password is not None:
        raise WebFetchError("URLs containing credentials are not supported.")
    expected_port = 443 if scheme == "https" else 80
    if port is not None and port != expected_port:
        raise WebFetchError("Only standard HTTP and HTTPS ports are supported.")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").rstrip(".").casefold()
    except UnicodeError as error:
        raise WebFetchError("URL hostname is invalid.") from error
    if not hostname:
        raise WebFetchError("URL hostname is invalid.")
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    target = parsed.path or "/"
    if parsed.query:
        target += f"?{parsed.query}"
    normalized = urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))
    return ResolvedWebUrl(normalized, scheme, hostname, expected_port, target)


def _system_resolver(hostname: str, port: int) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise WebFetchError("URL hostname could not be resolved.") from error
    return tuple(dict.fromkeys(str(record[4][0]) for record in records))


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def _doh_resolver(hostname: str, port: int) -> tuple[str, ...]:
    del port
    addresses: list[str] = []
    for record_type in ("A", "AAAA"):
        connection = _PinnedHttpsConnection(_DOH_HOST, _DOH_ADDRESS, 443)
        target = f"/dns-query?{urlencode({'name': hostname, 'type': record_type})}"
        try:
            connection.request(
                "GET",
                target,
                headers={
                    "Accept": "application/dns-json",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            response = _read_response(connection, _DOH_RESPONSE_LIMIT)
            if response.status != 200:
                raise WebFetchError("安全 DNS 查询失败, 请检查网络或代理设置。")
            payload_value = cast(object, json.loads(response.body))
        except (HTTPException, OSError, TimeoutError, ssl.SSLError, json.JSONDecodeError) as error:
            connection.close()
            raise WebFetchError("安全 DNS 查询失败, 请检查网络或代理设置。") from error
        if not isinstance(payload_value, dict):
            raise WebFetchError("安全 DNS 返回了无法识别的数据。")
        payload = cast(dict[str, object], payload_value)
        if payload.get("Status") != 0:
            continue
        answers_value = payload.get("Answer", [])
        if not isinstance(answers_value, list):
            raise WebFetchError("安全 DNS 返回了无法识别的数据。")
        for answer_value in cast(list[object], answers_value):
            if not isinstance(answer_value, dict):
                continue
            answer = cast(dict[str, object], answer_value)
            if answer.get("type") not in {1, 28}:
                continue
            address = answer.get("data")
            if isinstance(address, str):
                addresses.append(address)
    if not addresses:
        raise WebFetchError("安全 DNS 没有返回可用的公网地址。")
    return tuple(dict.fromkeys(addresses))


def _public_addresses(
    hostname: str,
    port: int,
    resolver: Resolver,
    fake_ip_resolver: Resolver,
) -> tuple[str, ...]:
    addresses = tuple(resolver(hostname, port))
    if not addresses:
        raise WebFetchError("网址域名没有解析到可用地址。")
    try:
        parsed = tuple(ipaddress.ip_address(address) for address in addresses)
    except ValueError as error:
        raise WebFetchError("网址域名返回了无效地址。") from error
    if (
        not _is_ip_literal(hostname)
        and parsed
        and all(address.version == 4 and address in _FAKE_IP_NETWORK for address in parsed)
    ):
        addresses = tuple(fake_ip_resolver(hostname, port))
        try:
            parsed = tuple(ipaddress.ip_address(address) for address in addresses)
        except ValueError as error:
            raise WebFetchError("安全 DNS 返回了无效地址。") from error
    if any(not address.is_global for address in parsed):
        raise WebFetchError("不支持访问本机、内网或保留网络地址。")
    return tuple(str(address) for address in parsed)


class _PinnedHttpConnection(HTTPConnection):
    def __init__(self, host: str, address: str, port: int) -> None:
        super().__init__(host, port, timeout=WEB_TIMEOUT_SECONDS)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHttpsConnection(HTTPSConnection):
    def __init__(self, host: str, address: str, port: int) -> None:
        self._ssl_context = ssl.create_default_context()
        super().__init__(host, port, timeout=WEB_TIMEOUT_SECONDS, context=self._ssl_context)
        self._address = address

    def connect(self) -> None:
        raw_socket = socket.create_connection((self._address, self.port), self.timeout)
        try:
            self.sock = self._ssl_context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _read_response(connection: HTTPConnection, limit: int) -> WebResponse:
    try:
        response = connection.getresponse()
        content_length = response.getheader("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > limit:
                    raise WebFetchError("URL response exceeds the 10 MiB limit.")
            except ValueError as error:
                raise WebFetchError("URL response has an invalid Content-Length header.") from error
        body = response.read(limit + 1)
        if len(body) > limit:
            raise WebFetchError("URL response exceeds the 10 MiB limit.")
        return WebResponse(
            status=response.status,
            headers={key.casefold(): value for key, value in response.getheaders()},
            body=body,
        )
    finally:
        connection.close()


def _http_transport(url: ResolvedWebUrl, address: str, limit: int) -> WebResponse:
    connection: HTTPConnection
    if url.scheme == "https":
        connection = _PinnedHttpsConnection(url.hostname, address, url.port)
    else:
        connection = _PinnedHttpConnection(url.hostname, address, url.port)
    try:
        connection.request(
            "GET",
            url.target,
            headers={
                "Accept": "text/html, application/xhtml+xml, text/plain;q=0.8",
                "Accept-Encoding": "identity",
                "Connection": "close",
                "User-Agent": "LoreDock/0.1 URL snapshot",
            },
        )
        return _read_response(connection, limit)
    except (HTTPException, OSError, TimeoutError, ssl.SSLError) as error:
        connection.close()
        raise WebFetchError("URL could not be fetched securely.") from error


def _media_type(headers: Mapping[str, str]) -> tuple[str, str]:
    raw = headers.get("content-type", "").split(";", 1)[0].strip().casefold()
    suffix = _ALLOWED_MEDIA_TYPES.get(raw)
    if suffix is None:
        raise WebFetchError("URL response is not supported HTML or plain text.")
    return raw, suffix


def _charset(headers: Mapping[str, str]) -> str:
    raw = headers.get("content-type", "")
    for parameter in raw.split(";")[1:]:
        name, separator, value = parameter.partition("=")
        if separator and name.strip().casefold() == "charset":
            return value.strip().strip("\"'") or "utf-8"
    return "utf-8"


def _snapshot_name(url: ResolvedWebUrl, suffix: str) -> str:
    candidate = PurePosixPath(urlsplit(url.url).path).name
    stem = candidate.rsplit(".", 1)[0] if "." in candidate else candidate
    safe_stem = "".join(
        character if character.isalnum() or character in "-_" else "-" for character in stem
    )
    return f"{(safe_stem.strip('-_') or url.hostname)[:100]}{suffix}"


class UrlFetcher:
    def __init__(
        self,
        *,
        resolver: Resolver = _system_resolver,
        fake_ip_resolver: Resolver = _doh_resolver,
        transport: Transport = _http_transport,
        max_bytes: int = MAX_WEB_BYTES,
    ) -> None:
        self.resolver = resolver
        self.fake_ip_resolver = fake_ip_resolver
        self.transport = transport
        self.max_bytes = max_bytes

    def fetch(self, url: str) -> WebSnapshot:
        requested = _parse_url(url.strip())
        current = requested
        for redirect_count in range(MAX_REDIRECTS + 1):
            addresses = _public_addresses(
                current.hostname,
                current.port,
                self.resolver,
                self.fake_ip_resolver,
            )
            response = self.transport(current, addresses[0], self.max_bytes)
            if len(response.body) > self.max_bytes:
                raise WebFetchError("URL response exceeds the 10 MiB limit.")
            encoding = response.headers.get("content-encoding", "identity").strip().casefold()
            if encoding not in {"", "identity"}:
                raise WebFetchError("Compressed URL responses are not supported.")
            if response.status in _REDIRECT_STATUSES:
                location = response.headers.get("location")
                if not location:
                    raise WebFetchError("URL redirect is missing its destination.")
                if redirect_count == MAX_REDIRECTS:
                    raise WebFetchError("URL redirected too many times.")
                redirected = _parse_url(urljoin(current.url, location))
                if current.scheme == "https" and redirected.scheme != "https":
                    raise WebFetchError("HTTPS URLs may not redirect to HTTP.")
                current = redirected
                continue
            if response.status != 200:
                raise WebFetchError(f"URL returned HTTP status {response.status}.")
            media_type, suffix = _media_type(response.headers)
            try:
                text = response.body.decode(_charset(response.headers))
            except (LookupError, UnicodeDecodeError) as error:
                raise WebFetchError("URL response text encoding is invalid.") from error
            return WebSnapshot(
                requested_url=requested.url,
                final_url=current.url,
                filename=_snapshot_name(current, suffix),
                media_type=media_type,
                content=text.encode("utf-8"),
            )
        raise AssertionError("redirect loop must terminate")
