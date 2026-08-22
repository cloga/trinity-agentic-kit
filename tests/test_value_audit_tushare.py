from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import cast
from urllib import request as urllib_request

import pytest

from trinity_agentic_kit.value_audit import AuditResult
from trinity_agentic_kit.value_audit_tushare import (
    PACKAGE_VERSION,
    HttpsTushareClient,
    RetryPolicy,
    TushareMappingError,
    TushareRequestError,
    TushareTokenError,
    audit_tushare_company,
    cli,
    create_tushare_client,
    fetch_tushare_frames,
    map_tushare_frames_to_payload,
    resolve_tushare_token,
)


def _annual_rows() -> dict[str, object]:
    income: list[dict[str, object]] = []
    balance: list[dict[str, object]] = []
    cashflow: list[dict[str, object]] = []
    for offset, year in enumerate(range(2020, 2025)):
        end_date = f"{year}1231"
        announcement = f"{year + 1}0331"
        revenue = 1_000_000_000.0 * (1.1**offset)
        net_income = 100_000_000.0 * (1.1**offset)
        income.append(
            {
                "ts_code": "600000.SH",
                "end_date": end_date,
                "ann_date": announcement,
                "report_type": "1",
                "revenue": revenue,
                "oper_cost": revenue * 0.6,
                "operate_profit": revenue * 0.2,
                "total_profit": revenue * 0.18,
                "income_tax": revenue * 0.03,
                "n_income_attr_p": net_income,
                "rd_exp": revenue * 0.02,
            }
        )
        balance.append(
            {
                "ts_code": "600000.SH",
                "end_date": end_date,
                "ann_date": announcement,
                "report_type": "1",
                "total_assets": 3_000_000_000.0 * (1.08**offset),
                "total_liab": 1_200_000_000.0 * (1.08**offset),
                "total_hldr_eqy_exc_min_int": 1_800_000_000.0 * (1.08**offset),
                "total_cur_assets": 1_000_000_000.0,
                "total_cur_liab": 500_000_000.0,
                "money_cap": 400_000_000.0,
                "intan_assets": 20_000_000.0,
                "goodwill": 10_000_000.0,
                "st_borr": 100_000_000.0,
                "non_cur_liab_due_1y": 20_000_000.0,
                "lt_borr": 200_000_000.0,
                "bond_payable": 50_000_000.0,
                "acct_payable": 80_000_000.0,
                "notes_payable": 20_000_000.0,
                "contract_liab": 30_000_000.0,
                "adv_receipts": 10_000_000.0,
                "oth_payable": 15_000_000.0,
            }
        )
        cashflow.append(
            {
                "ts_code": "600000.SH",
                "end_date": end_date,
                "ann_date": announcement,
                "report_type": "1",
                "depr_fa_coga_dpba": net_income * 0.15,
                "c_pay_acq_const_fiolta": net_income * 0.3,
                "n_cashflow_act": net_income * 1.1,
            }
        )
    return {
        "stock_basic": [
            {
                "ts_code": "600000.SH",
                "name": "Synthetic Manufacturing",
                "industry": "industrial machinery",
                "list_date": "19991110",
                "delist_date": "",
            }
        ],
        "daily_basic": [
            {
                "ts_code": "600000.SH",
                "trade_date": "20250331",
                "close": 12.0,
                "total_share": 100_000.0,
                "dv_ttm": 2.0,
            },
            {
                "ts_code": "600000.SH",
                "trade_date": "20250627",
                "close": 12.5,
                "total_share": 100_000.0,
                "dv_ttm": 2.4,
            },
            {
                "ts_code": "600000.SH",
                "trade_date": "20250701",
                "close": 99.0,
                "total_share": 100_000.0,
                "dv_ttm": 2.4,
            },
        ],
        "income": income,
        "balancesheet": balance,
        "cashflow": cashflow,
    }


class FakeClient:
    def __init__(self, frames: Mapping[str, object]) -> None:
        self.frames = frames
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def query(
        self,
        api_name: str,
        *,
        fields: str = "",
        **params: str,
    ) -> object:
        self.calls.append((api_name, fields, params))
        return self.frames.get(api_name, [])


def test_mapper_normalizes_units_visibility_and_provenance() -> None:
    frames = _annual_rows()
    future = dict(cast(list[dict[str, object]], frames["income"])[-1])
    future["end_date"] = "20250331"
    future["ann_date"] = "20250715"
    future["n_income_attr_p"] = 9_999_999_999.0
    cast(list[dict[str, object]], frames["income"]).append(future)

    payload = map_tushare_frames_to_payload(
        frames,
        "600000.sh",
        date(2025, 6, 30),
    )

    assert payload.company_id == "600000.SH"
    assert payload.currency == "CNY"
    assert payload.monetary_unit == "ones"
    assert payload.share_unit == "shares"
    assert payload.market.date == date(2025, 6, 27)
    assert payload.market.shares_outstanding == 1_000_000_000.0
    assert payload.market.dividend_per_share_ttm == pytest.approx(0.3)
    assert len(payload.periods) == 5
    assert all(period.visible_at <= payload.as_of_date for period in payload.periods)
    assert all(period.period_type == "annual" for period in payload.periods)
    assert payload.periods[-1].values["capital_expenditure"] > 0
    assert payload.periods[-1].values["gross_profit"] > 0
    assert set(payload.periods[-1].source_ids) <= {
        source.source_id for source in payload.provenance
    }


def test_mapper_uses_latest_visible_restatement() -> None:
    frames = _annual_rows()
    restatement = dict(cast(list[dict[str, object]], frames["income"])[-1])
    restatement["f_ann_date"] = "20250415"
    restatement["n_income_attr_p"] = 200_000_000.0
    cast(list[dict[str, object]], frames["income"]).append(restatement)

    before = map_tushare_frames_to_payload(frames, "600000.SH", date(2025, 4, 1))
    after = map_tushare_frames_to_payload(frames, "600000.SH", date(2025, 6, 30))

    assert before.periods[-1].values["net_income"] != 200_000_000.0
    assert after.periods[-1].values["net_income"] == 200_000_000.0
    assert after.periods[-1].visible_at == date(2025, 4, 15)


def test_mapper_excludes_single_quarter_and_prefers_adjusted_consolidated() -> None:
    frames = _annual_rows()
    baseline = dict(cast(list[dict[str, object]], frames["income"])[-1])
    single_quarter = dict(baseline)
    single_quarter["report_type"] = "2"
    single_quarter["f_ann_date"] = "20250420"
    single_quarter["n_income_attr_p"] = 999_000_000.0
    adjusted = dict(baseline)
    adjusted["report_type"] = "4"
    adjusted["f_ann_date"] = baseline["ann_date"]
    adjusted["n_income_attr_p"] = 210_000_000.0
    cast(list[dict[str, object]], frames["income"]).extend([single_quarter, adjusted])

    payload = map_tushare_frames_to_payload(frames, "600000.SH", date(2025, 6, 30))

    assert payload.periods[-1].values["net_income"] == 210_000_000.0


def test_mapper_prefers_update_flag_independent_of_response_order() -> None:
    frames = _annual_rows()
    baseline = cast(list[dict[str, object]], frames["income"])[-1]
    baseline["update_flag"] = "1"
    stale = dict(baseline)
    stale["update_flag"] = "0"
    stale["n_income_attr_p"] = 999_000_000.0
    cast(list[dict[str, object]], frames["income"]).append(stale)

    forward = map_tushare_frames_to_payload(frames, "600000.SH", date(2025, 6, 30))
    cast(list[dict[str, object]], frames["income"]).reverse()
    reversed_result = map_tushare_frames_to_payload(
        frames, "600000.SH", date(2025, 6, 30)
    )

    assert forward.periods[-1].values["net_income"] != 999_000_000.0
    assert (
        forward.periods[-1].values["net_income"]
        == reversed_result.periods[-1].values["net_income"]
    )


def test_mapper_enforces_listing_dates_and_accepts_company_type_override() -> None:
    frames = _annual_rows()
    identity = cast(list[dict[str, object]], frames["stock_basic"])[0]
    identity["industry"] = "banking"
    identity["list_date"] = "20250701"
    with pytest.raises(TushareMappingError, match="stock_basic"):
        map_tushare_frames_to_payload(frames, "600000.SH", date(2025, 6, 30))

    identity["list_date"] = "19991110"
    payload = map_tushare_frames_to_payload(
        frames,
        "600000.SH",
        date(2025, 6, 30),
        is_financial=False,
    )
    assert not payload.is_financial


def test_mapper_rejects_missing_required_rows() -> None:
    frames = _annual_rows()
    frames["stock_basic"] = []
    with pytest.raises(TushareMappingError, match="stock_basic"):
        map_tushare_frames_to_payload(frames, "600000.SH", date(2025, 6, 30))

    frames = _annual_rows()
    frames["daily_basic"] = []
    with pytest.raises(TushareMappingError, match="daily_basic"):
        map_tushare_frames_to_payload(frames, "600000.SH", date(2025, 6, 30))

    frames = _annual_rows()
    frames["income"] = []
    frames["balancesheet"] = []
    frames["cashflow"] = []
    with pytest.raises(TushareMappingError, match="No financial rows"):
        map_tushare_frames_to_payload(frames, "600000.SH", date(2025, 6, 30))


def test_fetch_uses_explicit_as_of_and_documented_fields() -> None:
    client = FakeClient(_annual_rows())

    result = fetch_tushare_frames(
        client,
        "600000.sh",
        date(2025, 6, 30),
        history_years=5,
    )

    assert set(result) == {
        "stock_basic",
        "daily_basic",
        "income",
        "balancesheet",
        "cashflow",
    }
    assert [call[0] for call in client.calls] == [
        "stock_basic",
        "stock_basic",
        "stock_basic",
        "daily_basic",
        "income",
        "balancesheet",
        "cashflow",
    ]
    assert [call[2]["list_status"] for call in client.calls[:3]] == ["L", "D", "P"]
    assert client.calls[3][2] == {
        "ts_code": "600000.SH",
        "start_date": "20200630",
        "end_date": "20250630",
    }
    assert "total_share" in client.calls[3][1]
    assert "update_flag" in client.calls[4][1]
    assert "c_depr_fina_amort" not in client.calls[6][1]


def test_fetch_has_bounded_retry_and_safe_errors() -> None:
    class FlakyClient:
        def __init__(self) -> None:
            self.attempts = 0

        def query(self, api_name: str, *, fields: str = "", **params: str) -> object:
            del api_name, fields, params
            self.attempts += 1
            raise TimeoutError("secret-token-value timed out")

    sleeps: list[float] = []
    client = FlakyClient()
    with pytest.raises(TushareRequestError) as captured:
        fetch_tushare_frames(
            client,
            "600000.SH",
            date(2025, 6, 30),
            retry_policy=RetryPolicy(
                max_attempts=3,
                initial_delay_seconds=0.1,
                maximum_delay_seconds=0.15,
            ),
            sleep=sleeps.append,
        )

    assert client.attempts == 3
    assert sleeps == [0.1, 0.15]
    assert captured.value.retryable
    assert captured.value.__cause__ is None
    assert "secret-token-value" not in str(captured.value)


def test_permanent_fetch_error_is_not_retried() -> None:
    class ForbiddenClient:
        def query(self, api_name: str, *, fields: str = "", **params: str) -> object:
            del api_name, fields, params
            raise RuntimeError("403 permission denied")

    with pytest.raises(TushareRequestError) as captured:
        fetch_tushare_frames(
            ForbiddenClient(),
            "600000.SH",
            date(2025, 6, 30),
            sleep=lambda _: None,
        )
    assert captured.value.attempts == 1
    assert not captured.value.retryable


def test_audit_api_delegates_to_value_audit_core() -> None:
    result = audit_tushare_company(
        "600000.SH",
        date(2025, 6, 30),
        client=FakeClient(_annual_rows()),
    )

    assert isinstance(result, AuditResult)
    assert set(result.models) == {"graham", "buffett", "greenwald", "lynch"}
    latest_income = cast(
        float,
        cast(list[dict[str, object]], _annual_rows()["income"])[-1]["n_income_attr_p"],
    )
    assert result.models["lynch"].metrics["latest_restated_eps"] == pytest.approx(
        latest_income / 1_000_000_000.0
    )
    assert result.provenance


def test_token_resolution_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "environment-secret")
    assert resolve_tushare_token() == "environment-secret"
    assert resolve_tushare_token("explicit-secret") == "explicit-secret"
    monkeypatch.delenv("TUSHARE_TOKEN")
    with pytest.raises(TushareTokenError):
        resolve_tushare_token()


def test_https_client_uses_encrypted_endpoint_and_safe_representation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[urllib_request.Request, float]] = []

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(
            self,
            exception_type: object,
            exception: object,
            traceback: object,
        ) -> None:
            del exception_type, exception, traceback

        def read(self) -> bytes:
            return (
                b'{"code": 0, "data": {"fields": ["ts_code"], '
                b'"items": [["600000.SH"]]}}'
            )

    def urlopen(request: urllib_request.Request, *, timeout: float) -> FakeResponse:
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(urllib_request, "urlopen", urlopen)
    client = create_tushare_client("explicit-secret")
    assert isinstance(client, HttpsTushareClient)
    assert "explicit-secret" not in repr(client)
    assert client.query("stock_basic", ts_code="600000.SH") == [
        {"ts_code": "600000.SH"}
    ]
    request, timeout = requests[0]
    assert request.full_url == "https://api.tushare.pro"
    assert timeout == 30.0
    body = json.loads(cast(bytes, request.data).decode("utf-8"))
    assert body["token"] == "explicit-secret"


def test_cli_writes_result_and_does_not_echo_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = audit_tushare_company(
        "600000.SH",
        date(2025, 6, 30),
        client=FakeClient(_annual_rows()),
    )
    calls: list[dict[str, object]] = []

    def fake_audit(
        ticker: str,
        as_of: date,
        *,
        token: str | None,
        history_years: int,
        is_financial: bool | None,
    ) -> AuditResult:
        calls.append(
            {
                "ticker": ticker,
                "as_of": as_of,
                "token": token,
                "history_years": history_years,
                "is_financial": is_financial,
            }
        )
        return result

    monkeypatch.setattr(cli, "audit_tushare_company", fake_audit)
    output = tmp_path / "audit.json"
    status = cli.main(
        [
            "600000.SH",
            "--as-of",
            "2025-06-30",
            "--output",
            str(output),
            "--token",
            "cli-secret",
            "--company-type",
            "financial",
        ]
    )

    assert status == 0
    assert json.loads(output.read_text(encoding="utf-8"))["company_id"] == "600000.SH"
    assert calls[0]["token"] == "cli-secret"
    assert calls[0]["is_financial"] is True
    assert "cli-secret" not in capsys.readouterr().out


def test_cli_reports_safe_adapter_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_audit(
        ticker: str,
        as_of: date,
        *,
        token: str | None,
        history_years: int,
        is_financial: bool | None,
    ) -> AuditResult:
        del ticker, as_of, token, history_years, is_financial
        raise TushareTokenError("safe error")

    monkeypatch.setattr(cli, "audit_tushare_company", fail_audit)
    status = cli.main(
        [
            "600000.SH",
            "--as-of",
            "2025-06-30",
            "--output",
            str(tmp_path / "unused.json"),
        ]
    )
    assert status == 1
    assert capsys.readouterr().out.strip() == "error: safe error"


def test_cli_rejects_invalid_date() -> None:
    with pytest.raises(SystemExit):
        cli.main(
            [
                "600000.SH",
                "--as-of",
                "2025-02-30",
                "--output",
                "unused.json",
            ]
        )


def test_package_version_and_retry_guards() -> None:
    assert PACKAGE_VERSION == "0.1.0"
    with pytest.raises(ValueError, match="between 1 and 10"):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="finite and non-negative"):
        RetryPolicy(initial_delay_seconds=-1)
    with pytest.raises(ValueError, match="finite and at least 1"):
        RetryPolicy(backoff_multiplier=0.5)
    with pytest.raises(ValueError, match="finite and non-negative"):
        RetryPolicy(maximum_delay_seconds=-1)
    with pytest.raises(ValueError, match="finite and non-negative"):
        RetryPolicy(maximum_delay_seconds=float("inf"))
    with pytest.raises(ValueError, match="finite and positive"):
        HttpsTushareClient("token", timeout_seconds=0)
    with pytest.raises(TushareTokenError):
        HttpsTushareClient(" ")
    with pytest.raises(ValueError, match="history_years"):
        fetch_tushare_frames(
            FakeClient({}), "600000.SH", date(2025, 6, 30), history_years=31
        )
