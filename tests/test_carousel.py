# tests/test_carousel.py
import pytest
from app.carousel import construir_prompt, parse_json_resposta, gerar_html_slide

def test_prompt_inclui_nicho_restricoes_e_cores():
    prompt = construir_prompt(
        tema="Marketing Digital",
        plataforma="Instagram",
        nicho="coaches de vida",
        restricoes="não mencionar concorrentes",
        cores_marca="#FF4D00 laranja vibrante"
    )
    assert "coaches de vida" in prompt
    assert "não mencionar concorrentes" in prompt
    assert "Marketing Digital" in prompt
    assert "#FF4D00 laranja vibrante" in prompt

def test_parse_json_resposta_extrai_slides():
    resposta = '''```json
{
  "titulo_serie": "Teste",
  "paleta": {"nome":"dark","bg":"#000","accent":"#fff","accent2":"#aaa","text":"#fff","overlay":"rgba(0,0,0,0.5)"},
  "hashtags": ["#test"],
  "melhor_horario": "19:00",
  "slides": [{"numero":1,"emoji":"🔥","titulo":"Titulo","texto":"Texto","query_imagem":"query"}]
}
```'''
    dados = parse_json_resposta(resposta)
    assert len(dados["slides"]) == 1
    assert dados["slides"][0]["titulo"] == "Titulo"

def test_parse_json_sem_backticks():
    import json
    dados_raw = {
        "titulo_serie": "T",
        "paleta": {"nome":"x","bg":"#000","accent":"#fff","accent2":"#aaa","text":"#fff","overlay":"x"},
        "hashtags": [],
        "melhor_horario": "18:00",
        "slides": []
    }
    dados = parse_json_resposta(json.dumps(dados_raw))
    assert dados["titulo_serie"] == "T"

PALETA_TESTE = {"bg":"#000","accent":"#FF0","accent2":"#F00","text":"#fff","overlay":"rgba(0,0,0,0.5)"}
SLIDE_TESTE = {"numero": 2, "emoji": "✨", "titulo": "Título", "texto": "Corpo do slide", "query_imagem": "q"}

def test_gerar_html_slide_sem_logo_sem_username():
    html = gerar_html_slide(SLIDE_TESTE, 7, "Tema", PALETA_TESTE)
    assert "Título" in html
    assert "Corpo do slide" in html
    assert "<img" not in html       # sem logo
    assert 'class="marca"' in html  # div marca existe mesmo vazia

def test_gerar_html_slide_com_logo_e_username():
    html = gerar_html_slide(
        SLIDE_TESTE, 7, "Tema", PALETA_TESTE,
        logo_url="file:///path/logo.png",
        username="@testhandle"
    )
    assert 'src="file:///path/logo.png"' in html
    assert "@testhandle" in html
