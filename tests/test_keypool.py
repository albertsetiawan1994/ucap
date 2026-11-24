"""Multi-key switching, quota memory and migration (Gemini mocked)."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ucap import gemini_client as gc
from ucap import storage
from ucap.errors import UcapError
from ucap.keypool import KeyPool, next_pacific_midnight, parse_quota

DAILY_429 = ("429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'details': [{'@type': "
             "'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaId': "
             "'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]}, {'@type': "
             "'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '36s'}]}}")
MINUTE_429 = ("429 RESOURCE_EXHAUSTED. {'error': {'details': [{'violations': [{'quotaId': "
              "'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'}]}, {'retryDelay': '12.5s'}]}}")


class ApiErr(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc).timestamp()


class Clock:
    def __init__(self, t=utc(2026, 11, 24, 12)):
        self.t = t

    def __call__(self):
        return self.t


class Gemini:
    """Fake API: behaviour[(secret, model)] is an exception or None (= success). Records every call."""

    def __init__(self, behaviour=None, clock=None, cost=0.0):
        self.behaviour, self.calls, self.clock, self.cost = behaviour or {}, [], clock, cost

    def factory(self, secret):
        gem = self

        class Models:
            def generate_content(self, model, contents, config):
                gem.calls.append((secret, model))
                if gem.clock:
                    gem.clock.t += gem.cost
                exc = gem.behaviour.get((secret, model))
                if exc:
                    raise exc
                return SimpleNamespace(text=f"ok from {secret}/{model}")
        return SimpleNamespace(models=Models())


def make_pool(n=3, clock=None, path=None, **flags):
    keys = [{"id": str(i), "label": f"Project {chr(64 + i)}", "enabled": True, "invalid": False}
            for i in range(1, n + 1)]
    return KeyPool(keys, lambda kid: f"S{kid}", path, clock or Clock())


def run(pool, gem, model="gemini-3.5-flash-lite", available=None, clock=None):
    return gc.transcribe(b"RIFF", pool, model, "SYS", available, client_factory=gem.factory,
                         clock=clock or (lambda: 0.0))


Q = lambda: ApiErr(429, MINUTE_429)  # noqa: E731
BUSY = lambda: ApiErr(503, "UNAVAILABLE high demand")  # noqa: E731


# ---- order of attempts --------------------------------------------------------

def test_first_key_first_model_success_is_not_a_switch():
    gem = Gemini()
    r = run(make_pool(), gem)
    assert gem.calls == [("S1", "gemini-3.5-flash-lite")]
    assert r["model"] == "gemini-3.5-flash-lite" and r["label"] == "Project A" and not r["switched"]
    assert r["text"] == "ok from S1/gemini-3.5-flash-lite"


def test_quota_rotates_keys_then_falls_back_to_next_model():
    m = "gemini-3.5-flash-lite"
    gem = Gemini({("S1", m): Q(), ("S2", m): Q(), ("S3", m): Q(), ("S1", "gemini-3.1-flash-lite"): Q()})
    r = run(make_pool(), gem, m)
    assert gem.calls == [("S1", m), ("S2", m), ("S3", m),
                         ("S1", "gemini-3.1-flash-lite"), ("S2", "gemini-3.1-flash-lite")]
    assert r["label"] == "Project B" and r["model"] == "gemini-3.1-flash-lite" and r["switched"]


def test_busy_or_missing_model_moves_to_next_model_with_same_key_order():
    m = "gemini-3.8-flash"
    gem = Gemini({("S1", m): BUSY(), ("S1", "gemini-3.1-flash-lite"): ApiErr(404, "no longer available")})
    r = run(make_pool(), gem, m)
    assert gem.calls == [("S1", m), ("S1", "gemini-3.1-flash-lite"), ("S1", "gemini-3.5-flash-lite")]
    assert r["label"] == "Project A" and r["model"] == "gemini-3.5-flash-lite"


def test_disabled_keys_are_never_used_and_no_usable_key_is_no_key():
    pool = make_pool()
    pool.keys[0]["enabled"] = False
    gem = Gemini()
    assert run(pool, gem)["label"] == "Project B"
    for k in pool.keys:
        k["enabled"] = False
    with pytest.raises(UcapError) as e:
        run(pool, gem)
    assert e.value.code == "no_key"


# ---- invalid keys ---------------------------------------------------------------

def test_invalid_key_is_marked_and_skipped_next_time():
    m = "gemini-3.5-flash-lite"
    pool = make_pool()
    gem = Gemini({("S1", m): ApiErr(400, "API key not valid. Please pass a valid API key.")})
    assert run(pool, gem)["label"] == "Project B"
    assert pool.keys[0]["invalid"] is True
    gem.calls.clear()
    run(pool, gem)
    assert gem.calls == [("S2", m)]  # key 1 not even tried
    pool.mark_invalid("1", False)  # user re-tested it successfully
    gem.calls.clear()
    gem.behaviour.clear()
    run(pool, gem)
    assert gem.calls == [("S1", m)]


# ---- quota memory -----------------------------------------------------------------

def test_parse_quota_daily_vs_minute():
    assert parse_quota(DAILY_429) == (True, 36.0)
    assert parse_quota(MINUTE_429) == (False, 12.5)
    assert parse_quota("429 RESOURCE_EXHAUSTED") == (False, None)


def test_daily_quota_blocks_until_pacific_midnight_and_minute_uses_retry_delay():
    clock = Clock(utc(2026, 11, 24, 12))  # 04:00 PST
    pool = make_pool(clock=clock)
    until = pool.mark_quota("1", "m", DAILY_429)
    assert until == utc(2026, 11, 25, 8)  # midnight PST = 08:00 UTC
    assert pool.mark_quota("2", "m", MINUTE_429) == clock.t + 12.5
    assert pool.mark_quota("3", "m", "429 quota") == clock.t + 60
    clock.t += 61
    assert pool.blocked_until("3", "m") is None and pool.blocked_until("1", "m") == until


@pytest.mark.parametrize("now,expected", [
    (utc(2026, 3, 7, 20), utc(2026, 3, 8, 8)),    # Sat noon PST -> Sun 00:00 PST (still standard time)
    (utc(2026, 3, 8, 20), utc(2026, 3, 9, 7)),    # day DST starts -> next midnight is PDT (UTC-7)
    (utc(2026, 10, 31, 20), utc(2026, 11, 1, 7)),  # midnight before DST ends is still PDT
    (utc(2026, 11, 1, 20), utc(2026, 11, 2, 8)),  # after DST ends -> PST (UTC-8)
    (utc(2026, 11, 25, 7, 59), utc(2026, 11, 25, 8)),  # one minute before Pacific midnight
])
def test_next_pacific_midnight_handles_dst(now, expected):
    assert next_pacific_midnight(now) == expected


def test_exhausted_pairs_are_skipped_without_a_request():
    m = "gemini-3.5-flash-lite"
    pool = make_pool()
    gem = Gemini({("S1", m): ApiErr(429, DAILY_429)})
    run(pool, gem)
    gem.calls.clear()
    r = run(pool, gem)
    assert gem.calls == [("S2", m)] and r["switched"]
    assert pool.today_counts("1") == {m: 1} and pool.today_counts("2") == {m: 2}


def test_all_exhausted_raises_quota_without_calls():
    pool = make_pool(n=2)
    for kid in ("1", "2"):
        for m in gc.fallback_order("gemini-3.5-flash-lite"):
            pool.mark_quota(kid, m, DAILY_429)
    gem = Gemini()
    with pytest.raises(UcapError) as e:
        run(pool, gem)
    assert e.value.code == "quota" and gem.calls == []
    assert pool.earliest_reset() == next_pacific_midnight(pool.clock())


def test_daily_state_and_counts_persist_and_expire(tmp_path):
    path = tmp_path / "quota.json"
    clock = Clock(utc(2026, 11, 24, 12))
    pool = make_pool(clock=clock, path=path)
    pool.mark_quota("1", "m", DAILY_429)
    pool.count("1", "m")
    again = make_pool(clock=clock, path=path)
    assert again.blocked_until("1", "m") == utc(2026, 11, 25, 8)
    assert again.today_counts("1") == {"m": 1}
    assert "S1" not in path.read_text()  # never a secret in the state file
    clock.t = utc(2026, 11, 25, 9)  # after Pacific midnight
    later = make_pool(clock=clock, path=path)
    assert later.blocked_until("1", "m") is None and later.today_counts("1") == {}
    later.forget("1")
    assert json.loads(path.read_text())["blocks"] == {}


# ---- budget -----------------------------------------------------------------------

def test_attempt_budget_caps_requests_at_eight():
    m = "gemini-3.5-flash-lite"
    pool = make_pool(n=10)
    gem = Gemini({(f"S{i}", mm): Q() for i in range(1, 11) for mm in gc.fallback_order(m)})
    with pytest.raises(UcapError) as e:
        run(pool, gem)
    assert len(gem.calls) == gc.MAX_ATTEMPTS == 8 and e.value.code == "quota"


def test_time_budget_stops_after_about_thirty_seconds():
    clock = Clock(0.0)
    gem = Gemini({("S1", mm): BUSY() for mm in gc.fallback_order("gemini-3.8-flash")}, clock=clock, cost=12.0)
    with pytest.raises(UcapError) as e:
        run(make_pool(n=1), gem, "gemini-3.8-flash", clock=clock)
    assert e.value.code == "busy" and len(gem.calls) == 3  # 0s, 12s, 24s; 36s > budget


# ---- migration --------------------------------------------------------------------

class FakeKeyring:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def get_password(self, service, user):
        return self.data.get((service, user))

    def set_password(self, service, user, pw):
        self.data[(service, user)] = pw

    def delete_password(self, service, user):
        self.data.pop((service, user))


def test_old_single_key_becomes_key_one_utama(tmp_path):
    kr = FakeKeyring({("Ucap", "gemini_api_key"): "AIzaOLDKEY123"})
    s = storage.Settings(tmp_path / "settings.json")
    assert storage.migrate_single_key(s, kr) is True
    assert s["keys"] == [{"id": "1", "label": "Utama", "enabled": True, "invalid": False}]
    assert storage.get_key_secret("1", kr) == "AIzaOLDKEY123"
    assert ("Ucap", "gemini_api_key") not in kr.data
    s.save()
    assert "AIzaOLDKEY123" not in (tmp_path / "settings.json").read_text()
    # runs only once, even if the user later removes every key
    s["keys"].clear()
    kr.set_password("Ucap", "gemini_api_key", "AIzaOTHER")
    assert storage.migrate_single_key(s, kr) is False and s["keys"] == []


def test_migration_without_old_key_just_marks_done(tmp_path):
    s = storage.Settings(tmp_path / "settings.json")
    assert storage.migrate_single_key(s, FakeKeyring()) is False
    assert s["keys_migrated"] is True and s["keys"] == []
