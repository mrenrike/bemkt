from app.chat import PERGUNTAS, proxima_pergunta, chat_completo, resumo_job

def test_primeira_pergunta_e_nicho():
    assert "nicho" in PERGUNTAS[0]["campo"]

def test_proxima_pergunta_apos_resposta():
    estado = {}
    p, done = proxima_pergunta(estado)
    assert not done
    assert p["campo"] == "nicho"

def test_chat_completo_apos_6_respostas():
    estado = {}
    campos = ["nicho", "tema", "logo_path", "cores_marca", "username_slide", "restricoes"]
    for campo in campos:
        estado[campo] = "resposta teste"
    _, done = proxima_pergunta(estado)
    assert done

def test_skip_opcional_nao_bloqueia():
    estado = {"nicho": "tech", "tema": "IA", "logo_path": "", "cores_marca": "azul"}
    # username e restricoes são opcionais — skip com string vazia
    estado["username_slide"] = ""
    estado["restricoes"] = ""
    _, done = proxima_pergunta(estado)
    assert done

def test_resumo_formata_dados():
    estado = {"nicho": "fitness", "tema": "treino", "logo_path": "", "cores_marca": "verde", "username_slide": "@gym", "restricoes": ""}
    r = resumo_job(estado)
    assert "fitness" in r
    assert "@gym" in r
