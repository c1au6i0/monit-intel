import os
import requests
from requests.auth import HTTPBasicAuth

BASE_URL = os.environ.get("MONIT_INTEL_URL", "http://localhost:8000")
AUTH_USER = os.environ.get("MONIT_INTEL_USER", "admin")
AUTH_PASS = os.environ.get("MONIT_INTEL_PASS", "RobaDaMatti")


def test_health_requires_auth():
    r = requests.get(f"{BASE_URL}/health", timeout=5)
    assert r.status_code == 401


def test_health_with_auth():
    r = requests.get(f"{BASE_URL}/health", auth=HTTPBasicAuth(AUTH_USER, AUTH_PASS), timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert "status" in data and "database" in data and "snapshots" in data


def test_status_requires_auth():
    r = requests.get(f"{BASE_URL}/status", timeout=5)
    assert r.status_code == 401


def test_status_with_auth():
    r = requests.get(f"{BASE_URL}/status", auth=HTTPBasicAuth(AUTH_USER, AUTH_PASS), timeout=5)
    assert r.status_code == 200


def test_analyze_requires_auth():
    r = requests.post(f"{BASE_URL}/analyze", json={}, timeout=5)
    assert r.status_code == 401


def test_analyze_with_auth():
    r = requests.post(
        f"{BASE_URL}/analyze",
        json={},
        auth=HTTPBasicAuth(AUTH_USER, AUTH_PASS),
        timeout=10,
    )
    assert r.status_code == 200


def test_history_requires_auth():
    r = requests.get(f"{BASE_URL}/history?service=docker&days=7", timeout=5)
    assert r.status_code == 401


def test_history_with_auth():
    r = requests.get(
        f"{BASE_URL}/history?service=docker&days=7",
        auth=HTTPBasicAuth(AUTH_USER, AUTH_PASS),
        timeout=5,
    )
    assert r.status_code in (200, 404)


def test_logs_requires_auth():
    r = requests.get(f"{BASE_URL}/logs/docker", timeout=5)
    assert r.status_code == 401


def test_logs_with_auth():
    r = requests.get(
        f"{BASE_URL}/logs/docker",
        auth=HTTPBasicAuth(AUTH_USER, AUTH_PASS),
        timeout=5,
    )
    # Depending on environment, may be 200 (logs), 404 (no mapping), or 500 (error)
    assert r.status_code in (200, 404, 500)


def test_mother_chat_requires_auth():
    r = requests.post(
        f"{BASE_URL}/mother/chat",
        json={"query": "hello"},
        timeout=5,
    )
    assert r.status_code == 401


def test_mother_chat_with_auth():
    r = requests.post(
        f"{BASE_URL}/mother/chat",
        json={"query": "hello"},
        auth=HTTPBasicAuth(AUTH_USER, AUTH_PASS),
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    assert "response" in data and isinstance(data["response"], str)
