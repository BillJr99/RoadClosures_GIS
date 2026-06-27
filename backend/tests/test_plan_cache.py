from app import config
from app.services import plan_cache


def test_plan_cache_key_is_stable_and_input_sensitive() -> None:
    req = {"lat": 40.1, "lon": -75.3, "hose_max_ft": 500}
    key1 = plan_cache.plan_cache_key(req, "100:200:EPSG:4326")
    key2 = plan_cache.plan_cache_key(dict(req), "100:200:EPSG:4326")
    assert key1 == key2
    # Different request or graph -> different key.
    assert plan_cache.plan_cache_key({**req, "hose_max_ft": 600}, "100:200:EPSG:4326") != key1
    assert plan_cache.plan_cache_key(req, "101:200:EPSG:4326") != key1


def test_plan_cache_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config, "PLAN_CACHE_DIR", tmp_path)
    assert plan_cache.load_cached_plan("missing") is None
    payload = {"cut_value": 3.2, "closures": {"type": "FeatureCollection", "features": []}}
    plan_cache.save_cached_plan("abc", payload)
    assert plan_cache.load_cached_plan("abc") == payload
