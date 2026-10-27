"""Tests for billing resource."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
import respx

from runcrate import (
    AsyncRuncrate,
    ConflictError,
    InsufficientCreditsError,
    PaginatedResponse,
    Runcrate,
    TimeoutError,
)

_IN_PROGRESS = {
    "error": {
        "code": "conflict",
        "message": "Being charged right now.",
        "details": {"reason": "idempotency_in_progress"},
    }
}


def _topup(key: str, **overrides: Any) -> dict[str, Any]:
    return {
        "id": "tu-1",
        "status": "succeeded",
        "amount_usd": 50,
        "idempotency_key": key,
        "invoice_number": "RC-000123",
        "balance_usd": 104.12,
        "created_at": "2026-10-26T10:00:00Z",
        **overrides,
    }


def _echo_topup(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    return httpx.Response(200, json={"data": _topup(body["idempotency_key"])})


class TestBilling:
    def test_get_balance(self, client: Runcrate, mock_api: respx.MockRouter):
        mock_api.get("/api/v1/billing/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "creditsBalance": 50.0,
                        "activeUsageCost": 2.5,
                    }
                },
            )
        )

        balance = client.billing.get_balance()
        assert balance.credits_balance == 50.0
        assert balance.active_usage_cost == 2.5
        assert balance.runway_hours is None

    def test_get_balance_runway(self, client: Runcrate, mock_api: respx.MockRouter):
        mock_api.get("/api/v1/billing/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "creditsBalance": 50.0,
                        "activeUsageCost": 2.5,
                        "floating_balance_usd": 47.5,
                        "burn_usd_per_hour": 2.49,
                        "runway_hours": 19.08,
                    }
                },
            )
        )

        balance = client.billing.get_balance()
        assert balance.floating_balance_usd == 47.5
        assert balance.burn_usd_per_hour == 2.49
        assert balance.runway_hours == 19.08

    def test_list_transactions(self, client: Runcrate, mock_api: respx.MockRouter):
        mock_api.get("/api/v1/billing/transactions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "t1", "type": "credit", "amount": 50.0},
                        {"id": "t2", "type": "debit", "amount": -2.5},
                    ],
                    "meta": {"hasMore": True, "total": 100},
                },
            )
        )

        result = client.billing.list_transactions(limit=2, offset=0)
        assert isinstance(result, PaginatedResponse)
        assert len(result.data) == 2
        assert result.data[0].id == "t1"
        assert result.data[0].amount == 50.0
        assert result.has_more is True
        assert result.total == 100

    def test_list_transactions_with_type_filter(self, client: Runcrate, mock_api: respx.MockRouter):
        route = mock_api.get("/api/v1/billing/transactions").mock(
            return_value=httpx.Response(200, json={"data": [], "meta": {}})
        )

        client.billing.list_transactions(type="credit")
        assert route.calls[0].request.url.params["type"] == "credit"

    def test_usage(self, client: Runcrate, mock_api: respx.MockRouter):
        mock_api.get("/api/v1/billing/usage").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "total_requests": 500,
                        "total_tokens": 100000,
                        "total_cost": 5.0,
                    }
                },
            )
        )

        usage = client.billing.usage(from_date="2025-01-01", to_date="2025-01-31")
        assert usage.total_requests == 500
        assert usage.total_cost == 5.0

    def test_usage_with_date_params(self, client: Runcrate, mock_api: respx.MockRouter):
        route = mock_api.get("/api/v1/billing/usage").mock(
            return_value=httpx.Response(200, json={"data": {}})
        )

        client.billing.usage(from_date="2025-01-01", to_date="2025-01-31")
        assert route.calls[0].request.url.params["from"] == "2025-01-01"
        assert route.calls[0].request.url.params["to"] == "2025-01-31"


class TestTopUp:
    def test_sends_amount_and_given_key(self, client: Runcrate, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/billing/topups").mock(side_effect=_echo_topup)

        topup = client.billing.top_up(amount_usd=50, idempotency_key="order-42")

        request = route.calls[0].request
        assert json.loads(request.content) == {"amount_usd": 50, "idempotency_key": "order-42"}
        assert request.headers["Idempotency-Key"] == "order-42"
        assert topup.status == "succeeded"
        assert topup.idempotency_key == "order-42"
        assert topup.balance_usd == 104.12

    def test_generates_a_key_when_absent(self, client: Runcrate, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/billing/topups").mock(side_effect=_echo_topup)

        first = client.billing.top_up(amount_usd=20)
        second = client.billing.top_up(amount_usd=20)

        sent = [json.loads(call.request.content)["idempotency_key"] for call in route.calls]
        assert uuid.UUID(sent[0]).version == 4
        assert first.idempotency_key == sent[0]
        assert second.idempotency_key == sent[1] != sent[0]

    def test_retry_reuses_the_key(
        self,
        api_key: str,
        base_url: str,
        mock_api: respx.MockRouter,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr("runcrate._transport.time.sleep", lambda _: None)
        route = mock_api.post("/api/v1/billing/topups").mock(
            side_effect=[httpx.ReadTimeout("slow"), httpx.Response(502), _echo_topup]
        )
        with Runcrate(api_key=api_key, base_url=base_url, max_retries=2) as client:
            topup = client.billing.top_up(amount_usd=50)

        bodies = [json.loads(call.request.content) for call in route.calls]
        keys = {call.request.headers["Idempotency-Key"] for call in route.calls}
        assert len(bodies) == 3
        assert bodies[0] == bodies[1] == bodies[2]
        assert keys == {bodies[0]["idempotency_key"]}
        assert topup.idempotency_key == bodies[0]["idempotency_key"]

    def test_requires_action(self, client: Runcrate, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/billing/topups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": _topup(
                        "k",
                        status="requires_action",
                        balance_usd=None,
                        invoice_number=None,
                        confirm_url="https://www.runcrate.ai/dashboard/billing?action=confirm-top-up",
                        expires_at="2026-10-27T10:00:00Z",
                    )
                },
            )
        )

        topup = client.billing.top_up(amount_usd=50, idempotency_key="k")
        assert topup.status == "requires_action"
        assert topup.confirm_url is not None
        assert topup.expires_at is not None

    def test_waits_and_asks_again_while_in_progress(
        self, api_key: str, base_url: str, mock_api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
    ):
        slept: list[float] = []
        monkeypatch.setattr("runcrate._transport.time.sleep", slept.append)
        route = mock_api.post("/api/v1/billing/topups").mock(
            side_effect=[httpx.Response(409, headers={"Retry-After": "5"}, json=_IN_PROGRESS), _echo_topup]
        )
        with Runcrate(api_key=api_key, base_url=base_url, max_retries=2) as client:
            topup = client.billing.top_up(amount_usd=50, idempotency_key="k")

        assert route.call_count == 2
        assert [c.request.headers["Idempotency-Key"] for c in route.calls] == ["k", "k"]
        assert slept == [5.0]
        assert topup.status == "succeeded"

    def test_error_carries_the_given_key(self, client: Runcrate, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/billing/topups").mock(
            return_value=httpx.Response(409, headers={"Retry-After": "5"}, json=_IN_PROGRESS)
        )

        with pytest.raises(ConflictError) as exc:
            client.billing.top_up(amount_usd=50, idempotency_key="k")
        assert exc.value.idempotency_key == "k"  # type: ignore[attr-defined]

    def test_timeout_carries_the_generated_key(
        self, client: Runcrate, mock_api: respx.MockRouter
    ):
        route = mock_api.post("/api/v1/billing/topups").mock(side_effect=httpx.ReadTimeout("slow"))

        with pytest.raises(TimeoutError) as exc:
            client.billing.top_up(amount_usd=50)
        sent = json.loads(route.calls[0].request.content)["idempotency_key"]
        assert exc.value.idempotency_key == sent  # type: ignore[attr-defined]

    async def test_async_waits_while_in_progress_and_error_carries_key(
        self, api_key: str, base_url: str, mock_api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
    ):
        async def no_sleep(_: float) -> None:
            return None

        monkeypatch.setattr("runcrate._transport.asyncio.sleep", no_sleep)
        route = mock_api.post("/api/v1/billing/topups").mock(
            side_effect=[
                httpx.Response(409, json=_IN_PROGRESS),
                _echo_topup,
                httpx.Response(402, json={"error": {"code": "NO_PAYMENT_METHOD", "message": "No card."}}),
            ]
        )
        async with AsyncRuncrate(api_key=api_key, base_url=base_url, max_retries=2) as client:
            topup = await client.billing.top_up(amount_usd=50, idempotency_key="k")
            with pytest.raises(InsufficientCreditsError) as exc:
                await client.billing.top_up(amount_usd=20)

        assert route.call_count == 3
        assert topup.idempotency_key == "k"
        sent = json.loads(route.calls[2].request.content)["idempotency_key"]
        assert exc.value.code == "NO_PAYMENT_METHOD"
        assert exc.value.idempotency_key == sent  # type: ignore[attr-defined]

    async def test_async_top_up(self, api_key: str, base_url: str, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/billing/topups").mock(side_effect=_echo_topup)

        async with AsyncRuncrate(api_key=api_key, base_url=base_url, max_retries=0) as client:
            given = await client.billing.top_up(amount_usd=75, idempotency_key="order-7")
            generated = await client.billing.top_up(amount_usd=75)

        assert json.loads(route.calls[0].request.content) == {
            "amount_usd": 75,
            "idempotency_key": "order-7",
        }
        assert given.idempotency_key == "order-7"
        assert uuid.UUID(generated.idempotency_key).version == 4


class TestAutoRecharge:
    def test_get(self, client: Runcrate, mock_api: respx.MockRouter):
        mock_api.get("/api/v1/billing/auto-recharge").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "enabled": True,
                        "threshold_usd": 20,
                        "target_usd": 100,
                        "last_failure_reason": None,
                        "last_failure_at": None,
                    }
                },
            )
        )

        settings = client.billing.get_auto_recharge()
        assert settings.enabled is True
        assert settings.threshold_usd == 20
        assert settings.target_usd == 100

    def test_set_sends_put_body(self, client: Runcrate, mock_api: respx.MockRouter):
        route = mock_api.put("/api/v1/billing/auto-recharge").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"enabled": False, "threshold_usd": 25, "target_usd": 150}},
            )
        )

        settings = client.billing.set_auto_recharge(enabled=False, threshold_usd=25, target_usd=150)

        assert json.loads(route.calls[0].request.content) == {
            "enabled": False,
            "threshold_usd": 25,
            "target_usd": 150,
        }
        assert settings.enabled is False
        assert settings.target_usd == 150


class TestPaymentMethods:
    def test_list(self, client: Runcrate, mock_api: respx.MockRouter):
        mock_api.get("/api/v1/billing/payment-methods").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "type": "card",
                            "brand": "visa",
                            "last4": "4242",
                            "exp_month": 12,
                            "exp_year": 2030,
                            "default": True,
                        },
                        {
                            "type": "card",
                            "brand": None,
                            "last4": None,
                            "exp_month": None,
                            "exp_year": None,
                            "default": False,
                        },
                    ]
                },
            )
        )

        methods = client.billing.list_payment_methods()
        assert [(m.brand, m.last4, m.default) for m in methods] == [
            ("visa", "4242", True),
            (None, None, False),
        ]
        assert methods[0].exp_year == 2030
