"""Downloads over HTTPS with the certificates of the computer.

The packaged application carries its own OpenSSL, whose default certificate file is a path of the
machine it was built on: on another Linux computer it trusts nothing, and behind a company proxy
that re-signs HTTPS it would not trust the company's authority either. The system's bundle (the
one wget and curl use, with the company's authority when the IT department installed it) is
added, and SSL_CERT_FILE, REQUESTS_CA_BUNDLE or CURL_CA_BUNDLE are honoured. The proxy of the
environment (https_proxy, no_proxy) is used as urllib does.
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
