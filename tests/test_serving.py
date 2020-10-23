import http.client
import json
import socket
import ssl
import sys
from io import BytesIO

import pytest

from werkzeug.datastructures import FileStorage
from werkzeug.serving import make_ssl_devcert
from werkzeug.test import stream_encode_multipart

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
    r = client.open()
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
    r = standard_app.open("//double-slash")
    assert "double-slash" not in r.json["HTTP_HOST"]
    assert r.json["PATH_INFO"] == "/double-slash"


def test_500_error(standard_app):
    r = standard_app.open("/crash")
    assert r.status == 500
    assert b"Internal Server Error" in r.data


@require_cryptography
def test_ssl_dev_cert(tmp_path, dev_server):
    client = dev_server(ssl_context=make_ssl_devcert(tmp_path))
    r = client.open()
    assert r.json["wsgi.url_scheme"] == "https"


@require_cryptography
def test_ssl_object(dev_server):
    client = dev_server(ssl_context="custom")
    r = client.open()
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


def test_content_type_and_length(standard_app):
    r = standard_app.open()
    assert "CONTENT_TYPE" not in r.json
    assert "CONTENT_LENGTH" not in r.json

    r = standard_app.open(data=b"{}", headers={"content-type": "application/json"})
    assert r.json["CONTENT_TYPE"] == "application/json"
    assert r.json["CONTENT_LENGTH"] == "2"


@pytest.mark.parametrize("send_length", [False, True])
@pytest.mark.skipif(sys.version_info < (3, 7), reason="requires Python >= 3.7")
def test_chunked_encoding(monkeypatch, dev_server, send_length):
    stream, length, boundary = stream_encode_multipart(
        {
            "value": "this is text",
            "file": FileStorage(
                BytesIO(b"this is a file"),
                filename="test.txt",
                content_type="text/plain",
            ),
        }
    )
    headers = {"content-type": f"multipart/form-data; boundary={boundary}"}

    if send_length:
        headers["transfer-encoding"] = "chunked"
        headers["content-length"] = str(length)

    client = dev_server("data")
    # Small block size to produce multiple chunks.
    conn = client.connect(blocksize=128)
    conn.putrequest("POST", "/")
    conn.putheader("Transfer-Encoding", "chunked")
    conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")

    # Sending the content-length header with chunked is invalid, but if
    # a client does send it the server should ignore it. Previously the
    # multipart parser would crash. Python's higher-level functions
    # won't send the header, which is why we use conn.put in this test.
    if send_length:
        conn.putheader("Content-Length", "invalid")

    conn.endheaders(stream, encode_chunked=True)
    r = conn.getresponse()
    data = json.load(r)
    r.close()
    assert data["form"]["value"] == "this is text"
    assert data["files"]["file"] == "this is a file"
    environ = data["environ"]
    assert environ["HTTP_TRANSFER_ENCODING"] == "chunked"
    assert "HTTP_CONTENT_LENGTH" not in environ
    assert environ["wsgi.input_terminated"]
