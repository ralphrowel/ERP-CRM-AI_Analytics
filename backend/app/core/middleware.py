"""Production Security Headers Middleware (Roadmap §V1.9)

Enforces HTTP Security Headers as required by the production deployment specification:
- Strict-Transport-Security (HSTS)
- X-Content-Type-Options
- X-Frame-Options
- Referrer-Policy
- Permissions-Policy
- Content-Security-Policy (CSP)
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds essential OWASP-recommended security headers to all HTTP responses."""

    def __init__(self, app, enable_hsts: bool = True) -> None:
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # 1. HSTS (Strict-Transport-Security)
        if self.enable_hsts or request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # 2. Prevent MIME-sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 3. Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # 4. Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 5. Restrict browser feature permissions
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # 6. Basic Content Security Policy (allows self-hosted assets and inline styles for SPA)
        if "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; "
                "frame-ancestors 'none'; "
                "connect-src 'self';"
            )

        return response
