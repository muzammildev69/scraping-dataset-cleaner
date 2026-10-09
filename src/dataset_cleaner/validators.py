"""Syntax-only validation and conservative normalisation of emails and URLs.

Nothing here talks to the network. A value that passes validation is
well-formed; it is *not* guaranteed to exist, resolve or accept mail.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_LOCAL_ATOM = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_LOCAL_PART = re.compile(rf"^{_LOCAL_ATOM}(?:\.{_LOCAL_ATOM})*$")
_HAS_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_URL_PARTS = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://([^/?#]*)(.*)$", re.DOTALL)
_DUPLICATE_SUFFIX = re.compile(r"_\d+$")

_EMAIL_COLUMN_NAMES = {"email", "email_address", "e_mail"}
_EMAIL_COLUMN_SUFFIXES = ("_email", "_email_address")
_URL_COLUMN_NAMES = {"url", "website", "link", "homepage"}
_URL_COLUMN_SUFFIXES = ("_url", "_website", "_link")
_ALLOWED_URL_SCHEMES = {"http", "https"}


def is_email_column(name: str) -> bool:
    """Return True if a normalised column name looks like an email column."""
    base = _DUPLICATE_SUFFIX.sub("", name)
    return base in _EMAIL_COLUMN_NAMES or base.endswith(_EMAIL_COLUMN_SUFFIXES)


def is_url_column(name: str) -> bool:
    """Return True if a normalised column name looks like a URL column."""
    base = _DUPLICATE_SUFFIX.sub("", name)
    return base in _URL_COLUMN_NAMES or base.endswith(_URL_COLUMN_SUFFIXES)


def _is_valid_domain(domain: str) -> bool:
    """Check a DNS name with at least two labels and an alphabetic-looking TLD."""
    if not domain or len(domain) > 253:
        return False
    try:
        ascii_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return False
    labels = ascii_domain.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        return False
    tld = labels[-1]
    return len(tld) >= 2 and not tld.isdigit()


def _is_valid_host(host: str) -> bool:
    """Check a URL host: a domain name, localhost, or an IPv4/IPv6 address."""
    if host == "localhost":
        return True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return _is_valid_domain(host)
    return True


def normalize_email(value: str) -> str:
    """Trim surrounding whitespace and lowercase the whole address."""
    return value.strip().lower()


def is_valid_email(value: str) -> bool:
    """Check email *syntax* (single ``@``, plain ASCII local part, valid domain).

    Quoted local parts, comments and internationalised local parts are not
    supported and are reported as invalid.
    """
    if not value or len(value) > 254 or any(char.isspace() for char in value):
        return False
    local, separator, domain = value.rpartition("@")
    if not separator or "@" in local or len(local) > 64:
        return False
    return bool(_LOCAL_PART.match(local)) and _is_valid_domain(domain)


def normalize_url(value: str, *, add_scheme: bool = False, strip_params: bool = False) -> str:
    """Normalise a URL without touching its path, query or fragment.

    Always: trim surrounding whitespace and lowercase the scheme and host.
    Optionally: prepend ``https://`` when the scheme is missing, and drop the
    query string and fragment. Values that cannot be parsed are returned
    trimmed but otherwise untouched so validation can flag them.
    """
    url = value.strip()
    if not url:
        return url
    if add_scheme and not _HAS_SCHEME.match(url):
        url = f"https:{url}" if url.startswith("//") else f"https://{url}"
    match = _URL_PARTS.match(url)
    if not match:
        return url
    scheme, authority, rest = match.groups()
    userinfo, at_sign, host_port = authority.rpartition("@")
    if strip_params:
        rest = re.split(r"[?#]", rest, maxsplit=1)[0]
    return f"{scheme.lower()}://{userinfo}{at_sign}{host_port.lower()}{rest}"


def is_valid_url(value: str) -> bool:
    """Check http(s) URL *syntax*: scheme, host, port and no whitespace.

    A valid result says nothing about whether the site is online.
    """
    if not value or any(char.isspace() or ord(char) < 32 for char in value):
        return False
    try:
        parts = urlsplit(value)
        host = parts.hostname
        _ = parts.port  # raises ValueError for a malformed or out-of-range port
    except ValueError:
        return False
    if parts.scheme.lower() not in _ALLOWED_URL_SCHEMES or not host:
        return False
    return _is_valid_host(host)
