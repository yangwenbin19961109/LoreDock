from collections.abc import Mapping

import pytest

from loredock.ingestion.web import ResolvedWebUrl, UrlFetcher, WebFetchError, WebResponse


class FakeTransport:
    def __init__(self, responses: Mapping[str, WebResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, int]] = []

    def __call__(self, url: ResolvedWebUrl, address: str, limit: int) -> WebResponse:
        self.calls.append((url.url, address, limit))
        return self.responses[url.url]


def public_resolver(hostname: str, port: int) -> tuple[str, ...]:
    del hostname, port
    return ("93.184.216.34",)


def test_fetcher_pins_public_address_and_normalizes_utf8_snapshot() -> None:
    transport = FakeTransport(
        {
            "https://example.com/guide": WebResponse(
                200,
                {"content-type": "text/html; charset=gb18030"},
                "<title>知识</title>".encode("gb18030"),
            )
        }
    )

    snapshot = UrlFetcher(resolver=public_resolver, transport=transport).fetch(
        "https://example.com/guide#ignored"
    )

    assert snapshot.requested_url == "https://example.com/guide"
    assert snapshot.final_url == snapshot.requested_url
    assert snapshot.filename == "guide.html"
    assert snapshot.content.decode() == "<title>知识</title>"
    assert transport.calls == [("https://example.com/guide", "93.184.216.34", 10 * 1024 * 1024)]


@pytest.mark.parametrize(
    "url",
    [
        "file:///private",
        "https://user:secret@example.com/",
        "http://example.com:8080/",
        "https://example.com:4430/",
    ],
)
def test_fetcher_rejects_unsupported_url_shapes(url: str) -> None:
    with pytest.raises(WebFetchError):
        UrlFetcher(resolver=public_resolver).fetch(url)


@pytest.mark.parametrize(
    "addresses",
    [
        ("127.0.0.1",),
        ("10.0.0.1",),
        ("169.254.169.254",),
        ("::1",),
        ("93.184.216.34", "192.168.1.2"),
    ],
)
def test_fetcher_rejects_private_or_mixed_dns_answers(addresses: tuple[str, ...]) -> None:
    transport = FakeTransport({})

    with pytest.raises(WebFetchError, match="本机、内网或保留"):
        UrlFetcher(resolver=lambda _host, _port: addresses, transport=transport).fetch(
            "https://example.com/"
        )

    assert transport.calls == []


def test_fetcher_replaces_hostname_fake_ip_with_validated_public_doh_answer() -> None:
    transport = FakeTransport(
        {"https://example.com/": WebResponse(200, {"content-type": "text/html"}, b"public")}
    )
    fallback_calls: list[tuple[str, int]] = []

    def fallback(hostname: str, port: int) -> tuple[str, ...]:
        fallback_calls.append((hostname, port))
        return ("93.184.216.34",)

    snapshot = UrlFetcher(
        resolver=lambda _host, _port: ("198.18.0.15",),
        fake_ip_resolver=fallback,
        transport=transport,
    ).fetch("https://example.com")

    assert snapshot.content == b"public"
    assert fallback_calls == [("example.com", 443)]
    assert transport.calls[0][1] == "93.184.216.34"


def test_fetcher_never_uses_fake_ip_fallback_for_ip_literal() -> None:
    fallback_called = False

    def fallback(_hostname: str, _port: int) -> tuple[str, ...]:
        nonlocal fallback_called
        fallback_called = True
        return ("93.184.216.34",)

    with pytest.raises(WebFetchError, match="本机、内网或保留"):
        UrlFetcher(
            resolver=lambda _host, _port: ("198.18.0.15",),
            fake_ip_resolver=fallback,
        ).fetch("http://198.18.0.15")

    assert fallback_called is False


def test_fetcher_rejects_private_answer_from_fake_ip_fallback() -> None:
    with pytest.raises(WebFetchError, match="本机、内网或保留"):
        UrlFetcher(
            resolver=lambda _host, _port: ("198.18.0.15",),
            fake_ip_resolver=lambda _host, _port: ("10.0.0.1",),
        ).fetch("https://example.com")


def test_fetcher_revalidates_redirect_and_blocks_private_destination() -> None:
    transport = FakeTransport(
        {"https://example.com/": WebResponse(302, {"location": "http://127.0.0.1/admin"}, b"")}
    )

    with pytest.raises(WebFetchError, match="redirect to HTTP"):
        UrlFetcher(resolver=public_resolver, transport=transport).fetch("https://example.com")


def test_fetcher_rejects_unsupported_or_oversized_responses() -> None:
    unsupported = FakeTransport(
        {"https://example.com/": WebResponse(200, {"content-type": "application/pdf"}, b"pdf")}
    )
    with pytest.raises(WebFetchError, match="not supported"):
        UrlFetcher(resolver=public_resolver, transport=unsupported).fetch("https://example.com")

    oversized = FakeTransport(
        {"https://example.com/": WebResponse(200, {"content-type": "text/plain"}, b"12345")}
    )
    with pytest.raises(WebFetchError, match="10 MiB"):
        UrlFetcher(resolver=public_resolver, transport=oversized, max_bytes=4).fetch(
            "https://example.com"
        )


def test_fetcher_rejects_compressed_response() -> None:
    transport = FakeTransport(
        {
            "https://example.com/": WebResponse(
                200,
                {"content-type": "text/html", "content-encoding": "gzip"},
                b"compressed",
            )
        }
    )

    with pytest.raises(WebFetchError, match="Compressed"):
        UrlFetcher(resolver=public_resolver, transport=transport).fetch("https://example.com")
