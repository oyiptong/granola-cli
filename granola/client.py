from __future__ import annotations

from dataclasses import dataclass

import requests

from granola.ratelimit import RateLimiter, RateLimitExhaustedError, TransientHttpError


@dataclass
class ApiError(Exception):
    error: str
    message: str
    retryable: bool
    exit_code: int
    context: dict

    def __str__(self) -> str:
        return self.message


class GranolaClient:
    def __init__(
        self,
        api_key: str,
        *,
        api_base_url: str,
        session: requests.Session | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        self.api_base_url = api_base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        self.rate_limiter = rate_limiter or RateLimiter()

    def list_notes_page(
        self, *, updated_after: str | None, cursor: str | None, page_size: int
    ) -> dict:
        params: dict[str, object] = {"page_size": min(page_size, 30)}
        if updated_after:
            params["updated_after"] = updated_after
        if cursor:
            params["cursor"] = cursor
        return self._request_json("GET", "/v1/notes", params=params)

    def iter_note_summaries(
        self, *, updated_after: str | None, page_size: int
    ) -> list[dict]:
        notes: list[dict] = []
        cursor: str | None = None
        while True:
            payload = self.list_notes_page(
                updated_after=updated_after, cursor=cursor, page_size=page_size
            )
            notes.extend(payload.get("notes") or [])
            if not payload.get("hasMore"):
                return notes
            cursor = payload.get("cursor")

    def get_note(self, note_id: str) -> dict:
        return self._request_json(
            "GET", f"/v1/notes/{note_id}", params={"include": "transcript"}
        )

    def _request_json(
        self, method: str, path: str, *, params: dict | None = None
    ) -> dict:
        url = f"{self.api_base_url}{path}"

        def operation() -> requests.Response:
            return self.session.request(method, url, params=params, timeout=30)

        try:
            response = self.rate_limiter.execute(operation, method=method, path=path)
        except RateLimitExhaustedError as exc:
            raise ApiError(
                "rate_limited",
                "Granola API rate limit retries exhausted",
                True,
                5,
                {"retry_after_seconds": exc.retry_after_seconds},
            ) from exc
        except TransientHttpError as exc:
            raise ApiError(
                "server_error",
                f"Granola API returned {exc.status_code}",
                True,
                1,
                {"status_code": exc.status_code},
            ) from exc
        except requests.RequestException as exc:
            raise ApiError("network_error", str(exc), True, 1, {}) from exc

        if response.status_code in {401, 403}:
            raise ApiError(
                "auth_failed",
                "Granola API authentication failed",
                False,
                4,
                {"status_code": response.status_code},
            )
        if response.status_code == 404:
            raise ApiError(
                "not_found",
                "Granola API resource not found",
                False,
                3,
                {"status_code": 404},
            )
        if response.status_code >= 400:
            raise ApiError(
                "fetch_failed",
                f"Granola API request failed with status {response.status_code}",
                False,
                1,
                {"status_code": response.status_code},
            )
        return response.json()
