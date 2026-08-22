from __future__ import annotations

from datetime import date

from trinity_agentic_kit.value_audit import AuditConfig, AuditResult, audit_company

from .client import create_tushare_client
from .contracts import RetryPolicy, TushareClient
from .fetch import fetch_tushare_frames
from .mapper import map_tushare_frames_to_payload


def audit_tushare_company(
    ticker: str,
    as_of: date,
    *,
    token: str | None = None,
    client: TushareClient | None = None,
    is_financial: bool | None = None,
    history_years: int = 12,
    retry_policy: RetryPolicy | None = None,
    config: AuditConfig | None = None,
) -> AuditResult:
    transport = client if client is not None else create_tushare_client(token)
    frames = fetch_tushare_frames(
        transport,
        ticker,
        as_of,
        history_years=history_years,
        retry_policy=retry_policy or RetryPolicy(),
    )
    payload = map_tushare_frames_to_payload(
        frames,
        ticker,
        as_of,
        is_financial=is_financial,
    )
    return audit_company(payload, config=config or AuditConfig())
