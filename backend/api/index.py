import sys
import os
from urllib.parse import parse_qs

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", "backend"))

for p in [backend_dir, parent_dir]:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

from app.main import app as base_app

class VercelPathMiddleware:
    """Restores the true requested path from Vercel's headers or rewrite query parameter."""
    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            
            # Check headers
            matched = headers.get(b"x-matched-path", b"").decode("latin1").split("?")[0]
            forwarded = headers.get(b"x-forwarded-uri", b"").decode("latin1").split("?")[0]
            
            # Check query string
            query_string = scope.get("query_string", b"").decode("latin1")
            params = parse_qs(query_string)
            
            if forwarded and not forwarded.endswith(".py"):
                scope["path"] = forwarded
            elif matched and "index.py" not in matched:
                scope["path"] = matched
            elif "path" in params:
                raw_path = params["path"][0].lstrip("/")
                scope["path"] = f"/api/{raw_path}"
                
                # Clean up 'path' parameter from query string so FastAPI query validation passes
                filtered = [(k, v) for k, v in parse_qs(query_string, keep_blank_values=True).items() if k != "path"]
                new_q = []
                for k, vals in filtered:
                    for val in vals:
                        new_q.append(f"{k}={val}")
                scope["query_string"] = "&".join(new_q).encode("latin1")
            elif scope.get("path") and not scope["path"].endswith(".py"):
                pass  # Keep valid scope path
            else:
                scope["path"] = "/api"

        await self.asgi_app(scope, receive, send)

app = VercelPathMiddleware(base_app)
