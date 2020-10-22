import json
import socket

import pytest

try:
    import cryptography
except ImportError:
    cryptography = None

requires_cryptography = pytest.mark.skipif(
    cryptography is None, reason="'cryptography' is not installed"
)


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({}, id="http"),
        pytest.param({"ssl_context": "adhoc"}, id="https", marks=requires_cryptography),
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
