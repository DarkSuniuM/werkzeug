import http.client
import json
import socket
import ssl
import sys
import urllib.request
from itertools import count
from pathlib import Path
from pathlib import PurePath

import pytest
from xprocess import ProcessStarter

from werkzeug.utils import cached_property

run_path = str(Path(__file__).parent / "test_apps" / "run.py")


def get_free_port():
    gen_port = count(49152)
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    while True:
        port = next(gen_port)

        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            continue

        s.close()
        return port


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.host)


class UnixSocketHandler(urllib.request.AbstractHTTPHandler):
    def unix_request(self, req):
        h = s = PurePath(req.selector)

        while not h.suffix == ".sock":
            h = h.parent

        req.host = str(h)
        req.selector = f"/{s.relative_to(h)}" if s != h else "/"
        return self.do_request_(req)

    def unix_open(self, req):
        return self.do_open(UnixSocketHTTPConnection, req)


class DevServerClient:
    opener = urllib.request.build_opener(
        UnixSocketHandler, urllib.request.HTTPSHandler(context=ssl.SSLContext())
    )

    def __init__(self, kwargs):
        host = kwargs.get("hostname", "127.0.0.1")

        if not host.startswith("unix"):
            port = kwargs.get("port")

            if port is None:
                kwargs["port"] = port = get_free_port()

            scheme = "https" if "ssl_context" in kwargs else "http"
            self.addr = f"{host}:{port}"
            self.url = f"{scheme}://{self.addr}"
        else:
            self.addr = host[7:]
            self.url = host

        self.log_path = None

    def connect(self):
        protocol = self.url.partition(":")[0]

        if protocol == "https":
            return http.client.HTTPSConnection(self.addr, context=ssl.SSLContext())

        if protocol == "unix":
            return UnixSocketHTTPConnection(self.addr)

        return http.client.HTTPConnection(self.addr)

    def get(self, path="", **kwargs):
        with self.opener.open(f"{self.url}{path}", **kwargs) as response:
            response.data = response.read()

        if response.headers["Content-Type"].startswith("application/json"):
            response.json = json.loads(response.data)
        else:
            response.json = None

        return response


@pytest.fixture()
def dev_server(xprocess, request):
    xp_name = f"dev_server-{request.node.name}"

    def start_dev_server(name="echo_environ", **kwargs):
        client = DevServerClient(kwargs)

        class Starter(ProcessStarter):
            args = [sys.executable, run_path, name, json.dumps(kwargs)]

            @cached_property
            def pattern(self):
                client.get("/get-pid").close()
                return "GET /get-pid"

        _, client.log_path = xprocess.ensure(xp_name, Starter, restart=True)
        return client

    yield start_dev_server
    xprocess.getinfo(xp_name).terminate()


@pytest.fixture()
def standard_app(dev_server):
    return dev_server()
