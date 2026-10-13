"""Entrypoint: starts uvicorn, with optional TLS.

Kept out of the Dockerfile CMD so the TLS flags come from configuration (the
config file or `VOZLAB_TLS_CERT` / `VOZLAB_TLS_KEY`) instead of a shell
one-liner that has to be kept in sync with the docs.
"""

import os


def ssl_kwargs() -> dict:
    """uvicorn ssl arguments, when a certificate is configured."""
    cert = os.environ.get("VOZLAB_TLS_CERT") or ""
    key = os.environ.get("VOZLAB_TLS_KEY") or ""
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
        host=os.environ.get("VOZLAB_HOST", "0.0.0.0"),  # nosec B104
        port=int(os.environ.get("VOZLAB_PORT", "8080")),
        proxy_headers=False,
        **ssl_kwargs(),
    )


if __name__ == "__main__":
    main()
