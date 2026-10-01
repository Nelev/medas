"""Rate limiting for the routes.

Every request reaches this API from the UI's server, so the remote address is
the same for all users and would put them in one bucket. The limit is keyed on
the verified session subject instead, which session_claims leaves on the
request; the unauthenticated health check falls back to the address.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def rate_limit_key(request: Request) -> str:
    return getattr(request.state, "user_key", None) or get_remote_address(request)


# key_style="endpoint" counts per route function; the default counts per URL
# path, so /conversations/{id} would get a fresh bucket for every id.
limiter = Limiter(key_func=rate_limit_key, key_style="endpoint")

# The routes that call the model or index a file are billable and get the
# tight limit; reads only query Postgres and get a looser one, so clicking
# through the sidebar does not trip it.
LIMITS = "10/minute;200/day"
READ_LIMITS = "60/minute;2000/day"
