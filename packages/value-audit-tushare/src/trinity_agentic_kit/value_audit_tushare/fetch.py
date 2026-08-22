from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .contracts import RetryPolicy, TushareClient, TushareRequestError

_TRANSIENT_MARKERS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "connection",
    "reset",
    "temporarily",
    "timeout",
    "timed out",
    "too many requests",
)
_PERMANENT_MARKERS = (
    "400",
    "401",
    "403",
    "404",
    "forbidden",
    "invalid",
    "permission",
    "权限",
    "参数",
)

_STOCK_FIELDS = "ts_code,symbol,name,industry,market,list_status,list_date,delist_date"
_DAILY_FIELDS = "ts_code,trade_date,close,total_share,dv_ttm"
_INCOME_FIELDS = (
    "ts_code,ann_date,f_ann_date,end_date,report_type,update_flag,comp_type,revenue,"
    "oper_cost,operate_profit,total_profit,income_tax,n_income_attr_p,n_income,rd_exp"
)
_BALANCE_FIELDS = (
    "ts_code,ann_date,f_ann_date,end_date,report_type,update_flag,total_assets,total_liab,"
    "total_hldr_eqy_exc_min_int,total_cur_assets,total_cur_liab,money_cap,"
    "intan_assets,goodwill,st_borr,non_cur_liab_due_1y,lt_borr,bond_payable,"
    "acct_payable,notes_payable,contract_liab,adv_receipts,oth_payable"
)
_CASHFLOW_FIELDS = (
    "ts_code,ann_date,f_ann_date,end_date,report_type,update_flag,"
    "depr_fa_coga_dpba,amort_intang_assets,lt_amort_deferred_exp,"
    "use_right_asset_dep,c_pay_acq_const_fiolta,n_cashflow_act"
)


@dataclass(frozen=True, slots=True)
class _Endpoint:
    api_name: str
    fields: str
    dated: bool


_ENDPOINTS = (
    _Endpoint("stock_basic", _STOCK_FIELDS, False),
    _Endpoint("daily_basic", _DAILY_FIELDS, True),
    _Endpoint("income", _INCOME_FIELDS, True),
    _Endpoint("balancesheet", _BALANCE_FIELDS, True),
    _Endpoint("cashflow", _CASHFLOW_FIELDS, True),
)


def _is_retryable(error: Exception) -> bool:
    message = str(error).casefold()
    if any(marker in message for marker in _PERMANENT_MARKERS):
        return False
    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return True
    return any(marker in message for marker in _TRANSIENT_MARKERS)


def _query_with_retry(
    client: TushareClient,
    endpoint: _Endpoint,
    *,
    params: dict[str, str],
    retry_policy: RetryPolicy,
    sleep: Callable[[float], None],
) -> object:
    delay = retry_policy.initial_delay_seconds
    for attempt in range(1, retry_policy.max_attempts + 1):
        try:
            return client.query(
                endpoint.api_name,
                fields=endpoint.fields,
                **params,
            )
        except Exception as error:
            retryable = _is_retryable(error)
            if not retryable or attempt == retry_policy.max_attempts:
                raise TushareRequestError(
                    endpoint.api_name,
                    attempt,
                    retryable=retryable,
                ) from None
            sleep(min(delay, retry_policy.maximum_delay_seconds))
            delay *= retry_policy.backoff_multiplier
    raise AssertionError("unreachable")


def fetch_tushare_frames(
    client: TushareClient,
    ticker: str,
    as_of: date,
    *,
    history_years: int = 12,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        raise ValueError("ticker must be non-empty")
    if history_years < 1 or history_years > 30:
        raise ValueError("history_years must be between 1 and 30")
    policy = retry_policy or RetryPolicy()
    try:
        start = as_of.replace(year=as_of.year - history_years)
    except ValueError:
        start = as_of.replace(year=as_of.year - history_years, day=28)
    dates = {
        "ts_code": normalized_ticker,
        "start_date": start.strftime("%Y%m%d"),
        "end_date": as_of.strftime("%Y%m%d"),
    }
    frames: dict[str, object] = {}
    for endpoint in _ENDPOINTS:
        if endpoint.api_name == "stock_basic":
            frames[endpoint.api_name] = [
                _query_with_retry(
                    client,
                    endpoint,
                    params={
                        "ts_code": normalized_ticker,
                        "list_status": status,
                    },
                    retry_policy=policy,
                    sleep=sleep,
                )
                for status in ("L", "D", "P")
            ]
            continue
        params = dates if endpoint.dated else {"ts_code": normalized_ticker}
        frames[endpoint.api_name] = _query_with_retry(
            client,
            endpoint,
            params=params,
            retry_policy=policy,
            sleep=sleep,
        )
    return frames
