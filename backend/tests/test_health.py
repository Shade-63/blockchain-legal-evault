def test_health_liveness(client):
    """
    Test that the base health endpoint is alive.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_health_dependencies_all_healthy(
    client,
    mock_db_connection,
    mock_storage_connection,
    mock_blockchain_connection
):
    """
    Test /health/dependencies when all components are healthy.
    """
    mock_db_connection.return_value = (True, None)
    mock_storage_connection.return_value = (True, None)
    mock_blockchain_connection.return_value = (True, None)

    response = client.get("/health/dependencies")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
    assert data["dependencies"]["database"]["healthy"] is True
    assert data["dependencies"]["database"]["error"] is None
    assert data["dependencies"]["storage"]["healthy"] is True
    assert data["dependencies"]["storage"]["error"] is None
    assert data["dependencies"]["blockchain"]["healthy"] is True
    assert data["dependencies"]["blockchain"]["error"] is None

def test_health_dependencies_partial_failure(
    client,
    mock_db_connection,
    mock_storage_connection,
    mock_blockchain_connection
):
    """
    Test /health/dependencies when database fails but others succeed.
    """
    mock_db_connection.return_value = (False, "Connection refused")
    mock_storage_connection.return_value = (True, None)
    mock_blockchain_connection.return_value = (True, None)

    response = client.get("/health/dependencies")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["dependencies"]["database"]["healthy"] is False
    assert data["dependencies"]["database"]["error"] == "Connection refused"
    assert data["dependencies"]["storage"]["healthy"] is True
    assert data["dependencies"]["blockchain"]["healthy"] is True

def test_health_dependencies_all_failed(
    client,
    mock_db_connection,
    mock_storage_connection,
    mock_blockchain_connection
):
    """
    Test /health/dependencies when all components fail.
    """
    mock_db_connection.return_value = (False, "DB Error")
    mock_storage_connection.return_value = (False, "Storage Error")
    mock_blockchain_connection.return_value = (False, "Blockchain Error")

    response = client.get("/health/dependencies")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["dependencies"]["database"]["healthy"] is False
    assert data["dependencies"]["database"]["error"] == "DB Error"
    assert data["dependencies"]["storage"]["healthy"] is False
    assert data["dependencies"]["storage"]["error"] == "Storage Error"
    assert data["dependencies"]["blockchain"]["healthy"] is False
    assert data["dependencies"]["blockchain"]["error"] == "Blockchain Error"
    
def test_health_liveness_api_prefix(client):
    """
    Test that the base health endpoint is also accessible under /api/v1/health.
    """
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
