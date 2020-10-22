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

    with client.get() as response:
        data = json.load(response)

    assert response.status == 200
    assert data["PATH_INFO"] == "/"
