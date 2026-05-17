"""Thin wrapper over python-garminconnect that exposes the operations we need
and translates library exceptions into our domain types.
"""

from __future__ import annotations

from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


class GarminError(Exception):
    """Generic Garmin error."""


class GarminAuthError(GarminError):
    """Garmin rejected our credentials or expired tokens."""


class GarminMFARequired(GarminError):
    """Garmin returned an MFA challenge. Carry `challenge` to resume."""

    def __init__(self, challenge: Any) -> None:
        super().__init__("MFA required")
        self.challenge = challenge


class GarminRateLimitError(GarminError):
    """Garmin rate-limited us; back off."""


def login_with_credentials(email: str, password: str) -> str:
    """Log in to Garmin Connect with email/password.

    Returns the serialized garth session as a JSON string (to be encrypted and
    stored in `garmin_credentials.oauth_tokens_encrypted`).

    Raises:
        GarminAuthError: invalid credentials.
        GarminMFARequired: MFA needed — call submit_mfa_code(challenge, code).
        GarminRateLimitError: too many login attempts.
    """
    client = Garmin(email=email, password=password, is_cn=False)
    try:
        result = client.login()
    except GarminConnectAuthenticationError as e:
        msg = "invalid Garmin credentials"
        raise GarminAuthError(msg) from e
    except GarminConnectTooManyRequestsError as e:
        msg = "rate limited by Garmin"
        raise GarminRateLimitError(msg) from e
    except GarminConnectConnectionError as e:
        msg = "connection error reaching Garmin"
        raise GarminError(msg) from e

    if isinstance(result, tuple) and result[0] == "needs_mfa":
        # garminconnect's MFA flow returns a continuation we resume later
        raise GarminMFARequired(challenge=result[1])

    return client.garth.dumps()  # type: ignore[no-any-return]


def submit_mfa_code(challenge: Any, code: str) -> str:
    """Resume an MFA login with the user-provided code."""
    try:
        challenge.resume_login(code)
    except GarminConnectAuthenticationError as e:
        msg = "MFA code invalid"
        raise GarminAuthError(msg) from e
    return challenge.garth.dumps()  # type: ignore[no-any-return]


def login_with_tokens(serialized_session: str) -> Garmin:
    """Restore a Garmin client from previously dumped garth tokens.

    Issues a refresh login() to confirm the session is still valid. Raises
    GarminAuthError if tokens are expired and need re-auth.
    """
    client = Garmin()
    client.garth.loads(serialized_session)
    try:
        client.login()  # refresh, validates tokens
    except GarminConnectAuthenticationError as e:
        msg = "Garmin session expired"
        raise GarminAuthError(msg) from e
    return client
