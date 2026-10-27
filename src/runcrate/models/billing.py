"""Billing models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

TopUpStatus = Literal["succeeded", "processing", "requires_action", "declined"]


class Balance(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    credits_balance: float = Field(alias="creditsBalance")
    active_usage_cost: float = Field(alias="activeUsageCost")
    # The balance net of what running instances have used, in USD.
    floating_balance_usd: Optional[float] = None
    # What the running instances cost together, in USD an hour.
    burn_usd_per_hour: Optional[float] = None
    # Hours the floating balance lasts at that rate; None when nothing runs.
    runway_hours: Optional[float] = None


class Transaction(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    project_id: Optional[str] = None
    type: Optional[str] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None


class UsageSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_requests: Optional[int] = None
    total_prompt_tokens: Optional[int] = None
    total_completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[float] = None


class TopUp(BaseModel):
    """One top-up of the balance from the workspace's saved card.

    ``requires_action``: a workspace owner or manager opens ``confirm_url`` to confirm it;
    nothing is charged until then. Calling ``top_up`` again with the same ``idempotency_key``
    answers the top-up's current status, which is how ``processing`` and ``requires_action``
    are polled.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    status: TopUpStatus
    amount_usd: float
    idempotency_key: str
    invoice_number: Optional[str] = None
    # Only when succeeded.
    balance_usd: Optional[float] = None
    # Only when requires_action.
    confirm_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    # Only when declined: card_declined, payment_blocked or authentication_required.
    reason: Optional[str] = None
    message: Optional[str] = None
    created_at: Optional[datetime] = None


class AutoRecharge(BaseModel):
    """When the balance falls below ``threshold_usd``, top it up to ``target_usd``."""

    model_config = ConfigDict(extra="allow")

    enabled: bool
    threshold_usd: Optional[float] = None
    target_usd: Optional[float] = None
    last_failure_reason: Optional[str] = None
    last_failure_at: Optional[datetime] = None


class PaymentMethod(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    brand: Optional[str] = None
    last4: Optional[str] = None
    exp_month: Optional[int] = None
    exp_year: Optional[int] = None
    default: bool = False
