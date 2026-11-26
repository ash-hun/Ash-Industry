"""[core] 공개 URL 을 가져와 HTML 과 PDF 를 읽기 쉬운 텍스트로 돌려주는 web_fetch 내장 도구."""

import io
import re
import html
import httpx
import socket
import asyncio
import ipaddress
from typing import Any
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from urllib.parse import urljoin, urlparse
from collections.abc import Callable, Awaitable

from ash_industry.model_layer.model_types import TextContent, ToolResultMessage
from ash_industry.core.tools.tools_registry import AshTool

TOOL_NAME = "web_fetch"
TOOL_DESCRIPTION = (
    "Fetch a public URL and return its content as readable text (HTML stripped, PDF text extracted). "
    "Use this to read a specific web page when you already have its URL — "
    "complements web_search, which only returns result snippets. "
    "The first line names the final URL after redirects; cite that URL as the source."
)
TOOL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The URL to fetch (http or https)",
        },
        "max_length": {
            "type": "integer",
            "description": "Maximum characters of text to return (default: 10000)",
        },
    },
    "required": ["url"],
}

MAX_REDIRECTS = 5
MAX_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 50
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n\s*\n\s*\n+")

Resolve = Callable[[str], Awaitable[list[str]]]


class BlockedUrl(ValueError):
    """사설, loopback, 링크 로컬처럼 공개 웹이 아닌 주소다."""


async def resolve_host(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def is_public_ip(raw: str) -> bool:
    ip = ipaddress.ip_address(raw.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


class WebFetchTool(AshTool):
    """LLM 이 고른 URL 을 그대로 따라가므로 컨테이너 안의 내부 서비스(DB, MCP, 클라우드 메타데이터)로
    향하지 않게, 리다이렉트를 직접 따라가며 매 단계 주소를 확인한다."""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    parameters = TOOL_PARAMETERS
    execution_mode = "parallel"

    def __init__(self, resolve: Resolve | None = None) -> None:
        self._resolve = resolve or resolve_host

    async def execute(
        self,
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
    ) -> ToolResultMessage:
        url = params["url"]
        max_length = int(params.get("max_length", 10000))

        if not url.startswith(("http://", "https://")):
            return self._error(tool_call_id, f"Invalid URL (must start with http/https): {url}")

        try:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=False, headers={"User-Agent": "ash-industry/1.0"}
            ) as client:
                final_url, content_type, body = await self._get(client, url)
        except BlockedUrl as exc:
            return self._error(tool_call_id, f"Blocked URL: {exc}")
        except httpx.HTTPError as exc:
            return self._error(tool_call_id, f"Fetch failed: {exc}")

        try:
            text = _to_text(content_type, body)
        except ValueError as exc:
            return self._error(tool_call_id, f"Could not read {final_url}: {exc}")

        truncated = ""
        if len(text) > max_length:
            text = text[:max_length]
            truncated = f"\n\n[truncated to {max_length} chars]"

        return ToolResultMessage(
            tool_call_id=tool_call_id,
            tool_name=self.name,
            content=[TextContent(text=f"Content of {final_url}:\n\n{text}{truncated}")],
        )

    async def _get(self, client: httpx.AsyncClient, url: str) -> tuple[str, str, bytes]:
        # ponytail: 확인한 뒤 httpx 가 DNS 를 다시 조회해 rebinding 은 못 막는다, 위협이 커지면 확인한 IP 로 붙는다
        for _ in range(MAX_REDIRECTS + 1):
            await self._check(url)
            async with client.stream("GET", url) as response:
                if response.is_redirect and "location" in response.headers:
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise httpx.HTTPError(f"response larger than {MAX_BYTES} bytes")
                return url, response.headers.get("content-type", ""), bytes(body)
        raise httpx.HTTPError(f"more than {MAX_REDIRECTS} redirects")

    async def _check(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise BlockedUrl(url)
        try:
            addrs = await self._resolve(parsed.hostname)
        except OSError as exc:
            raise httpx.HTTPError(f"cannot resolve {parsed.hostname}: {exc}") from exc
        if not addrs or not all(is_public_ip(a) for a in addrs):
            raise BlockedUrl(f"{parsed.hostname} is not a public address")

    def _error(self, tool_call_id: str, text: str) -> ToolResultMessage:
        return ToolResultMessage(
            tool_call_id=tool_call_id, tool_name=self.name, content=[TextContent(text=text)], is_error=True,
        )


def _to_text(content_type: str, body: bytes) -> str:
    if "pdf" in content_type or body.startswith(b"%PDF"):
        return _pdf_to_text(body)
    raw = body.decode(_charset(content_type), errors="replace")
    return _html_to_text(raw) if "html" in content_type else raw


def _charset(content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type)
    return match.group(1) if match else "utf-8"


def _pdf_to_text(body: bytes) -> str:
    """공고문 같은 PDF 는 본문이 곧 근거라 글만 꺼낸다. 쪽 구분을 남겨 출처의 쪽을 말할 수 있게 한다."""
    try:
        reader = PdfReader(io.BytesIO(body))
        pages = reader.pages[:MAX_PDF_PAGES]
        parts = [f"[page {n}]\n{(page.extract_text() or '').strip()}" for n, page in enumerate(pages, start=1)]
    except (PdfReadError, ValueError, KeyError) as exc:
        raise ValueError(f"not a readable PDF ({exc})") from exc
    if len(reader.pages) > MAX_PDF_PAGES:
        parts.append(f"[only the first {MAX_PDF_PAGES} of {len(reader.pages)} pages]")
    return "\n\n".join(parts)


def _html_to_text(raw: str) -> str:
    """의존성 없이 HTML 태그를 제거하고 텍스트만 추출."""
    no_scripts = _SCRIPT_STYLE_RE.sub(" ", raw)
    no_tags = _TAG_RE.sub(" ", no_scripts)
    unescaped = html.unescape(no_tags)
    lines = [line.strip() for line in unescaped.splitlines()]
    collapsed = "\n".join(line for line in lines if line)
    return _WS_RE.sub("\n\n", collapsed).strip()
