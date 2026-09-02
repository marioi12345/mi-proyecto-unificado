import io
import re
import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Configuración de la página web
st.set_page_config(page_title="Transformador de Archivos CLA", layout="wide")

st.title("📄 Telemedicina")
st.write("Sube tu archivo CSV o XLSX de origen para realizar la transformación y aplicar las reglas de negocio.")

# --- FUNCIONES AUXILIARES ---

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
                df = pd.read_csv(archivo_subido, sep=sep, encoding=encoding, on_bad_lines='skip', dtype=str)
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue

    archivo_subido.seek(0)
    return pd.read_csv(archivo_subido, sep=None, engine='python', on_bad_lines='skip', dtype=str)

def limpiar_rut(rut_val):
    """Limpia puntos, guion, dígito verificador y ceros a la izquierda."""
    if pd.isna(rut_val):
        return ""
    rut_str = str(rut_val).strip().replace('.', '')
    if '-' in rut_str:
        rut_str = rut_str.split('-')[0]
    return rut_str.lstrip('0')

def parsear_monto(val):
    """Convierte cadenas monetarias como '$12.250' o '12250' a float ejecutable."""
    if pd.isna(val):
        return 0.0
    val_str = str(val).replace('$', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(val_str)
    except Exception:
        return 0.0

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
    """Normaliza la fecha al formato DD/MM/YYYY."""
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

    return dt_parseada.strftime('%d/%m/%Y')

# --- INTERFAZ Y PROCESAMIENTO ---

archivo_subido = st.file_uploader("Selecciona el archivo de entrada (CSV o XLSX)", type=["csv", "txt", "xlsx", "xls"])

if archivo_subido is not None:
    try:
        df_origen = cargar_archivo_inteligente(archivo_subido)
        
        # 1. PARSEO DE CAMPOS NUMÉRICOS Y Mapeo
        aporte_rs = df_origen['Aporte Redsalud'].apply(parsear_monto)
        aporte_cla = df_origen['Aporte Caja Los Andes'].apply(parsear_monto)
        copago_fonasa_isapre = df_origen['COPAGO AFILIADO FONASA/ISAPRE'].apply(parsear_monto)
        copago_cla = df_origen['COPAGO AFILIADO CLA'].apply(parsear_monto)
        ben_desc = df_origen['BEN_DESCRIPCION'].fillna('').astype(str).str.strip()

        # Cálculo de Aporte Total Pesos
        ben_dctopesos = aporte_rs + aporte_cla

        # 2. VALIDACIONES DE REGLAS DE NEGOCIO
        motivo_descarte = []

        for idx in df_origen.index:
            errores = []
            
            # Regla 1: Aporte Redsalud + Aporte Caja Los Andes > 6690
            if ben_dctopesos.loc[idx] > 6690:
                errores.append(f"Aporte Total ({ben_dctopesos.loc[idx]:.0f}) supera los 6690")

            # Regla 2: Aporte Redsalud != 1220
            if aporte_rs.loc[idx] != 1220:
                errores.append(f"Aporte Redsalud ({aporte_rs.loc[idx]:.0f}) es distinto de 1220")

            # Regla 3: Aporte Caja Los Andes > 5470
            if aporte_cla.loc[idx] > 5470:
                errores.append(f"Aporte Caja Los Andes ({aporte_cla.loc[idx]:.0f}) supera los 5470")

            # Regla 4: Teleconsulta Medicina General -> COPAGO AFILIADO CLA debe ser 0
            if ben_desc.loc[idx] == "Teleconsulta Medicina General" and copago_cla.loc[idx] != 0:
                errores.append(f"Teleconsulta Medicina General tiene COPAGO CLA de {copago_cla.loc[idx]:.0f} (debe ser 0)")

            if errores:
                motivo_descarte.append("; ".join(errores))
            else:
                motivo_descarte.append(None)

        # 3. CONSTRUCCIÓN DE DATAFRAMES (VÁLIDOS Y DESCARTADOS)
        df_origen['MOTIVO_RECHAZO'] = motivo_descarte

        mask_validos = df_origen['MOTIVO_RECHAZO'].isna()
        df_validos_orig = df_origen[mask_validos].copy()
        df_rechazados_orig = df_origen[~mask_validos].copy()

        # Construir estructura requerida para salida válida
        df_salida = pd.DataFrame()
        df_salida['PER_RUT'] = df_validos_orig['PER_RUT'].apply(limpiar_rut)
        df_salida['BEN_FECTRX'] = df_validos_orig['BEN_FECTRX'].apply(normalizar_fecha)
        df_salida['BEN_DCTOPESOS'] = (aporte_rs[mask_validos] + aporte_cla[mask_validos]).astype(int)
        df_salida['BEN_MONTOTPESOS'] = copago_fonasa_isapre[mask_validos].astype(int)
        df_salida['BEN_COPAGOPESOS'] = copago_cla[mask_validos].astype(int)
        df_salida['PREST_RUT'] = df_validos_orig['PREST_RUT'].apply(limpiar_rut)

        # 4. REPORTES EN PANTALLA
        st.success("¡Procesamiento finalizado!")
        
        col1, col2 = st.columns(2)
        col1.metric("Registros Válidos (Archivo Final)", len(df_salida))
        col2.metric("Registros Descartados (Reporte)", len(df_rechazados_orig))

        if len(df_rechazados_orig) > 0:
            st.warning(f"⚠️ Se descartaron **{len(df_rechazados_orig)}** registros por no cumplir las reglas establecidas.")
            with st.expander("Ver detalle de registros descartados y motivos"):
                st.dataframe(df_rechazados_orig[['PER_RUT', 'BEN_DESCRIPCION', 'Aporte Redsalud', 'Aporte Caja Los Andes', 'COPAGO AFILIADO CLA', 'MOTIVO_RECHAZO']])

        # Previsualización salida
        st.subheader("Vista previa del archivo procesado de salida")
        st.dataframe(df_salida.head(10))

        # 5. BOTONES DE DESCARGA
        csv_salida = df_salida.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
        
        st.download_button(
            label="⬇️ Descargar CSV Procesado (Salida)",
            data=csv_salida,
            file_name="salida_procesada_CLA.csv",
            mime="text/csv"
        )

        if len(df_rechazados_orig) > 0:
            csv_rechazados = df_rechazados_orig.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                label="⚠️ Descargar Reporte de Registros Descartados",
                data=csv_rechazados,
                file_name="reporte_registros_descartados.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"Ocurrió un error al procesar el archivo: {e}")
