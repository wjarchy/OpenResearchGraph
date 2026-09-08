from __future__ import annotations

from fastapi.testclient import TestClient

from openresearchgraph.api import create_app


def test_health_and_web_app(settings) -> None:
    with TestClient(create_app(settings)) as client:
        health = client.get("/api/health")
        page = client.get("/")

    assert health.status_code == 200
    assert health.json()["provider"] == "deterministic-demo"
    assert page.status_code == 200
    assert "OpenResearchGraph" in page.text


def test_create_and_fetch_research(settings) -> None:
    with TestClient(create_app(settings)) as client:
        accepted = client.post(
            "/api/research",
            json={"query": "比较储能技术路线与产业化风险", "session_id": "api-test"},
        )
        assert accepted.status_code == 202
        run_id = accepted.json()["run_id"]
        with client.stream("GET", f"/api/research/{run_id}/events") as response:
            body = "".join(response.iter_text())
        final = client.get(f"/api/research/{run_id}")

    assert "event: run.completed" in body
    assert final.status_code == 200
    assert final.json()["report"].startswith("# 研究报告")


def test_arbitrary_dimension_api(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/data/query",
            json={
                "dimensions": ["sector", "region", "year", "month"],
                "period_mode": "cumulative",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["dimensions"] == ["sector", "region", "year", "month"]
    assert body["sql"].endswith("LIMIT 4")
    assert "effort" in body["columns"]
