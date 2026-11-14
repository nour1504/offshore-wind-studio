"""Downloads over HTTPS with the computer's own certificates.

The bundled OpenSSL looks for certificates where the build machine had them: on another Linux it
trusts nothing, nor a company proxy that re-signs HTTPS. The system's bundle (the one wget and curl
use) is added, SSL_CERT_FILE, REQUESTS_CA_BUNDLE and CURL_CA_BUNDLE are honoured, and the
environment's proxy (https_proxy, no_proxy) is used as urllib does.
"""

import os
import ssl
import urllib.request
from functools import cache
from typing import Any

# Bundles of the usual Linux distributions (Debian/Ubuntu, Fedora/RHEL, openSUSE, Alpine)
SYSTEM_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/ca-bundle.pem",
    "/etc/ssl/cert.pem",
)


@cache
def context() -> ssl.SSLContext:
    found = ssl.create_default_context()
    for variable in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        path = os.environ.get(variable, "")
        if path and os.path.isfile(path):
            found.load_verify_locations(cafile=path)
    for path in SYSTEM_BUNDLES:
        if os.path.isfile(path):
            try:
                found.load_verify_locations(cafile=path)
            except (OSError, ssl.SSLError):
                continue
            break
    return found


def urlopen(request: str | urllib.request.Request, timeout: float = 30) -> Any:
    """urllib.request.urlopen with the certificates of the computer."""
    return urllib.request.urlopen(request, timeout=timeout, context=context())
