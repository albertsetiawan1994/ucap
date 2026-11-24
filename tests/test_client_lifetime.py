from ucap import gemini_client as gc


def test_make_client_reuses_one_client_per_key(monkeypatch):
    made = []

    class FakeClient:
        def __init__(self, api_key, http_options=None):
            made.append(api_key)

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", FakeClient)
    gc._CLIENTS.clear()
    a1 = gc._make_client("k1")
    a2 = gc._make_client("k1")
    b = gc._make_client("k2")
    assert a1 is a2 and a1 is not b
    assert made == ["k1", "k2"]
    gc._drop_client("k1")
    assert gc._make_client("k1") is not a1
    gc._CLIENTS.clear()


def test_closed_error_detected():
    assert gc._is_closed_error(RuntimeError("Cannot send a request, as the client has been closed."))
    assert not gc._is_closed_error(RuntimeError("quota"))
