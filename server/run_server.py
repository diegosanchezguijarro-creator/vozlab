"""Entrypoint: starts uvicorn, with optional TLS.

Kept out of the Dockerfile CMD so the TLS flags come from configuration (the
config file or `SCRIBE_TLS_CERT` / `SCRIBE_TLS_KEY`) instead of a shell
one-liner that has to be kept in sync with the docs.
"""

import os


def _env(suffix: str, default: str = "") -> str:
    """Read `SCRIBE_<suffix>`, falling back to the pre-rename `VOZLAB_<suffix>`."""
    return (os.environ.get(f"SCRIBE_{suffix}")
            or os.environ.get(f"VOZLAB_{suffix}")
            or default)


def ssl_kwargs() -> dict:
    """uvicorn ssl arguments, when a certificate is configured."""
    cert = _env("TLS_CERT")
    key = _env("TLS_KEY")
    if not cert:
        return {}
    if not key:
        key = cert
    return {"ssl_certfile": cert, "ssl_keyfile": key}


def main() -> None:
    import uvicorn          # imported here so the module works without it

    uvicorn.run(
        "server:app",
        # binding every interface is the point: the app connects over the LAN.
        # Access is controlled by the bearer token, not by the bind address.
        host=_env("HOST", "0.0.0.0"),  # nosec B104
        port=int(_env("PORT", "8080")),
        proxy_headers=False,
        **ssl_kwargs(),
    )


if __name__ == "__main__":
    main()
