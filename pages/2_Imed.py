import io
import re
import gc
import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Configuración de la página web
st.set_page_config(page_title="Transformador de Archivos IMED", layout="centered")

st.title("📄 Transformador de Archivos IMED")
st.write("Sube tu archivo (CSV, TXT o XLSX) de origen para limpiar los RUTs y calcular las validaciones automáticamente.")

# --- FUNCIONES AUXILIARES ---

@st.cache_data(ttl=300)
def cargar_archivo_inteligente(archivo_subido):
    """Carga CSV, TXT o XLSX probando separadores y codificaciones como STRING puro (dtype=str)."""
    nombre_archivo = archivo_subido.name.lower()
    
    if nombre_archivo.endswith('.xlsx') or nombre_archivo.endswith('.xls'):
        archivo_subido.seek(0)
        return pd.read_excel(archivo_subido, dtype=str)

    separadores = [';', ',', '\t', '|']
    codificaciones = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']

    for encoding in codificaciones:
        for sep in separadores:
            try:
                archivo_subido.seek(0)
                df = pd.read_csv(archivo_subido, sep=sep, encoding=encoding, dtype=str)
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue

    archivo_subido.seek(0)
    return pd.read_csv(archivo_subido, sep=None, engine='python', on_bad_lines='skip', dtype=str)

def liberar_memoria():
    """Limpia la caché de datos de Streamlit y fuerza la liberación de memoria en el sistema."""
    st.cache_data.clear()
    gc.collect()

def limpiar_rut(rut_val):
    """Limpia puntos, guion, dígito verificador y ceros a la izquierda. Ej: 15.393.463-0 -> 15393463"""
    if pd.isna(rut_val):
        return ""
    rut_str = str(rut_val).strip().replace('.', '')
    if '-' in rut_str:
        rut_str = rut_str.split('-')[0]
    return rut_str.lstrip('0')

def es_fecha_mes_anterior(fecha_val):
    """Verifica si una fecha pertenece exactamente al mes anterior al actual."""
    hoy = datetime.now()
    primer_dia_mes_anterior = (hoy - relativedelta(months=1)).replace(day=1)
    mes_esperado = primer_dia_mes_anterior.month
    anio_esperado = primer_dia_mes_anterior.year

    if pd.isna(fecha_val) or not str(fecha_val).strip():
        return False

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
        return False

    return dt_parseada.month == mes_esperado and dt_parseada.year == anio_esperado

def normalizar_fecha(fecha_val):
    """
    Normaliza la fecha y verifica que corresponda al mes anterior.
    Si no corresponde al mes anterior (o si la fecha es inválida/vacía),
    devuelve el primer día del mes anterior en formato DD/MM/YYYY.
    """
    hoy = datetime.now()
    primer_dia_mes_anterior = (hoy - relativedelta(months=1)).replace(day=1)
    fecha_defecto = primer_dia_mes_anterior.strftime('%d/%m/%Y')

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

    if es_fecha_mes_anterior(fecha_val):
        return dt_parseada.strftime('%d/%m/%Y')
    else:
        return fecha_defecto

# --- INTERFAZ Y PROCESAMIENTO ---

archivo_subido = st.file_uploader("Selecciona el archivo de entrada", type=["csv", "txt", "xlsx", "xls"])

if archivo_subido is not None:
    try:
        df = cargar_archivo_inteligente(archivo_subido)
        
        # -------------------------------------------------------------
        # FILTRADO / ELIMINACIÓN DE REGISTROS CON ESTADO_BONO = 0, "Bono Anulado" O APORTE_SEGURO = 0
        # -------------------------------------------------------------
        if 'estado_bono' in df.columns:
            es_anulado = df['estado_bono'].astype(str).str.contains('anulado', case=False, na=False)
            val_numerico = pd.to_numeric(df['estado_bono'], errors='coerce')
            es_cero = val_numerico == 0
            df = df[~(es_cero | es_anulado)]

        if 'aporte_seguro' in df.columns:
            df = df[pd.to_numeric(df['aporte_seguro'], errors='coerce').fillna(0) != 0]

        # -------------------------------------------------------------
        # 1. EVALUACIÓN Y ALERTAS DE FECHA
        # -------------------------------------------------------------
        hoy = datetime.now()
        primer_dia_mes_anterior = (hoy - relativedelta(months=1)).replace(day=1)
        fecha_primer_dia_str = primer_dia_mes_anterior.strftime('%d/%m/%Y')

        # Detectar cuáles registros no corresponden al mes anterior
        es_valido_mask = df['fecha_emision'].apply(es_fecha_mes_anterior)
        cant_fechas_incorrectas = (~es_valido_mask).sum()

        if cant_fechas_incorrectas > 0:
            st.warning(f"⚠️ **Alerta de Fechas:** Se detectaron **{cant_fechas_incorrectas}** registros con fecha distinta al mes anterior.")
            
            accion_fechas = st.radio(
                "¿Qué deseas hacer con los registros cuyas fechas no corresponden al mes anterior?",
                [
                    "Eliminar los registros con fecha distinta al mes anterior",
                    f"Modificar fecha por el primer día del mes anterior ({fecha_primer_dia_str})"
                ]
            )
        else:
            accion_fechas = "Modificar"
            st.info("✅ **Validación de Fechas:** Todas las fechas pertenecen al mes anterior.")

        # Aplicar eliminación si el usuario selecciona esa opción
        if "Eliminar" in accion_fechas:
            df = df[es_valido_mask].copy()

        # -------------------------------------------------------------
        # 2. APLICAR LAS TRANSFORMACIONES
        # -------------------------------------------------------------
        df_resultado = pd.DataFrame()
        df_resultado['PER_RUT'] = df['rut_titular'].apply(limpiar_rut)
        
        if "Eliminar" in accion_fechas:
            df_resultado['BEN_FECTRX'] = pd.to_datetime(df['fecha_emision'], dayfirst=True).dt.strftime('%d/%m/%Y')
        else:
            df_resultado['BEN_FECTRX'] = df['fecha_emision'].apply(normalizar_fecha)
        
        valor_total = pd.to_numeric(df['valor_total'], errors='coerce').fillna(0)
        aporte_financiador = pd.to_numeric(df['aporte_financiador'], errors='coerce').fillna(0)
        aporte_seguro = pd.to_numeric(df['aporte_seguro'], errors='coerce').fillna(0)
        copago_beneficiario = pd.to_numeric(df['copago_beneficiario'], errors='coerce').fillna(0)

        df_resultado['BEN_MONTOTPESOS'] = valor_total - aporte_financiador 
        df_resultado['BEN_DCTOPESOS'] = aporte_seguro
        df_resultado['BEN_COPAGOPESOS'] = copago_beneficiario
        df_resultado['PREST_RUT'] = df['rut_prestador'].apply(limpiar_rut)
        
        # -------------------------------------------------------------
        # 3. CÁLCULO INTERNO DE LA VALIDACIÓN Y ALERTAS DE CUADRATURA
        # -------------------------------------------------------------
        validacion_temp = df_resultado['BEN_MONTOTPESOS'] - df_resultado['BEN_DCTOPESOS'] - df_resultado['BEN_COPAGOPESOS']
        registros_no_cero = (validacion_temp.round(2) != 0).sum()

        st.success("¡Archivo procesado con éxito!")

        if registros_no_cero > 0:
            st.warning(f"⚠️ **Atención:** Se encontraron **{registros_no_cero}** registros descuadrados (donde BEN_MONTOTPESOS - BEN_DCTOPESOS - BEN_COPAGOPESOS ≠ 0).")
        else:
            st.info("✅ **Validación impecable:** Todos los registros en la comprobación son iguales a 0.")

        # -------------------------------------------------------------
        # 4. PREVISUALIZACIÓN Y DESCARGA
        # -------------------------------------------------------------
        st.subheader("Vista previa de los datos procesados")
        st.dataframe(df_resultado.head(10))

        csv_resultado = df_resultado.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')

        st.download_button(
            label="⬇️ Descargar CSV Procesado",
            data=csv_resultado,
            file_name="resultado_transformado.csv",
            mime="text/csv"
        )

        liberar_memoria()

    except Exception as e:
        st.error(f"Ocurrió un error al procesar el archivo: {e}")
