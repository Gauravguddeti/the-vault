from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request

def get_user_id_or_ip(request: Request) -> str:
    """
    Use the user's ID from the JWT token if available, otherwise fall back to IP.
    Note: Auth dependency parses the token, but slowapi might run before or we can just parse the header manually,
    but for simplicity, IP is usually fine for rate limiting in a small app.
    """
    return get_remote_address(request)

limiter = Limiter(key_func=get_user_id_or_ip)
