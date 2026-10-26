"""Sanitized provider failures crossing the PMS adapter boundary."""


class PMSProviderError(Exception):
    code = "PMS_UNAVAILABLE"
    retryable = True

    def __init__(self, message: str = "PMS provider request failed") -> None:
        super().__init__(message)


class PMSAuthenticationError(PMSProviderError):
    code = "PMS_AUTH_FAILED"
    retryable = False


class PMSRateLimitError(PMSProviderError):
    code = "PMS_RATE_LIMITED"


class PMSTimeoutError(PMSProviderError):
    code = "PMS_TIMEOUT"


class PMSInvalidResponseError(PMSProviderError):
    code = "PMS_INVALID_RESPONSE"
    retryable = False


class PMSUnsupportedCapabilityError(PMSProviderError):
    code = "PMS_CAPABILITY_UNSUPPORTED"
    retryable = False

    def __init__(self, capability: str) -> None:
        super().__init__(f"PMS capability is unsupported: {capability}")
