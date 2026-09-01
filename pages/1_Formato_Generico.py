import io
import re
import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Configuración de la página
st.set_page_config(page_title="Transformador Universal", layout="wide")

st.title("🔄 Transformador Universal de Archivos")
st.write("Sube tu archivo (CSV, TXT o XLSX), configura el mapeo y genera la salida estandarizada.")

# --- 1. FUNCIONES AUXILIARES ---

def cargar_archivo_inteligente(archivo_subido):
    """Carga CSV, TXT o XLSX probando separadores y codificaciones como STRING puro (dtype=str)."""
    nombre_archivo = archivo_subido.name.lower()

    if nombre_archivo.endswith('.xlsx') or nombre_archivo.endswith('.xls'):
        archivo_subido.seek(0)
        return pd.read_excel(archivo_subido, dtype=str)

    separadores = [',', ';', '\t', '|']
    codificaciones = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']

    for encoding in codificaciones:
        for sep in separadores:
            try:
                archivo_subido.seek(0)
                df = pd.read_csv(archivo_subido, sep=sep, encoding=encoding, on_bad_lines='skip', dtype=str)
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue

    archivo_subido.seek(0)
    return pd.read_csv(archivo_subido, sep=None, engine='python', on_bad_lines='skip', dtype=str)

def limpiar_rut(rut_val):
    """
    Limpia puntos, guiones, ceros a la izquierda y remueve el dígito verificador (DV).
    Ejemplos:
      - '15.393.463-0' -> '15393463'
      - '153934630'   -> '15393463'
      - '15393463K'   -> '15393463'
      - '76110809'    -> '76110809'
    """
    if pd.isna(rut_val) or rut_val is None:
        return ""
    
    rut_str = str(rut_val).strip().upper().replace('.', '')
    
    # Caso 1: Viene con guion (ej: 15393463-0)
    if '-' in rut_str:
        rut_cuerpo = rut_str.split('-')[0]
        return rut_cuerpo.lstrip('0')
    
    # Caso 2: Viene sin guion
    rut_limpio = re.sub(r'[^0-9K]', '', rut_str)
    
    if not rut_limpio:
        return ""

    # Si termina en K o la longitud indica que trae DV (>= 8 caracteres)
    if rut_limpio.endswith('K') or len(rut_limpio) >= 8:
        return rut_limpio[:-1].lstrip('0')
    
    return rut_limpio.lstrip('0')

def limpiar_monto(val):
    """Convierte montos con puntos de miles a número entero exacto."""
    if pd.isna(val) or val is None:
        return 0
    
    val_str = str(val).strip()
    
    if re.match(r'^\d+\.0$', val_str):
        val_str = val_str.replace('.0', '000')

    val_limpio = re.sub(r'[^\d]', '', val_str)
    
    if not val_limpio:
        return 0
        
    return int(val_limpio)

def normalizar_fecha(fecha_val):
    """Normaliza la fecha y verifica que corresponda al mes anterior."""
    hoy = datetime.now()
    primer_dia_mes_anterior = (hoy - relativedelta(months=1)).replace(day=1)
    fecha_defecto = primer_dia_mes_anterior.strftime('%d/%m/%Y')
    
    mes_anterior_esperado = primer_dia_mes_anterior.month
    anio_anterior_esperado = primer_dia_mes_anterior.year

    if pd.isna(fecha_val) or not str(fecha_val).strip():
        return fecha_defecto

    fecha_str = str(fecha_val).strip()
    dt_parseada = None

    match = re.search(r'(\d{1,2})\s+de\s+([a-zA-Za-z]+)\s+de\s+(\d{4})', fecha_str)
    meses = {
        'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
        'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
        'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
    }
    
    if match:
        dia, mes_nombre, anio = match.groups()
        mes_num = meses.get(mes_nombre.lower(), 1)
        try:
            dt_parseada = datetime(int(anio), mes_num, int(dia))
        except Exception:
            pass
    else:
        try:
            dt_temp = pd.to_datetime(fecha_str, dayfirst=True)
            if not pd.isna(dt_temp):
                dt_parseada = dt_temp.to_pydatetime()
        except Exception:
            pass

    if dt_parseada is None:
        return fecha_defecto

    if dt_parseada.month == mes_anterior_esperado and dt_parseada.year == anio_anterior_esperado:
        return dt_parseada.strftime('%d/%m/%Y')
    else:
        return fecha_defecto

def obtener_indice_seguro(columnas, palabras_clave=[]):
    """Devuelve el índice de la columna en la lista buscando por palabras clave."""
    for idx, col in enumerate(columnas):
        if any(p.lower() in col.lower() for p in palabras_clave):
            return idx
    return 0

# --- 2. CARGA DE ARCHIVO Y MAPEO ---

archivo_subido = st.file_uploader("Selecciona el archivo de entrada", type=["csv", "txt", "xlsx", "xls"])

if archivo_subido is not None:
    try:
        df_origen = cargar_archivo_inteligente(archivo_subido)
        cols = list(df_origen.columns)
        
        st.info(f"📋 Archivo cargado correctamente: **{len(df_origen)}** filas y **{len(cols)}** columnas.")

        st.subheader("⚙️ Configuración del Mapeo")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 🆔 Identificación y Fechas")
            
            idx_rut = obtener_indice_seguro(cols, ['rut_titular', 'rut_afiliado', 'rut_asistente', 'per_rut', 'rut'])
            col_per_rut = st.selectbox("Columna para **PER_RUT**:", cols, index=idx_rut)

            idx_fecha = obtener_indice_seguro(cols, ['dia_actividad', 'fecha_emision', 'fecha', 'ben_fectrx'])
            col_fectrx = st.selectbox("Columna para **BEN_FECTRX** (Fecha):", cols, index=idx_fecha)

            origen_prest = st.radio("Origen para **PREST_RUT**:", ["Valor Fijo", "Columna del CSV"], index=1, horizontal=True, key="r_prest")
            if origen_prest == "Valor Fijo":
                val_prest = st.text_input("RUT Fijo para PREST_RUT:", value="76110809", key="val_prest")
            else:
                idx_prest = obtener_indice_seguro(cols, ['rut_proveedor', 'rut_prestador', 'prest_rut'])
                col_prest_rut = st.selectbox("Columna para **PREST_RUT**:", cols, index=idx_prest, key="sel_prest")

        with col2:
            st.markdown("#### 💰 Configuración de Montos")

            origen_monto = st.radio("Origen para **BEN_MONTOTPESOS**:", ["Valor Fijo", "Columna del CSV"], index=0, horizontal=True)
            if origen_monto == "Valor Fijo":
                val_monto = st.number_input("Valor fijo BEN_MONTOTPESOS:", value=50000)
            else:
                idx_m = obtener_indice_seguro(cols, ['valor_total', 'monto', 'valor'])
                col_monto = st.selectbox("Columna para BEN_MONTOTPESOS:", cols, index=idx_m)

            origen_dcto = st.radio("Origen para **BEN_DCTOPESOS**:", ["Valor Fijo", "Columna del CSV"], index=0, horizontal=True)
            if origen_dcto == "Valor Fijo":
                val_dcto = st.number_input("Valor fijo BEN_DCTOPESOS:", value=50000)
            else:
                idx_d = obtener_indice_seguro(cols, ['aporte_seguro', 'descuento', 'asistente'])
                col_dcto = st.selectbox("Columna para BEN_DCTOPESOS:", cols, index=idx_d)

            origen_copago = st.radio("Origen para **BEN_COPAGOPESOS**:", ["Valor Fijo", "Columna del CSV"], index=0, horizontal=True)
            if origen_copago == "Valor Fijo":
                val_copago = st.number_input("Valor fijo BEN_COPAGOPESOS:", value=0)
            else:
                idx_c = obtener_indice_seguro(cols, ['copago_beneficiario', 'copago'])
                col_copago = st.selectbox("Columna para BEN_COPAGOPESOS:", cols, index=idx_c)

        st.markdown("---")

        # --- 3. EJECUCIÓN Y DESCARGA ---
        if st.button("🚀 Procesar y Generar CSV", type="primary"):
            df_resultado = pd.DataFrame()

            df_resultado['PER_RUT'] = df_origen[col_per_rut].apply(limpiar_rut)
            df_resultado['BEN_FECTRX'] = df_origen[col_fectrx].apply(normalizar_fecha)

            df_resultado['BEN_MONTOTPESOS'] = val_monto if origen_monto == "Valor Fijo" else df_origen[col_monto].apply(limpiar_monto)
            df_resultado['BEN_DCTOPESOS'] = val_dcto if origen_dcto == "Valor Fijo" else df_origen[col_dcto].apply(limpiar_monto)
            df_resultado['BEN_COPAGOPESOS'] = val_copago if origen_copago == "Valor Fijo" else df_origen[col_copago].apply(limpiar_monto)

            if origen_prest == "Valor Fijo":
                df_resultado['PREST_RUT'] = limpiar_rut(val_prest)
            else:
                df_resultado['PREST_RUT'] = df_origen[col_prest_rut].apply(limpiar_rut)

            # Validar cuadratura
            validacion_temp = df_resultado['BEN_MONTOTPESOS'] - df_resultado['BEN_DCTOPESOS'] - df_resultado['BEN_COPAGOPESOS']
            registros_descuadrados = (validacion_temp.round(2) != 0).sum()

            st.success("¡Transformación finalizada correctamente!")

            if registros_descuadrados > 0:
                st.warning(f"⚠️ **Atención:** Se detectaron **{registros_descuadrados}** registros descuadrados (BEN_MONTOTPESOS - BEN_DCTOPESOS - BEN_COPAGOPESOS ≠ 0).")
            else:
                st.info("✅ **Validación impecable:** Todos los registros cumplen con la regla de cuadratura = 0.")

            st.subheader("Vista Previa del Resultado Estandarizado")
            st.dataframe(df_resultado.head(10))

            csv_resultado = df_resultado.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')

            st.download_button(
                label="⬇️ Descargar CSV Estandarizado",
                data=csv_resultado,
                file_name="resultado_estandarizado.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"Error al procesar el archivo: {e}")
