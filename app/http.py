"""Shared HTTPS configuration."""

import ssl
from urllib.request import urlopen

import certifi

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def open_url(request, timeout):
    return urlopen(request, timeout=timeout, context=SSL_CONTEXT)
