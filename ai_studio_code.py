import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google import generativeai as genai
import json
import os
from datetime import datetime
import base64

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="CX Dashboard Auto - IA",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- ESTILOS CSS PARA REPLICAR REACT/TAILWIND ---
st.markdown("""
<style>
    /* Fondo y Tipografía General */
    .stApp {
        background-color: #0f172a;
        color: #f1f5f9;
        font-family: 'Inter', -apple-system, sans-serif;
    }
    
    /* Header Estilo React */
    .header-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-bottom: 2rem;
        margin-bottom: 2rem;
        border-bottom: 1px solid #1e293b;
    }
    .logo-text {
        font-size: 1.8rem;
        font-weight: 900;
        text-transform: uppercase;
        font-style: italic;
        letter-spacing: -0.05em;
    }
    .cyan-text { color: #06b6d4; }
    
    /* Tarjetas KPI */
    .kpi-card {
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid #334155;
        border-radius: 1rem;
        padding: 1.5rem;
        height: 100%;
    }
    .kpi-title {
        color: #94a3b8;
        font-weight: 600;
        margin-bottom: 1rem;
        text-transform: uppercase;
        font-size: 0.8rem;
    }
    .kpi-value {
        font-size: 3.5rem;
        font-weight: 800;
        line-height: 1;
    }
    
    /* Alertas Críticas Estilo React */
    .alert-container {
        background: rgba(133, 77, 14, 0.1);
        border: 1px solid rgba(161, 98, 7, 0.5);
        border-radius: 1.5rem;
        padding: 1.5rem;
        margin-top: 2rem;
        position: relative;
    }
    .alert-header {
        color: #fde047;
        font-weight: 900;
        text-transform: uppercase;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* Botones de Módulo */
    .stButton>button {
        background-color: #1e293b;
        color: #94a3b8;
        border: 1px solid #334155;
        border-radius: 0.75rem;
        font-weight: 700;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        border-color: #06b6d4;
        color: #06b6d4;
    }
    
    /* Esconder elementos innecesarios de Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- FUNCIONES DE CÁLCULO (Lógica Original) ---
def calculate_nps_details(df, score_col):
    scores = pd.to_numeric(df[score_col], errors='coerce').dropna()
    total = len(scores)
    if total == 0: return 0, 0, 0, 0, 0
    
    promoters = len(scores[scores >= 9])
    passives = len(scores[(scores >= 7) & (scores < 9)])
    detractors = len(scores[scores < 7])
    
    nps = ((promoters - detractors) / total) * 100
    return nps, promoters, passives, detractors, total

def get_critical_alerts(df, global_nps_ccs):
    total_vol = len(df)
    threshold_vol = total_vol * 0.05 # UMERAL 5% SOLICITADO
    
    alerts = []
    
    # Desviación por sucursal
    sucursales = df.groupby('Sucursal')
    for name, group in sucursales:
        vol = len(group)
        if vol >= threshold_vol:
            nps, _, _, _, _ = calculate_nps_details(group, 'Nota NPS CCS')
            if nps < (global_nps_ccs - 10):
                alerts.append({
                    "type": "Desviación",
                    "msg": f"**{name}**: NPS {nps:.0f} (Impacto: {(vol/total_vol)*100:.1f}%)"
                })
                
    # Brecha Marca vs CCS
    for name, group in df.groupby('Concesionario'):
        vol = len(group)
        if vol >= threshold_vol:
            nps_m, _, _, _, _ = calculate_nps_details(group, 'Nota NPS Marca')
            nps_c, _, _, _, _ = calculate_nps_details(group, 'Nota NPS CCS')
            diff = abs(nps_m - nps_c)
            if diff > 15:
                alerts.append({
                    "type": "Brecha",
                    "msg": f"**{name}**: Brecha {diff:.0f} pts (Impacto: {(vol/total_vol)*100:.1f}%)"
                })
    return alerts

# --- INTEGRACIÓN GEMINI ---
def analyze_with_ai(comments, api_key):
    if not api_key or not comments: return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        prompt = f"""
        Actúa como un Experto Analista de Datos CX Automotriz. Analiza estos comentarios:
        {chr(10).join(comments[:150])}
        
        Devuelve un JSON exacto:
        {{
          "satisfaction_topics": [{{"topic": "...", "count": 0}}],
          "dissatisfaction_topics": [{{"topic": "...", "count": 0}}],
          "summary": "Resumen ejecutivo en 2 frases."
        }}
        """
        response = model.generate_content(prompt)
        return json.loads(response.text.strip().replace('```json', '').replace('```', ''))
    except:
        return None

# --- UI PRINCIPAL ---
# Header
st.markdown("""
    <div class="header-container">
        <div>
            <div class="logo-text">CX Dashboard <span class="cyan-text">Auto</span></div>
            <div style="color: #64748b; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.2em;">Data Insight System v3.1</div>
        </div>
    </div>
""", unsafe_allow_html=True)

# Entrada de Datos Dual (Mismo diseño que React)
if 'venta_df' not in st.session_state:
    st.markdown('<div style="text-align: center; margin-bottom: 2rem; color: #94a3b8;">Carga los archivos de Ventas y Postventa para iniciar el análisis integral.</div>', unsafe_allow_html=True)
    
    col_v, col_p = st.columns(2)
    
    with col_v:
        st.markdown('<div class="kpi-card"><h3 style="color:white; font-weight:900; margin-bottom:0;">MÓDULO VENTAS</h3><p style="color:#64748b; font-size:12px;">Base de datos de entregas y 0km</p></div>', unsafe_allow_html=True)
        file_v = st.file_uploader("Subir CSV/XLSX Ventas", type=['csv', 'xlsx'], key="v_upload")
        
    with col_p:
        st.markdown('<div class="kpi-card"><h3 style="color:white; font-weight:900; margin-bottom:0;">MÓDULO POSTVENTA</h3><p style="color:#64748b; font-size:12px;">Base de datos de servicios y taller</p></div>', unsafe_allow_html=True)
        file_p = st.file_uploader("Subir CSV/XLSX Postventa", type=['csv', 'xlsx'], key="p_upload")
    
    st.divider()
    api_key_input = st.text_input("Gemini API Key (Para análisis cualitativo)", type="password")
    
    if st.button("🚀 CARGAR E INICIAR ANÁLISIS", use_container_width=True):
        if file_v: st.session_state.venta_df = pd.read_excel(file_v) if file_v.name.endswith('xlsx') else pd.read_csv(file_v)
        if file_p: st.session_state.post_df = pd.read_excel(file_p) if file_p.name.endswith('xlsx') else pd.read_csv(file_p)
        st.session_state.api_key = api_key_input
        st.rerun()

# Reporte de Salida
else:
    # Sidebar para controles
    with st.sidebar:
        st.markdown("### 🎛️ CONTROLES")
        active_tab = st.radio("Módulo Activo", ["Ventas", "Postventa"])
        
        current_df = st.session_state.venta_df if active_tab == "Ventas" else st.session_state.post_df
        
        brands = ["TODAS"] + sorted(current_df['Marca'].dropna().unique().tolist())
        selected_brand = st.selectbox("Marca", brands)
        
        if st.button("Reiniciar"):
            for key in st.session_state.keys(): del st.session_state[key]
            st.rerun()

    # Filtrado
    df = current_df.copy()
    if selected_brand != "TODAS":
        df = df[df['Marca'] == selected_brand]
        
    # KPIs Estilo React
    n_marca, prom_m, pass_m, detr_m, total_m = calculate_nps_details(df, 'Nota NPS Marca')
    n_ccs, prom_c, pass_c, detr_c, total_c = calculate_nps_details(df, 'Nota NPS CCS')
    
    k1, k2 = st.columns(2)
    with k1:
        color = "#4ade80" if n_marca > 50 else "#facc15" if n_marca > 0 else "#f87171"
        st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-title">NPS Marca ({active_tab})</div>
                <div style="display: flex; justify-content: space-between; align-items: flex-end;">
                    <div class="kpi-value" style="color: {color};">{n_marca:.0f}</div>
                    <div style="text-align: right; font-size: 11px; color: #94a3b8;">
                        <div style="color:#4ade80">{prom_m} Promotores</div>
                        <div style="color:#facc15">{pass_m} Pasivos</div>
                        <div style="color:#f87171">{detr_m} Detractores</div>
                        <div style="margin-top:4px">Total: {total_m}</div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    with k2:
        color_c = "#4ade80" if n_ccs > 50 else "#facc15" if n_ccs > 0 else "#f87171"
        st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-title">NPS Concesionario - CCS ({active_tab})</div>
                <div style="display: flex; justify-content: space-between; align-items: flex-end;">
                    <div class="kpi-value" style="color: {color_c};">{n_ccs:.0f}</div>
                    <div style="text-align: right; font-size: 11px; color: #94a3b8;">
                        <div style="color:#4ade80">{prom_c} Promotores</div>
                        <div style="color:#facc15">{pass_c} Pasivos</div>
                        <div style="color:#f87171">{detr_c} Detractores</div>
                        <div style="margin-top:4px">Total: {total_c}</div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

    # Gráfico de Tendencia
    st.markdown('<div class="kpi-card" style="margin-top: 1.5rem;">', unsafe_allow_html=True)
    st.subheader(f"📈 Evolución Temporal - {active_tab}")
    date_col = next((c for c in df.columns if 'fecha' in c.lower() or 'periodo' in c.lower()), None)
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        trend = df.set_index(date_col).resample('M').apply(lambda x: calculate_nps_details(x, 'Nota NPS Marca')[0]).reset_index()
        trend.columns = ['Mes', 'NPS']
        fig = px.line(trend, x='Mes', y='NPS', template="plotly_dark", markers=True)
        fig.update_traces(line_color='#06b6d4', line_width=4)
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=350)
        st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ALERTAS CRÍTICAS AL 5%
    alertas = get_critical_alerts(df, n_ccs)
    if alertas:
        st.markdown(f"""
            <div class="alert-container">
                <div class="alert-header">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
                    Alertas Críticas de CX - {active_tab}
                    <span style="font-size: 9px; margin-left: auto; color: rgba(253, 224, 71, 0.5);">FILTRO IMPACTO: >5% VOL</span>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                    {"".join([f'<div style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px; font-size: 13px; color: #fde047;">{a["msg"]}</div>' for a in alertas])}
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.success(f"No se detectan alertas críticas significativas (>5% vol) en {active_tab}")

    # IA y Análisis Cualitativo
    st.divider()
    if st.session_state.get('api_key'):
        st.subheader("🤖 Análisis Cualitativo IA")
        comentarios = df['Comentario'].dropna().tolist()
        res_ia = analyze_with_ai(comentarios, st.session_state.api_key)
        if res_ia:
            st.info(f"**Resumen IA:** {res_ia['summary']}")
            c1, c2 = st.columns(2)
            with c1:
                st.write("**✅ Fortalezas**")
                for t in res_ia['satisfaction_topics']: st.write(f"- {t['topic']} ({t['count']})")
            with c2:
                st.write("**❌ Oportunidades**")
                for t in res_ia['dissatisfaction_topics']: st.write(f"- {t['topic']} ({t['count']})")

    # Tabla Detalle
    st.subheader("📋 Detalle por Sucursal")
    suc_table = df.groupby('Sucursal').apply(lambda x: pd.Series({
        'NPS Marca': calculate_nps_details(x, 'Nota NPS Marca')[0],
        'NPS CCS': calculate_nps_details(x, 'Nota NPS CCS')[0],
        'Encuestas': len(x)
    })).reset_index()
    st.dataframe(suc_table.sort_values('NPS Marca', ascending=False), use_container_width=True)
