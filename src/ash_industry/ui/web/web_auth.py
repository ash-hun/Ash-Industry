"""[ui] Web HUD 접근 키 확인. 설정의 키 목록으로 REST 요청과 ws 연결의 사용자를 찾는다."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ash_industry.ash_config import ApiUser, AshSettings


def auth_enabled(settings: "AshSettings") -> bool:
    """접근 키가 하나라도 설정돼 있으면 web 인증을 켠다. 비어 있으면 지금처럼 NoAuth."""
    return bool(settings.security.api_keys)


def lookup_api_user(settings: "AshSettings", token: str | None) -> "ApiUser | None":
    if not token:
        return None
    return settings.security.api_keys.get(token)


def bearer_token(authorization: str | None) -> str | None:
    """Authorization 헤더의 Bearer 값. 다른 방식이거나 비어 있으면 None."""
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value else None
