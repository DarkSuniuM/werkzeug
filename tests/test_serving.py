import http.client
import json
import socket
import ssl

import pytest

from werkzeug.serving import make_ssl_devcert

try:
    import cryptography
except ImportError:
    cryptography = None

require_cryptography = pytest.mark.skipif(
    cryptography is None, reason="'cryptography' is not installed"
)


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({}, id="http"),
        pytest.param({"ssl_context": "adhoc"}, id="https", marks=require_cryptography),
        pytest.param({"use_reloader": True}, id="reloader"),
        pytest.param(
            {"hostname": "unix"},
            id="unix socket",
            marks=pytest.mark.skipif(
                not hasattr(socket, "AF_UNIX"), reason="requires unix socket support"
            ),
        ),
    ],
)
def test_server(tmp_path, dev_server, kwargs: dict):
    if kwargs.get("hostname") == "unix":
        kwargs["hostname"] = f"unix://{tmp_path / 'test.sock'}"

    client = dev_server(**kwargs)
    r = client.get()
    assert r.status == 200
    assert r.json["PATH_INFO"] == "/"


def test_untrusted_host(standard_app):
    conn = standard_app.connect()
    conn.request(
        "GET",
        "http://missing.test:1337/index.html#ignore",
        headers={"x-base-url": standard_app.url},
    )
    response = conn.getresponse()
    environ = json.load(response)
    response.close()
    conn.close()
    assert environ["HTTP_HOST"] == "missing.test:1337"
    assert environ["PATH_INFO"] == "/index.html"
    host, _, port = environ["HTTP_X_BASE_URL"].rpartition(":")
    assert environ["SERVER_NAME"] == host.partition("http://")[2]
    assert environ["SERVER_PORT"] == port


def test_double_slash_path(standard_app):
    r = standard_app.get("//double-slash")
    assert "double-slash" not in r.json["HTTP_HOST"]
    assert r.json["PATH_INFO"] == "/double-slash"


def test_500_error(standard_app):
    r = standard_app.get("/crash")
    assert r.status == 500
    assert b"Internal Server Error" in r.data


@require_cryptography
def test_ssl_dev_cert(tmp_path, dev_server):
    client = dev_server(ssl_context=make_ssl_devcert(tmp_path))
    r = client.get()
    assert r.json["wsgi.url_scheme"] == "https"


@require_cryptography
def test_ssl_object(dev_server):
    client = dev_server(ssl_context="custom")
    r = client.get()
    assert r.json["wsgi.url_scheme"] == "https"


def test_wrong_protocol(standard_app):
    """An HTTPS request to an HTTP server doesn't show a traceback.
    https://github.com/pallets/werkzeug/pull/838
    """
    conn = http.client.HTTPSConnection(standard_app.addr)

    with pytest.raises(ssl.SSLError):
        conn.request("GET", f"https://{standard_app.addr}")

    with standard_app.open_log() as f:
        log = f.read()

    assert "Traceback" not in log
