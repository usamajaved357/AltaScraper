"""domain/url_policy.py -- may the app fetch this URL on a user's say-so?

WHY THIS EXISTS. Several routes fetch a URL that arrived in a request: an image
link handed to /media/upload, a supplier page on the repricer, a competitor page
for optimisation. urllib will fetch anything -- file:///etc/passwd,
http://127.0.0.1:5000/..., the cloud metadata address 169.254.169.254 -- and
/media/upload SAVED what it got and served it back. That is a full-read
server-side request forgery: whoever may upload an image may read any address
the server can reach (master audit, 28 Sep 2026).

THE RULE, in one place so every fetch obeys the same one:
  * http and https only;
  * the host must resolve, and EVERY address it resolves to must be a public
    one -- not loopback, private, link-local, multicast, reserved or
    unspecified;
  * the same check again on every redirect, because a public page can answer
    "302 -> http://127.0.0.1/".

WHAT IT DOES NOT STOP: a host whose DNS answer changes between this check and
the connection (DNS rebinding). Closing that needs pinning the socket to the
checked address; the audit rated the remaining risk low for a mostly
single-user app, and it is noted rather than hidden.
"""
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_SCHEMES = ("http", "https")


def _bad_address(ip):
    a = ipaddress.ip_address(ip)
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
            or a.is_reserved or a.is_unspecified)


def refuse_reason(url, resolve=None):
    """"" when the app may fetch `url`; otherwise why not, in plain words.

    `resolve` is for tests: a function host -> [ip, ...]. Defaults to DNS.
    """
    try:
        p = urllib.parse.urlsplit(str(url or "").strip())
    except Exception:
        return "that is not a web address"
    if p.scheme.lower() not in ALLOWED_SCHEMES:
        return "only http and https addresses can be fetched"
    host = p.hostname or ""
    if not host:
        return "that web address has no host"
    try:
        if resolve is not None:
            ips = list(resolve(host))
        else:
            ips = sorted({i[4][0] for i in socket.getaddrinfo(
                host, p.port or (443 if p.scheme.lower() == "https" else 80))})
    except Exception:
        return "that address could not be found"
    if not ips:
        return "that address could not be found"
    for ip in ips:
        try:
            if _bad_address(ip.split("%")[0]):
                return ("that address points inside this server or its private "
                        "network, which the app will not fetch")
        except ValueError:
            return "that address could not be understood"
    return ""


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to somewhere refuse_reason() allows."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        why = refuse_reason(newurl)
        if why:
            raise urllib.error.URLError("redirected somewhere refused: " + why)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def urlopen(req, timeout=30, context=None):
    """urllib.request.urlopen, for a URL a USER supplied. Raises ValueError when
    the address is refused, before anything is sent."""
    url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
    why = refuse_reason(url)
    if why:
        raise ValueError(why)
    handlers = [_CheckedRedirect()]
    if context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers).open(req, timeout=timeout)
