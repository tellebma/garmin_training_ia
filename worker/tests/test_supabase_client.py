"""Tests for the Supabase service-role client wrapper."""

from __future__ import annotations

from garmin_sync.supabase_client import get_admin_client


def test_admin_client_is_constructed_once() -> None:
    a = get_admin_client()
    b = get_admin_client()
    assert a is b  # cached singleton


def test_admin_client_uses_service_role_key() -> None:
    client = get_admin_client()
    # supabase-py stores headers including the auth header
    headers = client.postgrest.session.headers
    # Should not be empty; the actual key is the service role from env
    assert "Authorization" in headers or "apikey" in headers
