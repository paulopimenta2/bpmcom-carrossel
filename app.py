import streamlit as st
import requests
import json
import re
import os
import time
from bs4 import BeautifulSoup
from urllib.parse import urlparse

LAYERRE_API_KEY = st.secrets.get("LAYERRE_API_KEY", os.getenv("LAYERRE_API_KEY", ""))
GEMINI_API_KEY  = st.secrets.get("GEMINI_API_KEY",  os.getenv("GEMINI_API_KEY",  ""))

TEMPLATES = {
    "capa": {
        "id": "a5825102-c015-4bba-ba8e-65dfb0362a9f",
        "layers": {
            "foto":         "1a79e050-da3b-452e-9623-b1810a42f9df",
            "logo_bpmat":   "ab11af47-1e5b-4cea-ac33-43c3e3cb0986",
            "nome_artista": "99a1e2a3-3f7e-4a29-b369-4a5b2ce6cddd",
            "titulo":       "cf5126c1-275b-4917-9e9a-af9e4d53036b",
            "veiculo":      "7f29b244-0450-48f8-930b-40304b314b36",
        }
    },
    "interno": {
        "id": "119879ec-4210-4d55-8b07-bec699bf5c81",
        "layers": {
            "foto":         "5c2a02e5-22cc-4a3c-8819-1ff8abcfe697",
            "logo_bpmat":   "ec677564-6820-437f-9d22-2654a3bf3965",
            "nome_veiculo": "bd7bee2a-8040-4c05-9403-1b1aef659c7e",
            "texto_slide":  "b01987f5-83f6-4c0c-bd38-62470b54b4f0",
            "titulo":       "09afea60-0752-42e1-81b4-a3ca97a17407",
        }
    },
    "encerramento": {
        "id": "5cd1a3e8-908f-4507-a82d-ada34b1efbf1",
        "layers": {
            "foto":         "bb195e4b-0210-47e9-a926-28e05d66c711",
            "logo_bpmat":   "bed6048a-87a6-4b6b-97ae-e36d73ddaf42",
            "nome_veiculo": "ad82794f-92b8-4523-a102-8271cccb6414",
            "texto_slide":  "f7604515-b765-4913-bb1c-56788d13c237",
            "titulo":       "5bfd2c65-b107-4272-b641-531abea6de95",
        }
    }
}

def remover_aspas(texto):
    for c in [chr(0x201c), chr(0x201d), chr(0x2018), chr(0x2019), chr(0x201e), chr(0x00ab), chr(0x00bb), chr(34), chr(39)]:
        texto = texto.replace(c, "")
    return texto.strip()

def extrair_noticia(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        titulo = soup.find("h1")
        titulo = titulo.get_text(strip=True) if titulo else ""
        paragrafos = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 50]
        texto = " ".join(paragrafos[:30])
        fotos = []
        for prop in ["og:image", "og:image:secure_url"]:
            tag = soup.find("meta", property=prop)
            if tag and tag.get("content", "").startswith("http") and tag["content"] not in fotos:
                fotos.append(tag["content"])
        for name in ["twitter:image", "twitter:image:src"]:
            tag = soup.find("meta", attrs={"name": name})
            if tag and tag.get("content", "").startswith("http") and tag["content"] not in fotos:
                fotos.append(tag["content"])
        SKIP = ["logo", "icon", "avatar", "1x1", "pixel", "tracking", "ad", "banner",
                "related", "mais-lidas", "sidebar", "newsletter", "social", "share",
                "favicon", "sprite", "placeholder"]
        for img in soup.find_all("img"):
            src = (img.get("src", "") or img.get("data-src", "") or
                   img.get("data-lazy-src", "") or img.get("data-original", ""))
            if src and src.startswith("http") and any(x in src for x in [".jpg", ".jpeg", ".png", ".webp"]):
                if not any(x in src.lower() for x in SKIP):
                    w = img.get("width", "0")
                    try:
                        if int(str(w).replace("px", "")) > 300 and src not in fotos:
                            fotos.append(src)
                    except:
                        if src not in fotos:
                            fotos.append(src)
        dominio = urlparse(url).netloc.replace("www.", "")
        return {"titulo": titulo, "texto": texto, "fotos": fotos[:5], "dominio": dominio, "url": url}
    except Exception as e:
        return {"titulo": "", "texto": "", "fotos": [], "dominio": "", "url": url, "erro": str(e)}

def estruturar_carrossel(dados):
    fotos_str = json.dumps(dados["fotos"])
    prompt = """Voce e um editor de conteudo para o Instagram de uma assessoria de imprensa chamada Bpmat.
Crie um carrossel de 3 a 5 slides com base na noticia abaixo.
REGRAS:
1. nome_artista: nome principal em MAIUSCULAS, extraido da noticia
2. veiculo: nome legivel para {dominio} (g1.globo.com->G1, oglobo.com->O Globo, uol.com.br->UOL, folha.uol.com.br->Folha, estadao.com.br->Estadao, terra.com.br->Terra, r7.com->R7, metropoles.com->Metropoles)
3. tipo_slide: "capa" | "interno" | "encerramento"
4. titulo_slide: max 10 palavras, SEM aspas, MAIUSCULAS
5. texto_slide: 2-3 frases informativas, diferentes por slide
6. foto_url: use SOMENTE URLs desta lista: {fotos}
7. Ultimo slide: tipo=encerramento, titulo=CONFIRA A MATERIA COMPLETA EM [VEICULO]
DOMINIO: {dominio}
TITULO: {titulo}
TEXTO: {texto}
JSON sem markdown:
{{
  "nome_artista": "NOME",
  "veiculo": "Veiculo",
  "slides": [
    {{"tipo_slide":"capa","titulo_slide":"TITULO","texto_slide":"texto.","foto_url":"url"}}
  ]
}}""".format(
        dominio=dados["dominio"],
        fotos=fotos_str,
        titulo=dados["titulo"],
        texto=dados["texto"][:3000]
    )
    r = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60
    )
    r.raise_for_status()
    raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    raw = re.sub(r"```json|```", "", raw).strip()
    return json.loads(raw)

def gerar_slide(slide, nome_artista, veiculo, idx, debug=False):
    tipo = slide.get("tipo_slide", "interno")
    tmpl = TEMPLATES.get(tipo, TEMPLATES["interno"])
    tid  = tmpl["id"]
    lc   = tmpl["layers"]

    nome_veiculo = "{} + {}".format(nome_artista, veiculo)
    titulo = remover_aspas(slide.get("titulo_slide", ""))
    texto  = slide.get("texto_slide", "")
    foto   = slide.get("foto_url", "")

    # Layerre API correta: "overrides" com "layer_id" e "properties"
    # Imagens: properties.img_url  |  Textos: properties.text
    overrides = []

    if foto:
        overrides.append({
            "layer_id": lc["foto"],
            "properties": {"img_url": foto}
        })

    if tipo == "capa":
        overrides.append({"layer_id": lc["nome_artista"], "properties": {"text": nome_artista}})
        overrides.append({"layer_id": lc["titulo"],       "properties": {"text": titulo}})
        overrides.append({"layer_id": lc["veiculo"],      "properties": {"text": veiculo}})
        overrides.append({"layer_id": lc["logo_bpmat"],   "properties": {"text": "#ImprensaBpmat"}})
    else:
        overrides.append({"layer_id": lc["titulo"],       "properties": {"text": titulo}})
        overrides.append({"layer_id": lc["texto_slide"],  "properties": {"text": texto}})
        overrides.append({"layer_id": lc["nome_veiculo"], "properties": {"text": nome_veiculo}})
        overrides.append({"layer_id": lc["logo_bpmat"],   "properties": {"text": "#ImprensaBpmat"}})

    payload = {
        "export_type": "png",
        "overrides": overrides
    }

    if debug:
        st.write("**Payload slide {}:**".format(idx))
        st.json(payload)

    r = requests.post(
        "https://api.layerre.com/v1/template/{}/variant".format(tid),
        headers={"Authorization": "Bearer {}".format(LAYERRE_API_KEY), "Content-Type": "application/json"},
        json=payload,
        timeout=60
    )
    if debug:
        try:
            st.write("**Layerre resposta slide {} (status {}):**".format(idx, r.status_code))
            st.json(r.json())
        except:
            st.write(r.text[:500])
    r.raise_for_status()
    data = r.json()
    img_url = data.get("url") or data.get("image_url") or data.get("output_url") or ""
    if not img_url and "outputs" in data:
        img_url = data["outputs"][0].get("url", "")
    return img_url

# -- UI --

st.set_page_config(page_title="Gerador de Carrossel - Bpmat", page_icon="v", layout="centered")

st.markdown("""
<div style="background:#5B2D8E;padding:24px 20px 18px;border-radius:12px;text-align:center;margin-bottom:8px">
  <h1 style="color:white;margin:0;font-size:1.8rem;font-weight:700">Gerador de Carrossel</h1>
  <p style="color:#e0c9ff;margin:6px 0 0;font-size:1rem">Assessoria Bpmat - Automacao de posts para Instagram</p>
</div>
""", unsafe_allow_html=True)

if not LAYERRE_API_KEY or not GEMINI_API_KEY:
    st.error("Chaves de API nao configuradas.")
    st.stop()

debug_mode = st.sidebar.checkbox("Modo debug (ver payloads)", value=False)

with st.sidebar.expander("Inspecionar template"):
    tid_insp = st.selectbox("Template", ["capa", "interno", "encerramento"])
    if st.button("Inspecionar"):
        tid = TEMPLATES[tid_insp]["id"]
        resp = requests.get(
            "https://api.layerre.com/v1/template/{}".format(tid),
            headers={"Authorization": "Bearer {}".format(LAYERRE_API_KEY)}
        )
        st.json(resp.json())

url_input = st.text_input("Cole o link da noticia:", placeholder="https://...")
gerar = st.button("Gerar Carrossel", type="primary", use_container_width=True)

if gerar and url_input:
    with st.spinner("Extraindo noticia..."):
        dados = extrair_noticia(url_input)

    if dados.get("erro"):
        st.error("Erro ao acessar URL: {}".format(dados["erro"]))
        st.stop()

    if not dados.get("titulo") and not dados.get("texto"):
        st.warning("Nao foi possivel extrair conteudo. Verifique se o link e publico.")
        st.stop()

    with st.spinner("Estruturando carrossel com Gemini..."):
        try:
            estrutura = estruturar_carrossel(dados)
        except Exception as e:
            st.error("Erro Gemini: {}".format(e))
            st.stop()

    slides       = estrutura.get("slides", [])
    nome_artista = estrutura.get("nome_artista", "ARTISTA")
    veiculo      = estrutura.get("veiculo", dados["dominio"])

    st.success("Carrossel estruturado: {} slides para {} - {}".format(len(slides), nome_artista, veiculo))
    progress = st.progress(0, text="Gerando imagens...")
    imgs = []
    for i, slide in enumerate(slides):
        progress.progress(i / len(slides), text="Gerando slide {}/{}...".format(i+1, len(slides)))
        try:
            url = gerar_slide(slide, nome_artista, veiculo, i+1, debug=debug_mode)
            imgs.append((i+1, slide.get("tipo_slide", ""), url))
        except Exception as e:
            st.warning("Erro slide {}: {}".format(i+1, e))
        time.sleep(0.5)
    progress.progress(1.0, text="Concluido!")

    st.markdown("---")
    st.subheader("Slides gerados")
    cols = st.columns(min(len(imgs), 3))
    for i, (num, tipo, url) in enumerate(imgs):
        col = cols[i % len(cols)]
        with col:
            if url:
                st.image(url, caption="Slide {} - {}".format(num, tipo), use_container_width=True)
                st.markdown("[Baixar slide {}]({})".format(num, url))
            else:
                st.error("Slide {}: erro".format(num))
    if imgs:
        st.markdown("---")
        st.info("Clique nos links acima para baixar cada post individualmente.")
