"""Tests for the rolling network-history store in merge.py."""
import json
import merge


def test_update_history_appends_one_snapshot(tmp_path):
    path = str(tmp_path / "history.json")
    stats = {
        "unique_alive": 100, "top_speed": 500.0, "avg_speed": 40.0,
        "median_speed": 35.0, "speed_percentile_90": 90.0,
        "vless_count": 50, "vmess_count": 10, "trojan_count": 8,
        "ss_count": 5, "hy2_count": 2, "bs_count": 30, "chs_count": 70,
        "country_stats": [{"code": "DE", "count": 9}],
    }
    merge.update_history(stats, path=path)
    data = json.load(open(path, encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["total"] == 100
    assert data[0]["max_speed"] == 500
    assert data[0]["countries"] == 1
    assert "t" in data[0]


def test_update_history_rotates_to_90(tmp_path):
    path = str(tmp_path / "history.json")
    seed = [{"t": str(i), "total": i} for i in range(95)]
    json.dump(seed, open(path, "w", encoding="utf-8"))
    merge.update_history({"unique_alive": 999}, path=path)
    data = json.load(open(path, encoding="utf-8"))
    assert len(data) == 90
    assert data[-1]["total"] == 999          # newest kept
    assert data[0]["total"] == 6             # oldest 6 dropped (95+1-90)


def test_load_history_recovers_from_garbage(tmp_path):
    path = str(tmp_path / "history.json")
    open(path, "w", encoding="utf-8").write("{ not json")
    assert merge.load_history(path) == []


def test_load_history_missing_file(tmp_path):
    assert merge.load_history(str(tmp_path / "nope.json")) == []


def test_compute_trends_insufficient_history():
    t = merge.compute_trends([{"total": 100, "max_speed": 500}])
    assert t["nodes_pct"] is None
    assert t["speed_pct"] is None
    assert t["series_total"] == [100]


def test_compute_trends_percent_delta():
    hist = [
        {"total": 100, "max_speed": 400},
        {"total": 110, "max_speed": 500},
    ]
    t = merge.compute_trends(hist)
    assert round(t["nodes_pct"], 1) == 10.0
    assert round(t["speed_pct"], 1) == 25.0
    assert t["series_total"] == [100, 110]
    assert t["series_speed"] == [400, 500]


def test_compute_trends_zero_previous_is_safe():
    hist = [{"total": 0, "max_speed": 0}, {"total": 5, "max_speed": 9}]
    t = merge.compute_trends(hist)
    assert t["nodes_pct"] is None       # no divide-by-zero
    assert t["speed_pct"] is None


def test_compute_trends_series_capped_to_30():
    hist = [{"total": i, "max_speed": i} for i in range(50)]
    t = merge.compute_trends(hist)
    assert len(t["series_total"]) == 30
    assert t["series_total"][0] == 20   # last 30 of 0..49
