import streamlit as st

st.set_page_config(
    page_title="Portal de Aplicaciones",
    page_icon="🚀",
    layout="wide"
)

st.title("Bienvenido al Portal Unificado 🚀")
st.write("Selecciona una de las herramientas del menú lateral para comenzar:")

st.markdown("""
- **Formato Genérico**: Acceso al generador de formatos.
- **IMED**: Sistema de gestión IMED.
- **PSP**: Módulo de análisis PSP.
""")