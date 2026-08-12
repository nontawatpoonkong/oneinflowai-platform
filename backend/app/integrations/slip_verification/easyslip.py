"""EasySlip API v2 adapter with a sanitized provider-neutral boundary."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.integrations.slip_verification.base import (
    SlipVerificationErrorCode,
    SlipVerificationProviderError,
    SlipVerificationRequest,
    SlipVerificationResult,
)

EASYSLIP_VERIFY_URL = "https://api.easyslip.com/v2/verify/bank"


class EasySlipVerificationProvider:
    name = "easyslip_v2"

    def __init__(self, api_key: str, timeout: float, *, transport=None) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    async def verify(self, evidence: SlipVerificationRequest) -> SlipVerificationResult:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    EASYSLIP_VERIFY_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files={"image": ("evidence", evidence.content, evidence.mime_type)},
                    data={
                        "matchAccount": "true",
                        "matchAmount": str(evidence.expected_amount),
                        "checkDuplicate": "true",
                    },
                )
        except httpx.TimeoutException as exc:
            raise SlipVerificationProviderError(
                SlipVerificationErrorCode.TIMEOUT
            ) from exc
        except httpx.HTTPError as exc:
            raise SlipVerificationProviderError(
                SlipVerificationErrorCode.NETWORK_ERROR
            ) from exc

        payload = self._json(response)
        if response.status_code >= 400:
            raise SlipVerificationProviderError(
                self._map_error(response.status_code, payload)
            )
        try:
            data = payload["data"]
            raw = data["rawSlip"]
            amount = Decimal(str(data["amountInSlip"]))
            local = raw["amount"]["local"]
            currency = str(local["currency"]).upper()
            receiver = raw["receiver"]
            account = receiver["account"]
            bank_account = account.get("bank") or account.get("proxy") or {}
            names = account.get("name") or {}
            transferred_at = datetime.fromisoformat(str(raw["date"]))
            transfer_reference = str(raw["transRef"]).strip()
            receiver_bank = str(
                receiver["bank"].get("short") or receiver["bank"].get("id")
            ).strip()
            receiver_name = (names.get("th") or names.get("en") or "").strip()
            receiver_account = str(bank_account.get("account") or "").strip()
            if not transfer_reference or not receiver_bank:
                raise ValueError
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise SlipVerificationProviderError(
                SlipVerificationErrorCode.PROVIDER_ERROR
            ) from exc

        return SlipVerificationResult(
            provider=self.name,
            provider_reference=transfer_reference,
            is_valid=True,
            amount=amount,
            currency=currency,
            transfer_reference=transfer_reference,
            transferred_at=transferred_at,
            receiver_name=receiver_name or None,
            receiver_account_masked=receiver_account or None,
            receiver_bank=receiver_bank,
            duplicate_reference_signal=bool(data["isDuplicate"]),
            raw_status_code="VERIFIED",
        )

    @staticmethod
    def _json(response: httpx.Response) -> dict:
        try:
            value = response.json()
        except ValueError as exc:
            raise SlipVerificationProviderError(
                SlipVerificationErrorCode.PROVIDER_ERROR
            ) from exc
        if not isinstance(value, dict):
            raise SlipVerificationProviderError(
                SlipVerificationErrorCode.PROVIDER_ERROR
            )
        return value

    @staticmethod
    def _map_error(status_code: int, payload: dict) -> str:
        error = payload.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        if status_code == 401 or code in {"MISSING_API_KEY", "INVALID_API_KEY"}:
            return SlipVerificationErrorCode.AUTHENTICATION_FAILED
        if status_code == 429 or code == "QUOTA_EXCEEDED":
            return SlipVerificationErrorCode.RATE_LIMITED
        if code in {
            "VALIDATION_ERROR",
            "IMAGE_SIZE_TOO_LARGE",
            "INVALID_IMAGE_TYPE",
            "INVALID_IMAGE_FORMAT",
            "SLIP_NOT_FOUND",
        }:
            return SlipVerificationErrorCode.INVALID_EVIDENCE
        if status_code in {403, 404}:
            return SlipVerificationErrorCode.PROVIDER_REJECTED
        return SlipVerificationErrorCode.PROVIDER_ERROR
