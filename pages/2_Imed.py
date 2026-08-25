import io
import pandas as pd
import streamlit as st

# Configuración de la página web
st.set_page_config(page_title="Transformador de Archivos IMED", layout="centered")

st.title("📄 Transformador de Archivos IMED")
st.write("Sube tu archivo (CSV, TXT o XLSX) de origen para limpiar los RUTs y calcular las validaciones automáticamente.")

# Función inteligente para cargar CSV o Excel
def cargar_archivo_inteligente(archivo_subido):
    nombre_archivo = archivo_subido.name.lower()
    
    # 1. Si el archivo es un Excel (.xlsx, .xls)
    if nombre_archivo.endswith('.xlsx') or nombre_archivo.endswith('.xls'):
        archivo_subido.seek(0)
        # Cargamos como dtype=str para preservar ceros a la izquierda y formatos numéricos puros
        return pd.read_excel(archivo_subido, dtype=str)

    # 2. Si es un archivo de texto o CSV
    separadores = [';', ',', '\t', '|']
    codificaciones = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']

    for encoding in codificaciones:
        for sep in separadores:
            try:
                archivo_subido.seek(0)
                df = pd.read_csv(archivo_subido, sep=sep, encoding=encoding, dtype=str)
                # Si logró leer más de 1 columna, encontramos el formato correcto
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue

    # Detección automática con motor python si falla lo anterior
    archivo_subido.seek(0)
    return pd.read_csv(archivo_subido, sep=None, engine='python', on_bad_lines='skip', dtype=str)

# 1. Botón para cargar el archivo (CSV, TXT, XLSX, XLS)
archivo_subido = st.file_uploader("Selecciona el archivo de entrada", type=["csv", "txt", "xlsx", "xls"])

if archivo_subido is not None:
    try:
        # Cargar archivo de forma robusta
        df = cargar_archivo_inteligente(archivo_subido)
        
        # -------------------------------------------------------------
        # FILTRADO / ELIMINACIÓN DE REGISTROS CON ESTADO_BONO = 0, "Bono Anulado" O APORTE_SEGURO = 0
        # -------------------------------------------------------------
        if 'estado_bono' in df.columns:
            # Detectar si contiene la palabra "anulado"
            es_anulado = df['estado_bono'].astype(str).str.contains('anulado', case=False, na=False)
            
            # Convertir a número para identificar los 0
            val_numerico = pd.to_numeric(df['estado_bono'], errors='coerce')
            es_cero = val_numerico == 0
            
            # Conservar solo los registros que NO sean 0 ni contengan "anulado"
            df = df[~(es_cero | es_anulado)]

        if 'aporte_seguro' in df.columns:
            # Asegurar conversión numérica para comparar correctamente
            df = df[pd.to_numeric(df['aporte_seguro'], errors='coerce').fillna(0) != 0]
        # -------------------------------------------------------------

        # Detectar la columna de bonificación automáticamente
        col_bonif = 'bonificacion_anterior' if 'bonificacion_anterior' in df.columns else 'bonificiacion_anterior'

        # Función para limpiar los RUTs
        def limpiar_rut(rut_val):
            if pd.isna(rut_val):
                return ""
            rut_str = str(rut_val).strip()
            if '-' in rut_str:
                rut_str = rut_str.split('-')[0]
            return rut_str.lstrip('0')

        # 2. Aplicar las transformaciones
        df_resultado = pd.DataFrame()
        df_resultado['PER_RUT'] = df['rut_titular'].apply(limpiar_rut)
        
        df_resultado['BEN_FECTRX'] = pd.to_datetime(
            df['fecha_emision'], 
            dayfirst=True, 
            format='mixed'
        ).dt.strftime('%d/%m/%Y')
        
        # Conversión segura a numérico para cálculo de montos
        valor_total = pd.to_numeric(df['valor_total'], errors='coerce').fillna(0)
        aporte_financiador = pd.to_numeric(df['aporte_financiador'], errors='coerce').fillna(0)
        aporte_seguro = pd.to_numeric(df['aporte_seguro'], errors='coerce').fillna(0)
        copago_beneficiario = pd.to_numeric(df['copago_beneficiario'], errors='coerce').fillna(0)

        df_resultado['BEN_MONTOTPESOS'] = valor_total - aporte_financiador 
        df_resultado['BEN_DCTOPESOS'] = aporte_seguro
        df_resultado['BEN_COPAGOPESOS'] = copago_beneficiario
        df_resultado['PREST_RUT'] = df['rut_prestador'].apply(limpiar_rut)
        
        # -------------------------------------------------------------
        # CÁLCULO INTERNO DE LA VALIDACIÓN Y ALERTAS
        # -------------------------------------------------------------
        validacion_temp = df_resultado['BEN_MONTOTPESOS'] - df_resultado['BEN_DCTOPESOS'] - df_resultado['BEN_COPAGOPESOS']
        registros_no_cero = (validacion_temp.round(2) != 0).sum()

        st.success("¡Archivo procesado con éxito!")

        # Mostrar la alerta según el resultado del cálculo
        if registros_no_cero > 0:
            st.warning(f"⚠️ **Atención:** Se encontraron **{registros_no_cero}** registros descuadrados (donde BEN_MONTOTPESOS - BEN_DCTOPESOS - BEN_COPAGOPESOS ≠ 0).")
        else:
            st.info("✅ **Validación impecable:** Todos los registros en la comprobación son iguales a 0.")
        # -------------------------------------------------------------

        # 3. Mostrar previsualización
        st.subheader("Vista previa de los datos procesados")
        st.dataframe(df_resultado.head(10))

        # 4. Convertir a CSV para la descarga
        csv_resultado = df_resultado.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')

        # Botón para descargar
        st.download_button(
            label="⬇️ Descargar CSV Procesado",
            data=csv_resultado,
            file_name="resultado_transformado.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"Ocurrió un error al procesar el archivo: {e}")
