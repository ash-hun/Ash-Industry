"""tools 의 web_fetch 내장 도구: HTML 과 PDF 를 글로 바꾸고, 공개 웹이 아닌 주소와 그리로 가는 리다이렉트를 막는다."""

import httpx
import pytest

from ash_industry.core.tools.builtin.web_fetch import WebFetchTool, is_public_ip
from tests.fixtures.tools_helpers import route_httpx

PAGE = "<html><head><style>x{}</style></head><body><h1>Hi</h1><p>World &amp; more</p></body></html>"
HOSTS = {"example.com": ["93.184.216.34"], "inner.example.com": ["10.0.0.5"], "meta": ["169.254.169.254"]}


async def _resolve(host: str) -> list[str]:
    return HOSTS.get(host, ["93.184.216.34"])


def _pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 712 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


async def test_web_fetch_returns_page_text_without_tags_or_styles(monkeypatch):
    route_httpx(monkeypatch, lambda request: httpx.Response(200, html=PAGE))

    result = await WebFetchTool(resolve=_resolve).execute("c1", {"url": "https://example.com"})

    text = result.content[0].text
    assert result.is_error is False
    assert "Hi" in text and "World & more" in text
    assert "<" not in text and "x{}" not in text


async def test_web_fetch_extracts_pdf_text_and_names_final_url(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/notice":
            return httpx.Response(302, headers={"location": "/files/notice.pdf"})
        return httpx.Response(200, content=_pdf("Deadline 2026-12-03"), headers={"content-type": "application/pdf"})

    route_httpx(monkeypatch, handler)

    result = await WebFetchTool(resolve=_resolve).execute("c1", {"url": "https://example.com/notice"})

    text = result.content[0].text
    assert result.is_error is False
    assert text.startswith("Content of https://example.com/files/notice.pdf:")
    assert "[page 1]" in text and "Deadline 2026-12-03" in text


async def test_web_fetch_rejects_non_http_url():
    result = await WebFetchTool(resolve=_resolve).execute("c1", {"url": "ftp://example.com"})

    assert result.is_error is True
    assert "Invalid URL" in result.content[0].text


@pytest.mark.parametrize("url", ["http://127.0.0.1:5432/", "http://inner.example.com/", "http://meta/latest", "http://[::1]/"])
async def test_web_fetch_blocks_non_public_addresses(monkeypatch, url):
    seen = route_httpx(monkeypatch, lambda request: httpx.Response(200, text="secret"))

    async def resolve(host: str) -> list[str]:
        return HOSTS.get(host, [host])

    result = await WebFetchTool(resolve=resolve).execute("c1", {"url": url})

    assert result.is_error is True and "Blocked URL" in result.content[0].text
    assert seen == []


async def test_web_fetch_blocks_redirect_into_private_network(monkeypatch):
    seen = route_httpx(
        monkeypatch, lambda request: httpx.Response(301, headers={"location": "http://meta/latest/meta-data"}),
    )

    result = await WebFetchTool(resolve=_resolve).execute("c1", {"url": "https://example.com/go"})

    assert result.is_error is True and "Blocked URL" in result.content[0].text
    assert [str(r.url) for r in seen] == ["https://example.com/go"]


def test_is_public_ip_rejects_mapped_private_addresses():
    assert is_public_ip("93.184.216.34") and is_public_ip("2606:2800:220:1::1")
    assert not any(is_public_ip(a) for a in ("10.1.2.3", "192.168.0.1", "::ffff:127.0.0.1", "fe80::1%en0", "0.0.0.0"))
