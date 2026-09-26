from datetime import UTC, datetime, timedelta

import jwt

from app.auth.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hashing():
    h = hash_password("s3cret")
    assert h != "s3cret"
    assert verify_password("s3cret", h)
    assert not verify_password("wrong", h)


def test_login_success_returns_bearer_token(client):
    r = client.post("/api/v1/auth/login", json={"username": "alice", "password": "alice-pass"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert decode_access_token(body["access_token"])["sub"] == "alice"


def test_login_wrong_password(client):
    r = client.post("/api/v1/auth/login", json={"username": "alice", "password": "nope"})
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = client.post("/api/v1/auth/login", json={"username": "mallory", "password": "x"})
    assert r.status_code == 401


def test_valid_token_passes(client, user_headers):
    r = client.get("/api/v1/auth/me", headers=user_headers)
    assert r.status_code == 200
    assert r.json() == {"username": "alice", "role": "user"}


def test_missing_token_fails(client):
    assert client.post("/api/v1/chat", json={"question": "hi"}).status_code == 401


def test_invalid_token_fails(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_expired_token_fails(client):
    token = create_access_token("alice", "user", expires_minutes=-1)
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_signed_with_other_key_fails(client):
    now = datetime.now(UTC)
    forged = jwt.encode(
        {
            "sub": "admin",
            "role": "admin",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": "production-agentic-ai",
        },
        "attacker-key-attacker-key-attacker-key",
        algorithm="HS256",
    )
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_alg_none_token_rejected(client):
    unsigned = jwt.encode({"sub": "admin", "iss": "production-agentic-ai"}, key="", algorithm="none")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {unsigned}"}).status_code == 401


def test_non_admin_cannot_upload(client, user_headers):
    r = client.post(
        "/api/v1/documents", headers=user_headers, files={"file": ("x.txt", b"some policy text", "text/plain")}
    )
    assert r.status_code == 403
