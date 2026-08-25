import io
import pandas as pd
import streamlit as st

# Configuración de la página
st.set_page_config(page_title="Unificador de Archivos Procesados", layout="wide")

st.title("🔗 Unificador de Archivos Procesados")
st.write("Sube múltiples archivos estandarizados (CSV, TXT o XLSX) para consolidarlos en un único archivo CSV.")

# Columnas requeridas del formato estandarizado
COLUMNAS_ESPERADAS = [
    'PER_RUT',
    'BEN_FECTRX',
    'BEN_MONTOTPESOS',
    'BEN_DCTOPESOS',
    'BEN_COPAGOPESOS',
    'PREST_RUT'
]

def cargar_archivo_estandar(archivo_subido):
    """Carga CSV, TXT o XLSX asegurando la lectura en texto puro para no alterar formatos."""
    nombre = archivo_subido.name.lower()
    
    if nombre.endswith('.xlsx') or nombre.endswith('.xls'):
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

# 1. Componente para subir múltiples archivos a la vez
archivos_subidos = st.file_uploader(
    "Selecciona los archivos procesados a unir:",
    type=["csv", "txt", "xlsx", "xls"],
    accept_multiple_files=True
)

if archivos_subidos:
    lista_dfs = []
    errores = []

    # 2. Carga y verificación de estructura de cada archivo
    for archivo in archivos_subidos:
        try:
            df_temp = cargar_archivo_estandar(archivo)
            
            # Limpiar espacios en los nombres de las columnas
            df_temp.columns = [col.strip().upper() for col in df_temp.columns]
            
            # Verificar si contiene las columnas requeridas
            columnas_faltantes = [col for col in COLUMNAS_ESPERADAS if col not in df_temp.columns]
            
            if not columnas_faltantes:
                # Filtrar y ordenar según las columnas estandarizadas
                df_temp = df_temp[COLUMNAS_ESPERADAS]
                lista_dfs.append(df_temp)
            else:
                errores.append(f"❌ **{archivo.name}**: Faltan las columnas `{', '.join(columnas_faltantes)}`")
        except Exception as e:
            errores.append(f"❌ **{archivo.name}**: Error al leer el archivo ({e})")

    # Mostrar advertencias si algún archivo no cumplió la estructura
    if errores:
        with st.expander("⚠️ Ver detalles de archivos no compatibles", expanded=True):
            for err in errores:
                st.write(err)

    # 3. Proceso de unificación
    if lista_dfs:
        df_unificado = pd.concat(lista_dfs, ignore_index=index_line if 'index_line' in locals() else True)
        
        st.success(f"✅ Se unieron exitosamente **{len(lista_dfs)}** archivos con un total de **{len(df_unificado)}** registros.")

        # Opciones de filtrado adicional
        col_op1, col_op2 = st.columns(2)
        
        with col_op1:
            eliminar_duplicados = st.checkbox("Eliminar registros exactamente duplicados", value=False)
            if eliminar_duplicados:
                filas_antes = len(df_unificado)
                df_unificado = df_unificado.drop_duplicates()
                filas_despues = len(df_unificado)
                st.info(f"Se eliminaron **{filas_antes - filas_despues}** filas duplicadas.")

        # Recálculo de validación global
        monto = pd.to_numeric(df_unificado['BEN_MONTOTPESOS'], errors='coerce').fillna(0)
        dcto = pd.to_numeric(df_unificado['BEN_DCTOPESOS'], errors='coerce').fillna(0)
        copago = pd.to_numeric(df_unificado['BEN_COPAGOPESOS'], errors='coerce').fillna(0)

        descuadrados = ((monto - dcto - copago).round(2) != 0).sum()

        if descuadrados > 0:
            st.warning(f"⚠️ **Atención:** El consolidado contiene **{descuadrados}** registros descuadrados.")
        else:
            st.info("✅ **Validación impecable:** Todos los registros en el consolidado cumplen la regla de cuadratura = 0.")

        # Previsualización del consolidado
        st.subheader("Vista Previa del Consolidado Final")
        st.dataframe(df_unificado.head(15))

        # 4. Generación de descarga
        csv_unificado = df_unificado.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')

        st.download_button(
            label="⬇️ Descargar Archivo Consolidado (CSV)",
            data=csv_unificado,
            file_name="archivos_procesados_unificados.csv",
            mime="text/csv"
        )
