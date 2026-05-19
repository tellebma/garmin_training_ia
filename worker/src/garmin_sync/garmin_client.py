"""Thin wrapper over python-garminconnect (>=0.3.2) that exposes the operations
we need and translates library exceptions into our domain types.

API discovery notes
-------------------
garminconnect 0.3.x dropped the external ``garth`` dependency in favour of an
internal session client exposed on the ``Garmin`` instance as ``.client``
(``Garmin.client: garminconnect.client.Client``). The relevant surface:

* ``Garmin(email, password, is_cn=False, return_on_mfa=True)`` — constructor.
  ``return_on_mfa=True`` makes ``Garmin.login()`` return ``("needs_mfa", None)``
  instead of calling the (unset) ``prompt_mfa`` hook when MFA is required.
* ``Garmin.login()`` — returns ``(None, None)`` on success or
  ``("needs_mfa", None)`` when MFA is needed. Raises
  ``GarminConnectAuthenticationError`` for bad credentials and
  ``GarminConnectTooManyRequestsError`` when *all* login strategies hit 429.
  When *some* strategies 429 and others fail differently, the library raises a
  generic ``GarminConnectConnectionError`` — those still leave
  ``Garmin.client.is_authenticated`` False, so we treat that as a rate limit.
* ``Garmin.resume_login(client_state, mfa_code)`` — completes the MFA flow on
  the same ``Garmin`` instance that returned ``"needs_mfa"``. The
  ``client_state`` argument is actually unused (the library prefixes it with
  ``_``); the MFA state is stored on ``Garmin.client``. We pass ``{}``.
* ``Garmin.client.dumps() -> str`` — serialises ``{di_token, di_refresh_token,
  di_client_id}`` as JSON. This is what we persist (encrypted).
* ``Garmin.client.loads(json_str)`` — restores the tokens on a fresh
  ``Garmin`` instance. Raises ``GarminConnectAuthenticationError`` if any
  required token is missing.
* ``Garmin.client.is_authenticated -> bool`` — True iff a usable token is set.

The previous wrapper called ``client.garth.dumps()``; that attribute does not
exist in 0.3.x, which is what caused the AttributeError in production after
Garmin rate-limited the IP and the library returned without raising.
"""

from __future__ import annotations

import logging
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

_RATE_LIMIT_MSG = "rate limited by Garmin"
logger = logging.getLogger(__name__)


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


def _serialize_session(client: Garmin) -> str:
    """Return the JSON-encoded session token bundle.

    Defensively checks ``client.client.is_authenticated`` first: if the
    underlying library returned from ``login()`` without raising but did not
    actually establish a session (the silent-429 scenario), we raise
    ``GarminRateLimitError`` rather than crash on an empty token dict later.
    """
    inner = getattr(client, "client", None)
    if inner is None or not getattr(inner, "is_authenticated", False):
        msg = "Garmin login returned without an authenticated session (likely rate-limited)"
        raise GarminRateLimitError(msg)
    return inner.dumps()  # type: ignore[no-any-return]


def login_with_credentials(email: str, password: str) -> str:
    """Log in to Garmin Connect with email/password.

    Returns the serialized session as a JSON string (to be encrypted and
    stored in ``garmin_credentials.oauth_tokens_encrypted``).

    Raises:
        GarminAuthError: invalid credentials.
        GarminMFARequired: MFA needed — call ``submit_mfa_code(challenge, code)``.
        GarminRateLimitError: too many login attempts.
    """
    # ``return_on_mfa=True`` so MFA bubbles up as a tuple instead of the
    # library trying to call a (None) prompt_mfa callback.
    client = Garmin(
        email=email,
        password=password,
        is_cn=False,
        return_on_mfa=True,
    )
    try:
        result = client.login()
    except GarminConnectAuthenticationError as e:
        msg = "invalid Garmin credentials"
        raise GarminAuthError(msg) from e
    except GarminConnectTooManyRequestsError as e:
        raise GarminRateLimitError(_RATE_LIMIT_MSG) from e
    except GarminConnectConnectionError as e:
        # Many real-world 429 cases surface here when only some strategies
        # 429'd and others raised other transport errors. Detect them by
        # string match so the caller gets a useful status.
        if "429" in str(e):
            raise GarminRateLimitError(_RATE_LIMIT_MSG) from e
        msg = "connection error reaching Garmin"
        raise GarminError(msg) from e

    if isinstance(result, tuple) and result[0] == "needs_mfa":
        # The Garmin *instance* carries the in-memory MFA state we need to
        # call ``resume_login`` on later. We hand it back opaquely as the
        # "challenge".
        raise GarminMFARequired(challenge=client)

    return _serialize_session(client)


def submit_mfa_code(challenge: Any, code: str) -> str:
    """Resume an MFA login with the user-provided code.

    ``challenge`` is the opaque object returned via ``GarminMFARequired`` —
    in practice the ``Garmin`` instance from the initial ``login()`` call.
    """
    try:
        # ``client_state`` is unused by the underlying library (parameter is
        # prefixed with ``_`` in the source), but the signature requires it.
        challenge.resume_login({}, code)
    except GarminConnectAuthenticationError as e:
        msg = "MFA code invalid"
        raise GarminAuthError(msg) from e
    except GarminConnectTooManyRequestsError as e:
        raise GarminRateLimitError(_RATE_LIMIT_MSG) from e
    except GarminConnectConnectionError as e:
        if "429" in str(e):
            raise GarminRateLimitError(_RATE_LIMIT_MSG) from e
        msg = "connection error reaching Garmin"
        raise GarminError(msg) from e
    return _serialize_session(challenge)


def login_with_tokens(serialized_session: str) -> Garmin:
    """Restore a Garmin client from a previously serialised session.

    The library's ``Client.loads`` raises ``GarminConnectAuthenticationError``
    if the JSON is missing tokens. We surface that as ``GarminAuthError`` so
    the cron loop can flag the credential row for refresh.

    ``Client.loads`` only restores tokens — it does NOT fetch the social
    profile (which the credentials-based ``login()`` does at the end). Without
    a ``display_name``, every daily-summary endpoint (``get_stats``,
    ``get_user_summary``, ``get_hrv_data``, …) crashes with
    ``"Display name is not set"``. So we replicate the profile fetch here.
    """
    client = Garmin()
    try:
        client.client.loads(serialized_session)
    except GarminConnectAuthenticationError as e:
        msg = "Garmin session expired"
        raise GarminAuthError(msg) from e
    except GarminConnectConnectionError as e:
        # ``loads`` wraps JSON parse errors in this type.
        msg = "Garmin session corrupted"
        raise GarminAuthError(msg) from e

    # Hydrate display_name / full_name from the social profile endpoint so the
    # subsequent ``get_stats`` / ``get_user_summary`` calls don't fail. Wrap in
    # try/except : if Garmin returns a malformed profile we degrade gracefully
    # to "endpoints requiring display_name fail" (caller already handles that).
    try:
        prof = client.client.connectapi("/userprofile-service/socialProfile")
        if isinstance(prof, dict):
            display_name = prof.get("displayName")
            if display_name:
                client.display_name = display_name
            full_name = prof.get("fullName")
            if full_name:
                client.full_name = full_name
    except Exception as exc:
        # Fail-open : leave display_name unset; sync.py raises a typed error.
        logger.warning("Failed to fetch social profile after token restore: %s", exc)

    return client
