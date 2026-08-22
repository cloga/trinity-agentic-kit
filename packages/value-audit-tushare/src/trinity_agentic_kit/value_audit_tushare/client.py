from __future__ import annotations

import json
import math
import os
import urllib.request
from collections.abc import Mapping, Sequence
from typing import cast

from .contracts import TushareClient, TushareTokenError

_TUSHARE_HTTPS_ENDPOINT = "https://api.tushare.pro"


class _TushareResponseError(RuntimeError):
    pass


def resolve_tushare_token(token: str | None = None) -> str:
    resolved = (token if token is not None else os.getenv("TUSHARE_TOKEN", "")).strip()
    if not resolved:
        raise TushareTokenError(
            "A Tushare token is required; pass token= or set TUSHARE_TOKEN."
        )
    return resolved


class HttpsTushareClient:
    __slots__ = ("_timeout_seconds", "_token")

    def __init__(self, token: str, *, timeout_seconds: float = 30.0) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self._token = resolve_tushare_token(token)
        self._timeout_seconds = timeout_seconds

    def query(
        self,
        api_name: str,
        *,
        fields: str = "",
        **params: str,
    ) -> object:
        body = json.dumps(
            {
                "api_name": api_name,
                "token": self._token,
                "params": params,
                "fields": fields,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            _TUSHARE_HTTPS_ENDPOINT,
            data=body,
            headers={
                "Connection": "close",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
            raw: object = json.loads(response.read().decode("utf-8"))
        if not isinstance(raw, Mapping):
            raise _TushareResponseError("Tushare returned an invalid response")
        payload = cast(Mapping[str, object], raw)
        if payload.get("code") != 0:
            raise _TushareResponseError(
                f"Tushare API returned code {payload.get('code')!r}"
            )
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise _TushareResponseError("Tushare returned an invalid data payload")
        result = cast(Mapping[str, object], data)
        raw_fields = result.get("fields")
        raw_items = result.get("items")
        if (
            isinstance(raw_fields, (str, bytes))
            or not isinstance(raw_fields, Sequence)
            or isinstance(raw_items, (str, bytes))
            or not isinstance(raw_items, Sequence)
        ):
            raise _TushareResponseError("Tushare returned invalid tabular data")
        names = [str(field) for field in cast(Sequence[object], raw_fields)]
        records: list[dict[str, object]] = []
        for item in cast(Sequence[object], raw_items):
            if isinstance(item, (str, bytes)) or not isinstance(item, Sequence):
                raise _TushareResponseError("Tushare returned an invalid data row")
            records.append(dict(zip(names, cast(Sequence[object], item), strict=False)))
        return records


def create_tushare_client(token: str | None = None) -> TushareClient:
    return HttpsTushareClient(resolve_tushare_token(token))
