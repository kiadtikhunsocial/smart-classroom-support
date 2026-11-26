"""Server-side search, multi-status filter, total count and per-status counts
for the staff ticket list (plan: docs/superpowers/plans/2026-11-13-tickets-fast-usable.md)."""


def test_total_count_header_ignores_limit(client, admin_headers, tag):
    r = client.get("/api/tickets", params={"q": tag, "limit": 1}, headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.headers["X-Total-Count"] == "4"


def test_search_matches_title_and_ticket_id(client, admin_headers, tag, ticket_ids):
    by_title = client.get("/api/tickets", params={"q": f"ลำโพงไม่ดัง {tag}"}, headers=admin_headers).json()
    assert [t["status"] for t in by_title] == ["waiting_parts"]
    # ticket numbers are matched case-insensitively
    by_id = client.get("/api/tickets", params={"q": ticket_ids[0].lower()}, headers=admin_headers).json()
    assert [t["ticket_id"] for t in by_id] == [ticket_ids[0]]


def test_search_treats_wildcards_literally(client, admin_headers, tag):
    titles = [t["title"] for t in client.get("/api/tickets", params={"q": "100%_x " + tag}, headers=admin_headers).json()]
    assert titles == [f"จอดับ 100%_x {tag}"]


def test_status_accepts_comma_separated_list(client, admin_headers, tag):
    r = client.get("/api/tickets", params={"q": tag, "status": "pending,waiting_parts"}, headers=admin_headers)
    assert sorted(t["status"] for t in r.json()) == ["pending", "waiting_parts"]
    assert r.headers["X-Total-Count"] == "2"


def test_school_scoped_user_sees_only_own_school(client, school_admin_headers, tag):
    r = client.get("/api/tickets", params={"q": tag}, headers=school_admin_headers)
    assert r.headers["X-Total-Count"] == "1"
    assert len(r.json()) == 1


def test_total_count_header_is_exposed_to_browsers(client, admin_headers):
    r = client.get("/api/tickets", params={"limit": 1}, headers={**admin_headers, "Origin": "http://localhost:5173"})
    assert "x-total-count" in r.headers["access-control-expose-headers"].lower()


def test_counts_groups_by_status_for_the_same_filters(client, admin_headers, tag):
    body = client.get("/api/tickets/counts", params={"q": tag}, headers=admin_headers).json()
    assert body["total"] == 4
    assert body["by_status"]["pending"] == 1 and body["by_status"]["waiting_parts"] == 1
    assert sum(body["by_status"].values()) == body["total"]


def test_counts_respects_school_scope(client, school_admin_headers, tag):
    assert client.get("/api/tickets/counts", params={"q": tag}, headers=school_admin_headers).json()["total"] == 1


def test_counts_requires_login(client):
    assert client.get("/api/tickets/counts").status_code == 401


def test_counts_route_is_not_swallowed_by_ticket_id_route(client, admin_headers):
    assert "by_status" in client.get("/api/tickets/counts", headers=admin_headers).json()
