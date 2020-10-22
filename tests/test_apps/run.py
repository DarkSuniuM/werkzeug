import json
import os
import sys
from importlib import import_module

from werkzeug import Request
from werkzeug import Response
from werkzeug import run_simple

name = sys.argv[1]
mod = import_module(name)


@Request.application
def app(request):
    if request.path == "/get-pid":
        return Response(str(os.getpid()))

    return Response.from_app(mod.app, request.environ)


kwargs = getattr(mod, "kwargs", {})
kwargs.update(hostname="127.0.0.1", port=0, application=mod.app)
kwargs.update(json.loads(sys.argv[2]))
run_simple(**kwargs)
