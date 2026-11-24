from types import SimpleNamespace

import pytest

from ucap import gemini_client as gc
from ucap.errors import UcapError


def test_prompt_contains_core_rules():
    p = gc.build_system_prompt("auto", "casual")
    for needle in ("ONLY the final text", "anu", "apa namanya", "um", "jam 6", "6pm", "numbered list",
                   "NEVER answer", "Casual", "never translate"):
        assert needle.lower() in p.lower(), needle


def test_prompt_language_and_style_switch():
    assert "uses English" in gc.build_system_prompt("en", "formal")
    assert "uses Indonesian" in gc.build_system_prompt("id", "formal")
    assert "Formal:" in gc.build_system_prompt("id", "formal")
    assert "Very casual:" in gc.build_system_prompt("auto", "very_casual")
    # unknown values fall back instead of crashing
    p = gc.build_system_prompt("xx", "weird")
    assert "Indonesian, English, or a mix" in p and "Casual:" in p


def test_prompt_dictionary_and_triggers():
    p = gc.build_system_prompt("auto", "casual", ["PT Sinar Jaya", " ", "Kubernetes"], ["tanda tangan email"])
    assert "- PT Sinar Jaya" in p and "- Kubernetes" in p
    assert "- tanda tangan email" in p
    assert "Personal dictionary" not in gc.build_system_prompt("auto", "casual", [], [])


class FakeModels:
    """generate_content fails for models listed in `fail` (model -> exception), else returns `text`."""

    def __init__(self, text=None, exc=None, fail=None, listing=()):
        self.text, self.exc, self.fail, self.listing, self.calls = text, exc, fail or {}, listing, []

    def generate_content(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        if kw["model"] in self.fail:
            raise self.fail[kw["model"]]
        return SimpleNamespace(text=self.text)

    def list(self):
        if self.exc:
            raise self.exc
        return list(self.listing)


def client(**kw):
    return SimpleNamespace(models=FakeModels(**kw))


class ApiErr(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


class ReadTimeout(Exception):
    pass


class ConnectTimeout(Exception):
    pass


@pytest.mark.parametrize("exc,code", [
    (ApiErr(400, "API key not valid. Please pass a valid API key."), "invalid_key"),
    (ApiErr(403, "PERMISSION_DENIED"), "invalid_key"),
    (ApiErr(429, "RESOURCE_EXHAUSTED: quota"), "quota"),
    (ApiErr(404, "models/foo is not found for api version v1"), "model"),
    (ApiErr(404, "This model models/gemini-2.5-flash is no longer available to new users."), "model"),
    (ApiErr(503, "UNAVAILABLE. This model is currently experiencing high demand."), "busy"),
    (RuntimeError("The model is overloaded. Please try again later."), "busy"),
    (ReadTimeout("The read operation timed out"), "busy"),
    (ConnectTimeout("timed out"), "offline"),
    (ConnectionError("getaddrinfo failed"), "offline"),
    (RuntimeError("boom"), "unknown"),
])
def test_error_mapping(exc, code):
    assert gc.classify_error(exc).code == code


def test_fallback_order_skips_duplicates_and_unavailable():
    assert gc.fallback_order("gemini-3.8-flash") == [
        "gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.6-flash"]
    assert gc.fallback_order("gemini-3.5-flash-lite") == [
        "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash"]
    assert gc.fallback_order("gemini-3.8-flash", ["gemini-3.8-flash", "gemini-3.6-flash"]) == [
        "gemini-3.8-flash", "gemini-3.6-flash"]


def M(name, actions=("generateContent",)):
    return SimpleNamespace(name=f"models/{name}", supported_actions=list(actions))


def test_filter_models_hides_non_dictation_and_sorts():
    listing = [M("gemini-3.8-flash"), M("gemini-3.5-flash"), M("gemini-3.1-flash-lite"), M("gemini-3.6-flash"),
               M("gemini-3.5-flash-lite"), M("gemini-3.7-flash"), M("gemini-3.5-pro"),
               M("gemini-3.6-flash-image"), M("nano-banana-pro"), M("deep-research-preview"),
               M("antigravity-1"), M("gemini-embedding-2", ("embedContent",)), M("gemini-3.5-flash-tts"),
               M("gemma-4-27b-it"), M("gemini-3.9-flash", ("countTokens",)),
               M("gemini-2.5-flash"), M("gemini-2.5-flash-lite")]
    assert gc.filter_models(listing) == [
        "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
        "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
        "gemini-3.5-pro"]


def test_test_key_reports_key_and_model_separately():
    r = gc.test_key("k", "gemini-3.5-flash-lite", client=client(text="OK", listing=[M("gemini-3.5-flash-lite")]))
    assert r["models"] == ["gemini-3.5-flash-lite"] and r["model_error"] is None and r["elapsed"] >= 0
    r = gc.test_key("k", "gemini-2.5-flash", client=client(
        listing=[M("gemini-3.5-flash-lite")], fail={"gemini-2.5-flash": ApiErr(404, "no longer available")}))
    assert r["model_error"].code == "model" and r["models"] == ["gemini-3.5-flash-lite"]
    with pytest.raises(UcapError) as e:
        gc.test_key("k", "m", client=client(exc=ApiErr(400, "API key not valid")))
    assert e.value.code == "invalid_key"
