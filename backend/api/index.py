import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))

if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app.main import app as base_app

class VercelPathMiddleware:
    """Restores the true requested path from Vercel's x-matched-path header."""
    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            # Vercel provides the real incoming path in x-matched-path
            matched = headers.get(b"x-matched-path")
            if matched:
                path = matched.decode("latin1").split("?")[0]
                scope["path"] = path
        await self.asgi_app(scope, receive, send)

app = VercelPathMiddleware(base_app)
