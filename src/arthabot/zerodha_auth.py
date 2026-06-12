from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import parse_qs, urlparse
import webbrowser

from arthabot.secrets import update_env_access_token


@dataclass(frozen=True)
class LoginCallback:
    request_token: str | None
    status: str


@dataclass(frozen=True)
class SessionRenewalResult:
    user_id: str


class KiteSessionClient(Protocol):
    def login_url(self) -> str: ...
    def generate_session(self, request_token: str, api_secret: str) -> dict: ...
    def set_access_token(self, access_token: str) -> None: ...
    def profile(self) -> dict: ...


class ZerodhaSessionRenewal:
    def __init__(
        self,
        *,
        api_secret: str,
        env_path: str | Path,
        kite: KiteSessionClient,
        callback_receiver: Callable[[], LoginCallback],
        browser_opener: Callable[[str], bool] = webbrowser.open,
    ) -> None:
        self.api_secret = api_secret
        self.env_path = Path(env_path)
        self.kite = kite
        self.callback_receiver = callback_receiver
        self.browser_opener = browser_opener

    def run(self) -> SessionRenewalResult:
        self.browser_opener(self.kite.login_url())
        callback = self.callback_receiver()
        if callback.status not in {"success", "login"} or not callback.request_token:
            raise PermissionError(f"Zerodha login {callback.status or 'failed'}")
        session = self.kite.generate_session(callback.request_token, api_secret=self.api_secret)
        access_token = str(session.get("access_token") or "")
        if not access_token:
            raise RuntimeError("Zerodha session response did not include an access token")
        self.kite.set_access_token(access_token)
        profile = self.kite.profile()
        user_id = str(profile.get("user_id") or "")
        if not user_id:
            raise RuntimeError("Zerodha profile validation failed")
        update_env_access_token(self.env_path, access_token)
        return SessionRenewalResult(user_id=user_id)


class RemoteZerodhaSessionRenewal:
    def __init__(self, *, api_secret: str, env_path: str | Path, kite: KiteSessionClient) -> None:
        self.api_secret = api_secret
        self.env_path = Path(env_path)
        self.kite = kite

    @property
    def login_url(self) -> str:
        return self.kite.login_url()

    def exchange(self, redirect_url_or_token: str) -> SessionRenewalResult:
        value = redirect_url_or_token.strip()
        if not value:
            raise ValueError("request_token is required")
        if "://" in value or "?" in value:
            query = parse_qs(urlparse(value).query)
            request_token = (query.get("request_token") or [""])[0]
            status = (query.get("status") or query.get("action") or ["login"])[0]
            if status not in {"success", "login"}:
                raise PermissionError(f"Zerodha login {status}")
        else:
            request_token = value
        if not request_token or len(request_token) > 512:
            raise ValueError("request_token is required")
        session = self.kite.generate_session(request_token, api_secret=self.api_secret)
        access_token = str(session.get("access_token") or "")
        if not access_token:
            raise RuntimeError("Zerodha session response did not include an access token")
        self.kite.set_access_token(access_token)
        profile = self.kite.profile()
        user_id = str(profile.get("user_id") or "")
        if not user_id:
            raise RuntimeError("Zerodha profile validation failed")
        update_env_access_token(self.env_path, access_token)
        return SessionRenewalResult(user_id=user_id)


class LoopbackCallbackReceiver:
    def __init__(self, *, host: str = "127.0.0.1", port: int = 8765, timeout_seconds: int = 180) -> None:
        self.result: list[LoginCallback] = []
        result = self.result

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                query = parse_qs(urlparse(self.path).query)
                callback = LoginCallback(
                    request_token=(query.get("request_token") or [None])[0],
                    status=(query.get("status") or query.get("action") or [""])[0],
                )
                result.append(callback)
                body = b"ArthaBot received the Zerodha callback. You may close this window."
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args) -> None:
                return

        self.server = HTTPServer((host, port), CallbackHandler)
        self.server.timeout = timeout_seconds

    def __call__(self) -> LoginCallback:
        self.server.handle_request()
        self.server.server_close()
        if not self.result:
            raise TimeoutError("timed out waiting for Zerodha login callback")
        return self.result[0]


def receive_login_callback(*, host: str = "127.0.0.1", port: int = 8765, timeout_seconds: int = 180) -> LoginCallback:
    return LoopbackCallbackReceiver(host=host, port=port, timeout_seconds=timeout_seconds)()
