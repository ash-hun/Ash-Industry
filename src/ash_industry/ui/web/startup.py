"""[ui] Web HUD 실행: 조립 결과로 FastAPI 앱을 만들어 uvicorn 으로 띄운다."""

from typing import TYPE_CHECKING

from ash_industry.common.logger import get_logger

if TYPE_CHECKING:
    from ash_industry.app.app_assembly import AppAssembly

logger = get_logger(__name__)


def run_web(assembly: "AppAssembly", session_id: str, host: str = "127.0.0.1", port: int = 7777) -> None:
    import uvicorn

    from ash_industry.ui.web.server import create_app

    app = create_app(assembly, initial_session_id=session_id or "default")
    logger.info(f"[WebHUD] Web HUD started → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
