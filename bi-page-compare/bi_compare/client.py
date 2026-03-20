from __future__ import annotations

from dataclasses import dataclass
import base64
import json
from typing import Any
from urllib import error, request

from .config import EnvConfig


class ApiError(RuntimeError):
    pass


@dataclass
class BiApiClient:
    env: EnvConfig
    timeout_seconds: int = 30
    token: str | None = None

    def sign_in(self) -> str:
        encoded_password = base64.b64encode(self.env.password.encode("utf-8")).decode("utf-8")
        payload = {
            "domain": self.env.domain,
            "loginId": self.env.login_id,
            "password": encoded_password,
        }
        data = self._request_json("POST", "/public-api/sign-in", body=payload)
        if data.get("result") != "ok":
            raise ApiError(f"{self.env.name} sign-in failed: {self._format_error(data)}")

        token = ((data.get("response") or {}).get("token") or "").strip()
        if not token:
            raise ApiError(f"{self.env.name} sign-in succeeded but token missing")
        self.token = token
        return token

    def get_page(self, page_id: str) -> dict[str, Any]:
        self._ensure_token()
        page_token = self.env.page_token or self.token or ""
        data = self._request_json(
            "GET",
            f"/public-api/page/{page_id}",
            headers={"token": page_token},
        )
        if data.get("result") != "ok":
            raise ApiError(f"{self.env.name} get_page({page_id}) failed: {self._format_error(data)}")
        response = data.get("response")
        if not isinstance(response, dict):
            raise ApiError(f"{self.env.name} get_page({page_id}) returned invalid response")
        return response

    def get_card_data(self, card_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._ensure_token()
        data = self._request_json(
            "POST",
            f"/public-api/card/{card_id}/data",
            headers={"X-Auth-Token": self.token or ""},
            body=body,
        )
        if data.get("result") != "ok":
            raise ApiError(f"{self.env.name} get_card_data({card_id}) failed: {self._format_error(data)}")

        response = data.get("response")
        if not isinstance(response, dict):
            raise ApiError(f"{self.env.name} get_card_data({card_id}) returned invalid response")
        return response

    def _ensure_token(self) -> None:
        if not self.token:
            raise ApiError(f"{self.env.name} token missing, call sign_in() first")

    def _request_json(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.env.base_url}{path}"
        req_headers = {"Accept": "application/json"}
        if headers:
            req_headers.update(headers)

        raw_body = None
        if body is not None:
            raw_body = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        req = request.Request(url=url, method=method, headers=req_headers, data=raw_body)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                text = resp.read().decode("utf-8")
        except error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise ApiError(f"HTTP {e.code} for {method} {url}: {raw}") from e
        except error.URLError as e:
            raise ApiError(f"Network error for {method} {url}: {e}") from e

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise ApiError(f"Invalid JSON from {method} {url}: {text[:300]}") from e

        if not isinstance(payload, dict):
            raise ApiError(f"Unexpected response shape from {method} {url}")
        return payload

    @staticmethod
    def _format_error(payload: dict[str, Any]) -> str:
        err = payload.get("error") or {}
        status = err.get("status")
        message = err.get("message")
        if status is None and not message:
            return json.dumps(payload, ensure_ascii=False)
        return f"status={status}, message={message}"
