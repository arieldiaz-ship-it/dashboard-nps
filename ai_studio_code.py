import streamlit as st
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import json
import os
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="CX Dashboard Auto - IA", layout="wide", initial_sidebar_state="expanded")

# Estilo personalizado para emular el dashboard oscuro
st.markdown("""
    <style>
    .main { background-color: #0f172a; color: #f1f5f9; }
    .stMetric { background-color: #1e293b; padding: 20px; border-radius: 15px; border: 1px solid #334155; }
    div[data-testid="stExpander"] { border: none !important; box-shadow: none !important; background-color: transparent !important; }
    .stAlert { border-radius: 15px; border: 1px solid #854d0e; background-color: rgba(66, 32, 6, 0.5); }
    </style>
""", unsafe_allow_html=True)

# --- LÓGICA DE PROCESAMIENTO ---
def calculate_nps(df, column):
    scores = pd.to_numeric(df[column], errors='coerce').dropna()
    if len(scores) == 0: return 0, 0, 0, 0, 0
    promoters = len(scores[scores >= 9])
    passives = len(scores[(scores >= 7) & (scores < 9)])
    detractors = len(scores[scores < 7])
    total = len(scores)
    score = ((promoters - detractors) / total) * 100
    return score, promoters, passives, detractors, total

def get_alerts(df, global_nps):
    # Umbral de impacto: >= 5% del volumen
    total_vol = len(df)
    threshold_vol = total_vol * 0.05
    
    # 1. Alertas por Sucursal con bajo NPS
    sucursales = df.groupby('Sucursal').apply(lambda x: calculate_nps(x, 'Nota NPS CCS')[0])
    sucursal_vol = df.groupby('Sucursal').size()
    
    alerts = []
    for suc, score in sucursales.items():
        vol = sucursal_vol[suc]
        if vol >= threshold_vol and score < (global_nps - 10):
            weight = (vol / total_vol) * 100
            alerts.append(f"⚠️ {suc}: NPS {score:.0f} | Impacto: {weight:.1f}% del volumen")
            
    # 2. Alertas por Brecha Marca vs CCS
    concesionarios = df.groupby('Concesionario')
    brechas = []
    for name, group in concesionarios:
        vol = len(group)
        if vol >= threshold_vol:
            nps_marca = calculate_nps(group, 'Nota NPS Marca')[0]
            nps_ccs = calculate_nps(group, 'Nota NPS CCS')[0]
            diff = abs(nps_marca - nps_ccs)
            if diff > 15:
                weight = (vol / total_vol) * 100
                brechas.append(f"🚩 {name}: Brecha de {diff:.0f} pts (Marca {nps_marca:.0f} vs CCS {nps_ccs:.0f}) | Peso: {weight:.1f}%")
    
    return alerts, brechas

# --- SERVICIOS IA ---
def run_ai_analysis(comments, api_key):
    if not comments: return None
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash') # O el modelo disponible
    
    prompt = f"""
    Actúa como Experto CX Automotriz. Analiza estos comentarios:
    {chr(10).join(comments[:200])}
    
    Devuelve un JSON con:
    - satisfaction_topics: list of {{topic, count, keywords}}
    - dissatisfaction_topics: list of {{topic, count, keywords}}
    - summary: 2 sentences max.
    """
    
    try:
        response = model.generate_content(prompt)
        # Limpiar respuesta para JSON
        text = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(text)
    except:
        return None

# --- UI PRINCIPAL ---
st.title("🚗 CX DASHBOARD AUTO - STREAMLIT EDITION")
st.caption("Data Insight System v3.1 | Powered by Gemini IA")

with st.sidebar:
    st.header("Configuración")
    api_key = st.text_input("Gemini API Key", type="password", value=os.getenv("API_KEY", ""))
    uploaded_file = st.file_uploader("Cargar Base NPS/CSI (Excel/CSV)", type=["xlsx", "csv"])
    
    if uploaded_file:
        df_raw = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
        marcas = ["TODAS"] + sorted(df_raw['Marca'].dropna().unique().tolist())
        selected_brand = st.selectbox("Filtrar por Marca", marcas)
        
        tab_active = st.radio("Módulo", ["Ventas", "Postventa"])

if uploaded_file:
    # Filtrado
    df = df_raw.copy()
    if selected_brand != "TODAS":
        df = df[df['Marca'] == selected_brand]
    
    # --- KPIs ---
    nps_marca_score, p, pas, d, total = calculate_nps(df, 'Nota NPS Marca')
    nps_ccs_score, cp, cpas, cd, ctotal = calculate_nps(df, 'Nota NPS CCS')
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric(f"NPS Marca - {tab_active}", f"{nps_marca_score:.0f}", delta=None)
        st.caption(f"Basado en {total} encuestas")
    with col2:
        st.metric(f"NPS CCS - {tab_active}", f"{nps_ccs_score:.0f}", delta=None)
        st.caption(f"Basado en {ctotal} encuestas")

    # --- EVOLUCIÓN ---
    st.subheader("📊 Evolución Temporal")
    # Intentar detectar fecha
    date_col = next((c for c in df.columns if 'fecha' in c.lower() or 'periodo' in c.lower()), None)
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df_trend = df.set_index(date_col).resample('M').apply(lambda x: calculate_nps(x, 'Nota NPS Marca')[0]).reset_index()
        df_trend.columns = ['Mes', 'NPS']
        fig = px.line(df_trend, x='Mes', y='NPS', title='Tendencia NPS Marca', markers=True, template="plotly_dark")
        fig.update_traces(line_color='#06b6d4', line_width=4)
        st.plotly_chart(fig, use_container_width=True)

    # --- ALERTAS CRÍTICAS (Ubicadas según solicitud) ---
    st.subheader(f"⚠️ Alertas Críticas de CX - {tab_active}")
    alertas_suc, alertas_brecha = get_alerts(df, nps_ccs_score)
    
    if alertas_suc or alertas_brecha:
        c1, c2 = st.columns(2)
        with c1:
            if alertas_suc:
                st.warning("**Desviación en Sucursales (Impacto >5%)**\n\n" + "\n\n".join(alertas_suc))
        with c2:
            if alertas_brecha:
                st.error("**Brechas Marca vs CCS (Impacto >5%)**\n\n" + "\n\n".join(alertas_brecha))
    else:
        st.success(f"No se detectan alertas de alto impacto (>5% vol) en {tab_active}")

    # --- ANÁLISIS CUALITATIVO IA ---
    st.subheader("🤖 Análisis Cualitativo (Voz del Cliente por IA)")
    if api_key:
        comments = df['Comentario'].dropna().tolist()
        if st.button("Generar Insights con IA"):
            with st.spinner("Analizando sentimientos y tópicos..."):
                analysis = run_ai_analysis(comments, api_key)
                if analysis:
                    st.info(f"**Resumen Ejecutivo:** {analysis['summary']}")
                    ca1, ca2 = st.columns(2)
                    with ca1:
                        st.write("**👍 Fortalezas**")
                        for t in analysis['satisfaction_topics']:
                            st.write(f"- {t['topic']} ({t['count']} menciones)")
                    with ca2:
                        st.write("**👎 Oportunidades**")
                        for t in analysis['dissatisfaction_topics']:
                            st.write(f"- {t['topic']} ({t['count']} menciones)")
    else:
        st.info("Introduce tu Gemini API Key en la barra lateral para activar el análisis de texto.")

    # --- TABLAS DE DETALLE ---
    st.subheader("📋 Detalle por Concesionario")
    concesionarios_nps = df.groupby('Concesionario').apply(lambda x: pd.Series({
        'NPS Marca': calculate_nps(x, 'Nota NPS Marca')[0],
        'NPS CCS': calculate_nps(x, 'Nota NPS CCS')[0],
        'Encuestas': len(x)
    })).reset_index()
    st.dataframe(concesionarios_nps.style.background_gradient(subset=['NPS Marca', 'NPS CCS'], cmap='RdYlGn'), use_container_width=True)

else:
    st.info("Por favor, carga un archivo para comenzar el análisis.")