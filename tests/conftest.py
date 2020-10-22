import http.client
import json
import socket
import ssl
import sys
import urllib.request
from itertools import count
from pathlib import Path
from pathlib import PurePath
from typing import List
from typing import Type
from typing import Union

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


handlers: List[Union[Type[urllib.request.BaseHandler], urllib.request.BaseHandler]] = [
    UnixSocketHandler
]

if hasattr(urllib.request, "HTTPSHandler"):
    handlers.append(urllib.request.HTTPSHandler(context=ssl.SSLContext()))

opener = urllib.request.build_opener(*handlers)
del handlers


class DevServerClient:
    def __init__(self, url):
        self.url = url
        self.log_path = None

    def get(self, path="", **kwargs):
        return opener.open(f"{self.url}{path}", **kwargs)


@pytest.fixture(name="dev_server")
def dev_server_factory(xprocess, request):
    xp_name = f"dev_server-{request.node.name}"

    def dev_server(name="echo_environ", **kwargs):
        hostname = kwargs.get("hostname", "127.0.0.1")

        if not hostname.startswith("unix"):
            port = kwargs.get("port")

            if port is None:
                kwargs["port"] = port = get_free_port()

            scheme = "https" if "ssl_context" in kwargs else "http"
            url = f"{scheme}://{hostname}:{port}"
        else:
            url = hostname

        client = DevServerClient(url)

        class Starter(ProcessStarter):
            args = [sys.executable, run_path, name, json.dumps(kwargs)]

            @cached_property
            def pattern(self):
                client.get("/get-pid").close()
                return "GET /get-pid"

        _, client.log_path = xprocess.ensure(xp_name, Starter, restart=True)
        return client

    yield dev_server
    xprocess.getinfo(xp_name).terminate()
