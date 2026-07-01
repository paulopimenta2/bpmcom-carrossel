import streamlit as st
import requests
import json
import re
import os
import time
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# ── CONFIG ──────────────────────────────────────────────────────────────────
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
    for c in [chr(0x201c),chr(0x201d),chr(0x2018),chr(0x2019),chr(0x201e),chr(0x00ab),chr(0x00bb),chr(34),chr(39)]:
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
        for tag in soup.find_all(["img","meta"]):
            src = tag.get("src") or tag.get("content","")
            if src and src.startswith("http") and any(x in src for x in [".jpg",".jpeg",".png",".webp"]):
                if not any(x in src.lower() for x in ["logo","icon","avatar","banner","thumb_small"]):
                    if src not in fotos:
                        fotos.append(src)
        dominio = urlparse(url).netloc.replace("www.","")
        return {"titulo": titulo, "texto": texto, "fotos": fotos[:6], "dominio": dominio, "url": url}
    except Exception as e:
        return {"titulo": "", "texto": "", "fotos": [], "dominio": "", "url": url, "erro": str(e)}
def estruturar_carrossel(dados):
    prompt = f"""Voce e um editor de conteudo para o Instagram de uma assessoria de imprensa chamada Bpmat.
Analise a noticia abaixo e crie um carrossel de 3 a 5 slides para o Instagram.

REGRAS OBRIGATORIAS:
1. nome_artista: nome principal em MAIUSCULAS, extraido da noticia (NUNCA use placeholder)
2. veiculo: mapeie o dominio {dados["dominio"]} para nome legivel (ex: g1.globo.com->G1, oglobo.com->O Globo)
3. tipo_slide: exatamente "capa" | "interno" | "encerramento"
4. titulo_slide: max 10 palavras, SEM aspas de qualquer tipo, em MAIUSCULAS
5. texto_slide: 2-3 frases informativas curtas, diferentes por slide
6. foto_url: use fotos diferentes por slide quando houver varias disponiveis
7. Ultimo slide: tipo="encerramento", titulo="CONFIRA A MATERIA COMPLETA EM [VEICULO]"
8. Distribua a narrativa: contexto -> desenvolvimento -> CTA

FOTOS DISPONIVEIS: {json.dumps(dados["fotos"])}
DOMINIO: {dados["dominio"]}
TITULO: {dados["titulo"]}
TEXTO: {dados["texto"][:3000]}

Retorne APENAS JSON valido (sem markdown):
{{
  "nome_artista": "NOME EM MAIUSCULAS",
  "veiculo": "Nome do Veiculo",
  "slides": [
    {{
      "tipo_slide": "capa",
      "titulo_slide": "TITULO SEM ASPAS",
      "texto_slide": "Texto informativo do slide.",
      "foto_url": "https://..."
    }}
  ]
}}"""
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
def gerar_slide(slide, nome_artista, veiculo, idx):
    tipo = slide.get("tipo_slide", "interno")
    tmpl = TEMPLATES.get(tipo, TEMPLATES["interno"])
    tid = tmpl["id"]
    layers_cfg = tmpl["layers"]
    nome_veiculo = f"{nome_artista} + {veiculo}"
    titulo = remover_aspas(slide.get("titulo_slide", ""))
    texto = slide.get("texto_slide", "")
    foto = slide.get("foto_url", "")
    layers = []
    if tipo == "capa":
        if foto: layers.append({"id": layers_cfg["foto"], "type": "image", "value": foto})
        layers.append({"id": layers_cfg["nome_artista"], "type": "text", "value": nome_artista})
        layers.append({"id": layers_cfg["titulo"],       "type": "text", "value": titulo})
        layers.append({"id": layers_cfg["veiculo"],      "type": "text", "value": veiculo})
        layers.append({"id": layers_cfg["logo_bpmat"],   "type": "text", "value": "#ImprensaBpmat"})
    else:
        if foto: layers.append({"id": layers_cfg["foto"], "type": "image", "value": foto})
        layers.append({"id": layers_cfg["titulo"],       "type": "text", "value": titulo})
        layers.append({"id": layers_cfg["texto_slide"],  "type": "text", "value": texto})
        layers.append({"id": layers_cfg["nome_veiculo"], "type": "text", "value": nome_veiculo})
        layers.append({"id": layers_cfg["logo_bpmat"],   "type": "text", "value": "#ImprensaBpmat"})
    payload = {"name": f"slide_{idx:02d}", "layers": layers, "format": "png"}
    r = requests.post(
        f"https://api.layerre.com/v1/template/{tid}/variant",
        headers={"Authorization": f"Bearer {LAYERRE_API_KEY}", "Content-Type": "application/json"},
        json=payload, timeout=60
    )
    r.raise_for_status()
    data = r.json()
    img_url = data.get("url") or data.get("image_url") or data.get("output_url") or ""
    if not img_url and "outputs" in data:
        img_url = data["outputs"][0].get("url","")
    return img_url
# ── STREAMLIT UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gerador de Carrossel - Bpmat", page_icon="v", layout="centered")

st.markdown("""
<div style="background:#5B2D8E;padding:24px 20px 18px;border-radius:12px;text-align:center;margin-bottom:24px">
  <h1 style="color:white;margin:0;font-size:1.8rem;font-weight:700">Gerador de Carrossel</h1>
  <p style="color:#e0c9ff;margin:6px 0 0;font-size:1rem">Assessoria Bpmat - Automacao de posts para Instagram</p>
</div>
""", unsafe_allow_html=True)

if not LAYERRE_API_KEY or not GEMINI_API_KEY:
    st.error("Chaves de API nao configuradas. Configure LAYERRE_API_KEY e GEMINI_API_KEY nos Secrets.")
    st.stop()

link = st.text_input("Cole o link da noticia aqui:", placeholder="https://oglobo.globo.com/...")
gerar = st.button("GERAR CARROSSEL", type="primary", use_container_width=True)

if gerar and link:
    with st.spinner("Extraindo noticia..."):
        dados = extrair_noticia(link)
    if not dados.get("titulo") and not dados.get("texto"):
        st.error("Nao foi possivel extrair o conteudo da noticia. Verifique o link.")
        st.stop()
    with st.expander("Noticia extraida", expanded=False):
        st.write(f"Titulo: {dados["titulo"]}")
        st.write(f"Dominio: {dados["dominio"]}")
        st.write(f"Fotos encontradas: {len(dados["fotos"])}")
    with st.spinner("Estruturando carrossel com Gemini AI..."):
        try:
            estrutura = estruturar_carrossel(dados)
        except Exception as e:
            st.error(f"Erro ao processar com Gemini: {e}")
            st.stop()
    nome_artista = estrutura.get("nome_artista", "ARTISTA")
    veiculo = estrutura.get("veiculo", dados["dominio"])
    slides = estrutura.get("slides", [])
    st.success(f"Carrossel estruturado: {len(slides)} slides para {nome_artista} - {veiculo}")
    progress = st.progress(0, text="Gerando imagens...")
    imgs = []
    for i, slide in enumerate(slides):
        progress.progress(i / len(slides), text=f"Gerando slide {i+1}/{len(slides)}...")
        try:
            url = gerar_slide(slide, nome_artista, veiculo, i+1)
            imgs.append((i+1, slide.get("tipo_slide",""), url))
        except Exception as e:
            st.warning(f"Erro no slide {i+1}: {e}")
        time.sleep(0.5)
    progress.progress(1.0, text="Concluido!")
    st.markdown("---")
    st.subheader("Slides gerados")
    cols = st.columns(min(len(imgs), 3))
    for i, (num, tipo, url) in enumerate(imgs):
        col = cols[i % len(cols)]
        with col:
            if url:
                st.image(url, caption=f"Slide {num} - {tipo}", use_container_width=True)
                st.markdown(f"[Baixar slide {num}]({url})")
            else:
                st.error(f"Slide {num}: erro ao gerar")
    if imgs:
        st.markdown("---")
        st.info("Clique em cada link acima para baixar as imagens e postar no Instagram!")
elif gerar and not link:
    st.warning("Cole o link da noticia antes de gerar o carrossel.")
