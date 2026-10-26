"""Billing resources."""

from __future__ import annotations

from typing import Any, Optional

from runcrate._pagination import PaginatedResponse
from runcrate._transport import new_idempotency_key
from runcrate.models.billing import (
    AutoRecharge,
    Balance,
    PaymentMethod,
    TopUp,
    Transaction,
    UsageSummary,
)
from runcrate.models.shared import ListMeta

_TOPUPS = "/api/v1/billing/topups"
_AUTO_RECHARGE = "/api/v1/billing/auto-recharge"


def _top_up_body(amount_usd: float, idempotency_key: Optional[str]) -> dict[str, Any]:
    key = new_idempotency_key() if idempotency_key is None else idempotency_key
    return {"amount_usd": amount_usd, "idempotency_key": key}


def _auto_recharge_body(enabled: bool, threshold_usd: float, target_usd: float) -> dict[str, Any]:
    return {"enabled": enabled, "threshold_usd": threshold_usd, "target_usd": target_usd}


class Billing:
    """Synchronous billing operations."""

    def __init__(self, transport: Any) -> None:
        self._transport = transport

    def get_balance(self) -> Balance:
        data, _ = self._transport.request(
            "GET", "/api/v1/billing/balance", cast_to=Balance
        )
        return data

    def list_transactions(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        type: Optional[str] = None,
    ) -> PaginatedResponse[Transaction]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if type is not None:
            params["type"] = type
        data, meta = self._transport.request(
            "GET", "/api/v1/billing/transactions", params=params, cast_to=list[Transaction]
        )
        return PaginatedResponse(
            data=data,
            meta=ListMeta.model_validate(meta) if meta else None,
        )

    def usage(
        self,
        *,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> UsageSummary:
        params: dict[str, Any] = {}
        if from_date is not None:
            params["from"] = from_date
        if to_date is not None:
            params["to"] = to_date
        data, _ = self._transport.request(
            "GET", "/api/v1/billing/usage", params=params or None, cast_to=UsageSummary
        )
        return data


    def top_up(self, *, amount_usd: float, idempotency_key: Optional[str] = None) -> TopUp:
        """Charge the workspace's saved card ``amount_usd`` (20 to 10000) and add it to the balance.

        Without ``idempotency_key`` a new one is made; the result carries it. Calling again with
        the same key never charges twice: it answers that top-up's current status, which is how
        a ``processing`` or ``requires_action`` top-up is polled. Needs the billing permission on
        the API key (``PermissionDeniedError``); a reached cap, no card or a payment hold raise
        ``InsufficientCreditsError`` with ``code`` saying which.
        """
        body = _top_up_body(amount_usd, idempotency_key)
        data, _ = self._transport.request(
            "POST",
            _TOPUPS,
            json=body,
            cast_to=TopUp,
            # The route answers the same top-up for the same key, so a retry (same body, same
            # key) never charges twice.
            idempotency_key=body["idempotency_key"],
            idempotent=True,
        )
        return data

    def get_auto_recharge(self) -> AutoRecharge:
        data, _ = self._transport.request("GET", _AUTO_RECHARGE, cast_to=AutoRecharge)
        return data

    def set_auto_recharge(
        self, *, enabled: bool, threshold_usd: float, target_usd: float
    ) -> AutoRecharge:
        """Turn auto-recharge on or off. Threshold and target are required either way."""
        data, _ = self._transport.request(
            "PUT",
            _AUTO_RECHARGE,
            json=_auto_recharge_body(enabled, threshold_usd, target_usd),
            cast_to=AutoRecharge,
        )
        return data

    def list_payment_methods(self) -> list[PaymentMethod]:
        data, _ = self._transport.request(
            "GET", "/api/v1/billing/payment-methods", cast_to=list[PaymentMethod]
        )
        return data


class AsyncBilling:
    """Asynchronous billing operations."""

    def __init__(self, transport: Any) -> None:
        self._transport = transport

    async def get_balance(self) -> Balance:
        data, _ = await self._transport.request(
            "GET", "/api/v1/billing/balance", cast_to=Balance
        )
        return data

    async def list_transactions(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        type: Optional[str] = None,
    ) -> PaginatedResponse[Transaction]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if type is not None:
            params["type"] = type
        data, meta = await self._transport.request(
            "GET", "/api/v1/billing/transactions", params=params, cast_to=list[Transaction]
        )
        return PaginatedResponse(
            data=data,
            meta=ListMeta.model_validate(meta) if meta else None,
        )

    async def usage(
        self,
        *,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> UsageSummary:
        params: dict[str, Any] = {}
        if from_date is not None:
            params["from"] = from_date
        if to_date is not None:
            params["to"] = to_date
        data, _ = await self._transport.request(
            "GET", "/api/v1/billing/usage", params=params or None, cast_to=UsageSummary
        )
        return data

    async def top_up(self, *, amount_usd: float, idempotency_key: Optional[str] = None) -> TopUp:
        """See ``Billing.top_up``."""
        body = _top_up_body(amount_usd, idempotency_key)
        data, _ = await self._transport.request(
            "POST",
            _TOPUPS,
            json=body,
            cast_to=TopUp,
            idempotency_key=body["idempotency_key"],
            idempotent=True,
        )
        return data

    async def get_auto_recharge(self) -> AutoRecharge:
        data, _ = await self._transport.request("GET", _AUTO_RECHARGE, cast_to=AutoRecharge)
        return data

    async def set_auto_recharge(
        self, *, enabled: bool, threshold_usd: float, target_usd: float
    ) -> AutoRecharge:
        """See ``Billing.set_auto_recharge``."""
        data, _ = await self._transport.request(
            "PUT",
            _AUTO_RECHARGE,
            json=_auto_recharge_body(enabled, threshold_usd, target_usd),
            cast_to=AutoRecharge,
        )
        return data

    async def list_payment_methods(self) -> list[PaymentMethod]:
        data, _ = await self._transport.request(
            "GET", "/api/v1/billing/payment-methods", cast_to=list[PaymentMethod]
        )
        return data
