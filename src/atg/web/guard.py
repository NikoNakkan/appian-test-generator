"""Who may talk to the local web tool, and the headers every response carries.

The server listens on 127.0.0.1 only, but a web page open in the same browser could still
reach it: through DNS rebinding (a hostile name that resolves to 127.0.0.1) or a cross-site
POST that starts an import. So every request must name this machine in its Host header, and a
POST that says where it comes from (Origin) must come from this tool itself.
"""

from __future__ import annotations

_LOCAL_NAMES = ("127.0.0.1", "localhost")

# The UI is plain files from this server: no outside scripts, styles, fonts or frames.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def allowed_host(host: str | None, port: int) -> bool:
    return host in {f"{name}:{port}" for name in _LOCAL_NAMES}


def allowed_origin(origin: str | None, port: int) -> bool:
    """No Origin header (a script or curl on this machine) is fine; a browser's must be ours."""
    return origin is None or origin in {f"http://{name}:{port}" for name in _LOCAL_NAMES}
