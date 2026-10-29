"""Field Guide frequencies must be regional and comparable across species:
a stray seen once must not rank like a common bird (Shiny Cowbird showed as
"Very Likely" in Massachusetts when each species was scaled to its own peak)."""
from app.services import ebird_service as es


def test_bar_chart_keeps_raw_checklist_frequency():
    header = "Species\tCode\t" + "\t".join(f"{m}-{w}" for m in range(1, 13) for w in range(1, 5))
    common = "Blue Jay\tblujay\t" + "\t".join(["0.5"] * 48)
    stray = "Shiny Cowbird\tshicow\t" + "\t".join(["0.0"] * 36 + ["0.002"] * 4 + ["0.0"] * 8)
    out = es._parse_bar_chart_tsv("\n".join([header, common, stray]))
    assert out["blujay"][0] == 0.5
    assert max(out["shicow"]) == 0.002          # not scaled up to 1.0


class _Resp:
    status_code = 200
    def __init__(self, data): self._d = data
    def json(self): return self._d


def test_inat_regional_monthly_scales_by_commonest_species(monkeypatch):
    def fake_get(url, params=None, **kw):
        assert params["radius"] == 50 and params["taxon_id"] == 3
        rows = [{"taxon": {"name": "Cyanocitta cristata"}, "count": 200},
                {"taxon": {"name": "Sitta carolinensis"}, "count": 50}]
        if params["month"] == 10:
            rows.append({"taxon": {"name": "Molothrus bonariensis"}, "count": 1})
        return _Resp({"results": rows, "total_results": len(rows)})
    monkeypatch.setattr(es.httpx, "get", fake_get)
    monkeypatch.setattr(es.time, "sleep", lambda s: None)
    out = es.fetch_inat_regional_monthly(42.3, -71.3, 50)
    assert out["cyanocitta cristata"] == [1.0] * 12
    assert out["sitta carolinensis"][0] == 0.25
    assert out["molothrus bonariensis"][9] == 0.005
    assert out["molothrus bonariensis"][0] == 0.0


def test_regional_list_uses_nearby_seasonality(monkeypatch):
    monkeypatch.setattr(es, "get_region_code_from_latlon", lambda *a: "US-MA-017")
    monkeypatch.setattr(es, "fetch_full_species_list", lambda *a: ["blujay", "shicow", "yefcan"])
    monkeypatch.setattr(es, "fetch_taxonomy_for_codes", lambda codes, key: {
        "blujay": {"common_name": "Blue Jay", "scientific_name": "Cyanocitta cristata"},
        "shicow": {"common_name": "Shiny Cowbird", "scientific_name": "Molothrus bonariensis"},
        "yefcan": {"common_name": "Yellow-fronted Canary", "scientific_name": "Crithagra mozambica"},
    })
    monkeypatch.setattr(es, "fetch_bar_chart_data", lambda *a: {})
    monkeypatch.setattr(es, "_fetch_geo_recent", lambda *a: {})
    monkeypatch.setattr(es, "fetch_inat_regional_monthly", lambda *a: {
        "cyanocitta cristata": [1.0] * 12, "molothrus bonariensis": [0.0] * 9 + [0.005, 0.0, 0.0]})
    rows = {r["common_name"]: r for r in es.fetch_regional_species_with_monthly_frequency(42.3, -71.3, "key")}
    assert rows["Blue Jay"]["monthly_frequency"] == [1.0] * 12
    assert max(rows["Shiny Cowbird"]["monthly_frequency"]) == 0.005
    assert rows["Yellow-fronted Canary"]["monthly_frequency"] == [0.0] * 12
