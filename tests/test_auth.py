from app.auth import hash_senha, verificar_senha, criar_token, verificar_token

def test_hash_e_verifica_senha():
    h = hash_senha("minhasenha123")
    assert verificar_senha("minhasenha123", h)
    assert not verificar_senha("errada", h)

def test_token_round_trip():
    token = criar_token({"sub": "42"})
    payload = verificar_token(token)
    assert payload["sub"] == "42"

def test_token_invalido_retorna_none():
    assert verificar_token("token.invalido.aqui") is None

def test_cadastro_cria_usuario_com_credito_trial(client):
    r = client.post("/auth/cadastro", json={
        "nome": "Ana", "email": "ana@test.com", "senha": "123456"
    })
    assert r.status_code == 200
    assert "token" in r.json()
    # verifica crédito trial
    token = r.json()["token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["creditos"] == 1

def test_login_retorna_token(client):
    client.post("/auth/cadastro", json={"nome": "Bob", "email": "bob@test.com", "senha": "abc123"})
    r = client.post("/auth/login", json={"email": "bob@test.com", "senha": "abc123"})
    assert r.status_code == 200
    assert "token" in r.json()

def test_login_senha_errada_retorna_401(client):
    client.post("/auth/cadastro", json={"nome": "Carol", "email": "carol@test.com", "senha": "certa"})
    r = client.post("/auth/login", json={"email": "carol@test.com", "senha": "errada"})
    assert r.status_code == 401

def test_me_sem_token_retorna_403(client):
    r = client.get("/me")
    assert r.status_code == 403
