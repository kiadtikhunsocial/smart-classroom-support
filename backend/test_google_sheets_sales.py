"""No-network tests for customer/sales Sheet mirroring."""

import httpx

from app import google_sheets as sheets


def test_new_lead_tab_is_created_and_customer_text_is_raw(monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet-test")
    monkeypatch.setattr(sheets, "_access_token", lambda: "test-token")
    calls = []

    def fake_get(url, **kwargs):
        return httpx.Response(400, text="Unable to parse range: Leads!A:J",
                              request=httpx.Request("GET", url))

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(sheets.httpx, "get", fake_get)
    monkeypatch.setattr(sheets.httpx, "post", fake_post)
    assert sheets.sync_lead_row({"id": 42, "name": "=IMPORTXML(test)", "source": "WEB"})
    assert any(":batchUpdate" in url and call["json"]["requests"][0]["addSheet"]
               ["properties"]["title"] == "Leads" for url, call in calls)
    appends = [call for url, call in calls if url.endswith(":append")]
    assert len(appends) == 2  # header, then lead
    assert appends[-1]["params"]["valueInputOption"] == "RAW"
    assert appends[-1]["json"]["values"][0][3] == "=IMPORTXML(test)"


def test_existing_sales_record_is_updated_not_appended(monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet-test")
    monkeypatch.setattr(sheets, "_access_token", lambda: "test-token")
    calls = []

    def fake_get(url, **kwargs):
        return httpx.Response(200, json={"values": [list(sheets.SALES_HEADER), ["", "7"]]},
                              request=httpx.Request("GET", url))

    def fake_put(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={}, request=httpx.Request("PUT", url))

    monkeypatch.setattr(sheets.httpx, "get", fake_get)
    monkeypatch.setattr(sheets.httpx, "put", fake_put)
    assert sheets.sync_sales_record_row({"id": 7, "lead_id": 42, "kind": "deal",
                                         "status": "won", "product": "Display"})
    assert len(calls) == 1
    assert "Sales%21A2%3AJ2" in calls[0][0]
    assert calls[0][1]["json"]["values"][0][8] == "won"
    assert calls[0][1]["params"]["valueInputOption"] == "RAW"
