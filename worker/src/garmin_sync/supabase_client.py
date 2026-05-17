"""Supabase Postgres client using the service role key — bypasses RLS by design.

This is ONLY used by the worker. The worker accesses every user's data, so it
needs service role. RLS still protects user-facing access (from the Next.js app
via the anon key).
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from garmin_sync.config import get_settings


@lru_cache(maxsize=1)
def get_admin_client() -> Client:
    """Returns a cached service-role Supabase client."""
    settings = get_settings()
    return create_client(
        str(settings.supabase_url),
        settings.supabase_service_role_key.get_secret_value(),
    )
