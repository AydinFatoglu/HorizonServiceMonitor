"""Read-only, loopback-only Horizon Console HTTP availability probe."""
import socket
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

ADMIN_URL = 'https://127.0.0.1/admin/'
WEB_REFRESH_MS = 45_000
WEB_TIMEOUT = 10


def _local_admin_url(url):
    parsed = urlsplit(url)
    # Do not follow a server redirect to a load balancer, HTML Access or an
    # external login page and mistakenly report that as this server's console.
    return (parsed.scheme in ('http', 'https')
            and parsed.hostname in ('127.0.0.1', '::1')
            and parsed.username is None and parsed.password is None
            and (parsed.path == '/admin' or parsed.path.startswith('/admin/')))


class AdminRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _local_admin_url(newurl):
            raise HTTPError(req.full_url, code, 'Redirect outside the local admin console', headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_admin_web(url=ADMIN_URL, timeout=WEB_TIMEOUT):
    """GET headers only; HTTP 200 measures availability, not login or TLS trust."""
    started = time.monotonic()
    result = {'kind': 'connection_error', 'code': None, 'detail': '', 'url': url}
    try:
        if not _local_admin_url(url):
            raise ValueError('Only loopback /admin URLs are supported')
        # This probe sends no credentials and stays on numeric loopback. A
        # server's FQDN certificate normally does not cover 127.0.0.1.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), AdminRedirectHandler())
        request = Request(url, headers={'User-Agent': 'HorizonServiceMonitor', 'Cache-Control': 'no-cache'}, method='GET')
        with opener.open(request, timeout=timeout) as response:
            result.update(kind='http', code=response.status, url=response.url)
    except HTTPError as exc:
        result.update(kind='http', code=exc.code, detail=str(exc.reason))
        exc.close()
    except (TimeoutError, socket.timeout) as exc:
        result.update(kind='timeout', detail=str(exc))
    except URLError as exc:
        result.update(kind='timeout' if isinstance(exc.reason, TimeoutError) else 'connection_error', detail=str(exc.reason))
    except (OSError, ValueError) as exc:
        result['detail'] = str(exc)
    result['seconds'] = time.monotonic() - started
    return result
