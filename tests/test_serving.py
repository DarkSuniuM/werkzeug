import json


def test_server(dev_server):
    client = dev_server(use_reloader=True)

    with client.get() as response:
        data = json.load(response)

    assert response.status == 200
    assert data["PATH_INFO"] == "/"
