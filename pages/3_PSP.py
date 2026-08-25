import io
import pandas as pd
import streamlit as st

# Configuración de la página web
st.set_page_config(page_title="Transformador de Archivos PSP", layout="centered")

st.title("📄 Transformador de Archivos PSP")
st.write("Sube tu archivo CSV de origen para limpiar los RUTs y calcular las validaciones automáticamente.")

# Función inteligente para leer CSV con cualquier separador o codificación
def cargar_csv_inteligente(archivo_subido):
    # Probar diferentes separadores y codificaciones habituales en Excel
    separadores = [';', ',', '\t', '|']
    codificaciones = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']

    for encoding in codificaciones:
        for sep in separadores:
            try:
                archivo_subido.seek(0)
                df = pd.read_csv(archivo_subido, sep=sep, encoding=encoding)
                # Si logró leer más de 1 columna, encontramos el formato correcto
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue

    # Si todo lo anterior falla, intentar detección automática con motor python
    archivo_subido.seek(0)
    return pd.read_csv(archivo_subido, sep=None, engine='python', on_bad_lines='skip')

# 1. Botón para cargar el archivo CSV
archivo_subido = st.file_uploader("Selecciona el archivo CSV de entrada", type=["csv", "txt"])

if archivo_subido is not None:
    try:
        # Cargar archivo de forma robusta
        df = cargar_csv_inteligente(archivo_subido)
        
        # -------------------------------------------------------------
        # FILTRADO / ELIMINACIÓN DE REGISTROS CON ESTADO_BONO = 0 O APORTE_SEGURO = 0
        # -------------------------------------------------------------
        if 'estado_bono' in df.columns:
            # Asegurar conversión numérica para comparar correctamente
            df = df[pd.to_numeric(df['estado_bono'], errors='coerce') != 0]

        if 'aporte_seguro' in df.columns:
            # Asegurar conversión numérica para comparar correctamente
            df = df[pd.to_numeric(df['aporte_seguro'], errors='coerce') != 0]
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
        df_resultado['BEN_FECTRX'] = pd.to_datetime(df['fecha_emision']).dt.strftime('%d/%m/%Y')
        df_resultado['BEN_MONTOTPESOS'] = df['valor_total'] - df['aporte_financiador'] - df[col_bonif]
        df_resultado['BEN_DCTOPESOS'] = df['aporte_seguro']
        df_resultado['BEN_COPAGOPESOS'] = df['copago_beneficiario']
        df_resultado['PREST_RUT'] = df['rut_prestador'].apply(limpiar_rut)
        
        # -------------------------------------------------------------
        # CÁLCULO INTERNO DE LA VALIDACIÓN Y ALERTAS
        # -------------------------------------------------------------
        # Calculamos la columna temporalmente
        validacion_temp = df_resultado['BEN_MONTOTPESOS'] - df_resultado['BEN_DCTOPESOS'] - df_resultado['BEN_COPAGOPESOS']
        registros_no_cero = (validacion_temp.round(2) != 0).sum()

        st.success("¡Archivo procesado con éxito!")

        # Mostrar la alerta según el resultado del cálculo
        if registros_no_cero > 0:
            st.warning(f"⚠️ **Atención:** Se encontraron **{registros_no_cero}** registros descuadrados (donde BEN_MONTOTPESOS - BEN_DCTOPESOS - BEN_COPAGOPESOS ≠ 0).")
        else:
            st.info("✅ **Validación impecable:** Todos los registros en la comprobación son iguales a 0.")
        # -------------------------------------------------------------

        # 3. Mostrar previsualización (ya sin la columna de validación)
        st.subheader("Vista previa de los datos procesados")
        st.dataframe(df_resultado.head(10))

        # 4. Convertir a CSV para la descarga (ya sin la columna de validación)
        csv_resultado = df_resultado.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')

        # Botón para descargar a tu equipo
        st.download_button(
            label="⬇️ Descargar CSV Procesado",
            data=csv_resultado,
            file_name="resultado_transformado.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"Ocurrió un error al procesar el archivo: {e}")
