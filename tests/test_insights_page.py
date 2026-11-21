import app as app_module


def test_insights_page_and_api_routes_are_registered(monkeypatch):
    monkeypatch.setattr(app_module, "init_db_indexes", lambda app: None)
    app = app_module.create_app()

    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/insights/<project_id>" in rules
    assert "/api/insights/<project_id>/chat" in rules

    client = app.test_client()
    response = client.get("/insights/example-project")

    assert response.status_code == 200
    assert b"Insights del proyecto" in response.data
    api_response = client.post("/api/insights/example-project/chat", json={"question": "test"})
    assert api_response.status_code == 401
