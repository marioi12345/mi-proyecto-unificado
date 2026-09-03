import io
import re
import gc
import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Configuración de la página web
st.set_page_config(page_title="Transformador de Archivos CLA", layout="wide")

st.title("📄 Telemedicina")
st.write("Sube tu archivo CSV o XLSX de origen para realizar la transformación y aplicar las reglas de negocio.")

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
                df = pd.read_csv(archivo_subido, sep=sep, encoding=encoding, on_bad_lines='skip', dtype=str)
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue

    archivo_subido.seek(0)
    return pd.read_csv(archivo_subido, sep=None, engine='python', on_bad_lines='skip', dtype=str)

def limpiar_rut(rut_val):
    """Limpia puntos, guion, dígito verificador y ceros a la izquierda. Ej: 15.393.463-0 -> 15393463"""
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

def normalizar_fecha(fecha_val):
    """Normaliza la fecha al formato DD/MM/YYYY aceptando marcas de tiempo con o sin hora/nanosegundos."""
    hoy = datetime.now()
    primer_dia_mes_anterior = (hoy - relativedelta(months=1)).replace(day=1)
    fecha_defecto = primer_dia_mes_anterior.strftime('%d/%m/%Y')

    if pd.isna(fecha_val) or not str(fecha_val).strip():
        return fecha_defecto

    fecha_str = str(fecha_val).strip()

    # Match para texto en español (ej. '21 de julio de 2026')
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
            return datetime(int(anio), mes_num, int(dia)).strftime('%d/%m/%Y')
        except Exception:
            return fecha_defecto
    else:
        try:
            dt_temp = pd.to_datetime(fecha_str, format='mixed', dayfirst=True)
            if not pd.isna(dt_temp):
                return dt_temp.strftime('%d/%m/%Y')
        except Exception:
            pass

    return fecha_defecto

# --- INTERFAZ Y PROCESAMIENTO ---

archivo_subido = st.file_uploader("Selecciona el archivo de entrada (CSV o XLSX)", type=["csv", "txt", "xlsx", "xls"])

if archivo_subido is not None:
    try:
        df_origen = cargar_archivo_inteligente(archivo_subido)
        
        # 1. PARSEO Y LIMPIEZA DE CAMPOS DE ORIGEN
        aporte_rs = df_origen['Aporte Redsalud'].apply(parsear_monto) if 'Aporte Redsalud' in df_origen.columns else pd.Series(0.0, index=df_origen.index)
        aporte_cla = df_origen['Aporte Caja Los Andes'].apply(parsear_monto) if 'Aporte Caja Los Andes' in df_origen.columns else pd.Series(0.0, index=df_origen.index)
        copago_fonasa_isapre = df_origen['COPAGO AFILIADO FONASA/ISAPRE'].apply(parsear_monto) if 'COPAGO AFILIADO FONASA/ISAPRE' in df_origen.columns else pd.Series(0.0, index=df_origen.index)
        copago_cla = df_origen['COPAGO AFILIADO CLA'].apply(parsear_monto) if 'COPAGO AFILIADO CLA' in df_origen.columns else pd.Series(0.0, index=df_origen.index)
        
        # Detección flexible para 'Seguro Complementario' o 'Seguro Complementarios'
        col_seguro = 'Seguro Complementario' if 'Seguro Complementario' in df_origen.columns else ('Seguro Complementarios' if 'Seguro Complementarios' in df_origen.columns else None)
        seguro_comp = df_origen[col_seguro].apply(parsear_monto) if col_seguro else pd.Series(0.0, index=df_origen.index)
        
        ben_desc = df_origen['BEN_DESCRIPCION'].fillna('').astype(str).str.strip() if 'BEN_DESCRIPCION' in df_origen.columns else pd.Series('', index=df_origen.index)

        # Cálculo de Aporte Total Pesos (Redsalud + CLA)
        ben_dctopesos = aporte_rs + aporte_cla

        # -------------------------------------------------------------
        # 2. VALIDACIONES Y REGLAS DE NEGOCIO (RECHAZO DE REGISTROS)
        # -------------------------------------------------------------
        motivo_descarte = []

        for idx in df_origen.index:
            errores = []
            
            # [VALIDACIÓN 1]: El Aporte Total (Aporte Redsalud + Aporte Caja Los Andes) no debe superar $6.690
            if ben_dctopesos.loc[idx] > 6690:
                errores.append(f"Aporte Total ({ben_dctopesos.loc[idx]:.0f}) supera los 6690")

            # [VALIDACIÓN 2]: El Aporte Redsalud no debe ser distinto de $1.220
            if aporte_rs.loc[idx] != 1220:
                errores.append(f"Aporte Redsalud ({aporte_rs.loc[idx]:.0f}) es distinto de 1220")

            # [VALIDACIÓN 3]: El Aporte Caja Los Andes no debe superar $5.470
            if aporte_cla.loc[idx] > 5470:
                errores.append(f"Aporte Caja Los Andes ({aporte_cla.loc[idx]:.0f}) supera los 5470")

            # [VALIDACIÓN 4]: Si la prestación es "Teleconsulta Medicina General", el COPAGO AFILIADO CLA debe ser 0
            if ben_desc.loc[idx] == "Teleconsulta Medicina General" and copago_cla.loc[idx] != 0:
                errores.append(f"Teleconsulta Medicina General tiene COPAGO CLA de {copago_cla.loc[idx]:.0f} (debe ser 0)")

            if errores:
                motivo_descarte.append("; ".join(errores))
            else:
                motivo_descarte.append(None)

        # -------------------------------------------------------------
        # 3. SEPARACIÓN DE DATAFRAMES (VÁLIDOS Y DESCARTADOS)
        # -------------------------------------------------------------
        df_origen['MOTIVO_RECHAZO'] = motivo_descarte

        mask_validos = df_origen['MOTIVO_RECHAZO'].isna()
        df_validos_orig = df_origen[mask_validos].copy()
        df_rechazados_orig = df_origen[~mask_validos].copy()

        # -------------------------------------------------------------
        # 4. CONSTRUCCIÓN DEL ARCHIVO FINAL DE SALIDA
        # -------------------------------------------------------------
        df_salida = pd.DataFrame()
        
        # [MAPPING 1]: RUT Afiliado sin puntos, guion ni DV
        df_salida['PER_RUT'] = df_validos_orig['PER_RUT'].apply(limpiar_rut)
        
        # [MAPPING 2]: Fecha normalizada en formato DD/MM/YYYY
        df_salida['BEN_FECTRX'] = df_validos_orig['BEN_FECTRX'].apply(normalizar_fecha)
        
        # [MAPPING 3]: BEN_MONTOTPESOS = COPAGO AFILIADO FONASA/ISAPRE - Seguro Complementario
        calc_montotpesos = copago_fonasa_isapre[mask_validos] - seguro_comp[mask_validos]
        df_salida['BEN_MONTOTPESOS'] = calc_montotpesos.astype(int)
        
        # [MAPPING 4]: BEN_DCTOPESOS = Aporte Redsalud + Aporte Caja Los Andes
        df_salida['BEN_DCTOPESOS'] = (aporte_rs[mask_validos] + aporte_cla[mask_validos]).astype(int)
        
        # [MAPPING 5]: BEN_COPAGOPESOS = COPAGO AFILIADO CLA
        df_salida['BEN_COPAGOPESOS'] = copago_cla[mask_validos].astype(int)
        
        # [MAPPING 6]: RUT Prestador sin puntos, guion ni DV
        df_salida['PREST_RUT'] = df_validos_orig['PREST_RUT'].apply(limpiar_rut)

        # -------------------------------------------------------------
        # 5. VALIDACIÓN DE CUADRATURA FINAL DE SALIDA
        # -------------------------------------------------------------
        # [VALIDACIÓN REGLA DE SALIDA]: BEN_MONTOTPESOS - BEN_DCTOPESOS - BEN_COPAGOPESOS = 0
        validacion_salida = df_salida['BEN_MONTOTPESOS'] - df_salida['BEN_DCTOPESOS'] - df_salida['BEN_COPAGOPESOS']
        registros_descuadrados = (validacion_salida.round(2) != 0).sum()

        # -------------------------------------------------------------
        # 6. MUESTRA DE REPORTES Y ALERTAS EN PANTALLA
        # -------------------------------------------------------------
        st.success("¡Procesamiento finalizado con éxito!")
        
        col1, col2 = st.columns(2)
        col1.metric("Registros Válidos (Archivo Final)", len(df_salida))
        col2.metric("Registros Descartados (Reporte)", len(df_rechazados_orig))

        # Alerta de Cuadratura
        if registros_descuadrados > 0:
            st.warning(f"⚠️ **Alerta de Cuadratura:** Se detectaron **{registros_descuadrados}** registros válidos descuadrados (BEN_MONTOTPESOS - BEN_DCTOPESOS - BEN_COPAGOPESOS ≠ 0).")
        else:
            st.info("✅ **Cuadratura Impecable:** Todos los registros en el archivo final cumplen con BEN_MONTOTPESOS - BEN_DCTOPESOS - BEN_COPAGOPESOS = 0.")

        # Alerta de Registros Descartados
        if len(df_rechazados_orig) > 0:
            st.warning(f"⚠️ Se descartaron **{len(df_rechazados_orig)}** registros por no cumplir con las reglas de negocio de montos/aportes.")
            with st.expander("Ver detalle de registros descartados y sus motivos"):
                cols_mostrar = [c for c in ['PER_RUT', 'BEN_DESCRIPCION', 'Aporte Redsalud', 'Aporte Caja Los Andes', 'COPAGO AFILIADO CLA', 'MOTIVO_RECHAZO'] if c in df_rechazados_orig.columns]
                st.dataframe(df_rechazados_orig[cols_mostrar])

        # Previsualización
        st.subheader("Vista previa del archivo procesado de salida")
        st.dataframe(df_salida.head(10))

        # -------------------------------------------------------------
        # 7. BOTONES DE DESCARGA
        # -------------------------------------------------------------
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

        # Liberación explícita de memoria
        st.cache_data.clear()
        gc.collect()

    except Exception as e:
        st.error(f"Ocurrió un error al procesar el archivo: {e}")
