import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import io
import re
import locale

# --- 1. CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Agrollanos Nómina Pro",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. ESTILOS CSS (TEMA AGROLLANOS DARK WEB) ---
st.markdown("""
    <style>
    /* Fondo General */
    .stApp {
        background-color: #121212;
        color: #E0E0E0;
    }
    /* Encabezado */
    .main-header {
        font-family: 'Arial Black', sans-serif;
        color: #2E7D32;
        text-align: center;
        font-size: 3rem;
        margin-bottom: 0;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    .sub-header {
        font-family: 'Segoe UI', sans-serif;
        color: #A0A0A0;
        text-align: center;
        font-size: 1.1rem;
        margin-top: -10px;
        margin-bottom: 30px;
        border-bottom: 1px solid #333;
        padding-bottom: 20px;
    }
    /* Botones */
    .stButton>button {
        background-color: #2E7D32;
        color: white;
        border-radius: 8px;
        border: none;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #4CAF50;
        border-color: #4CAF50;
        transform: scale(1.02);
    }
    /* Tablas */
    div[data-testid="stDataFrame"] {
        background-color: #1E1E1E;
        padding: 10px;
        border-radius: 10px;
        border: 1px solid #333;
    }
    /* Inputs */
    .stTextInput>div>div>input {
        background-color: #252526;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. LÓGICA DE NEGOCIO (Idéntica a la versión de escritorio) ---
HORAS_JORNADA_LV = 8.84 

def convertir_str_a_datetime(s):
    s = str(s).replace('"', '').replace("'", "").strip()
    formatos = [
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y %I:%M %p", "%d/%m/%Y %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p",
        "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"
    ]
    try: return pd.to_datetime(s, dayfirst=True).to_pydatetime()
    except: pass
    for fmt in formatos:
        try: return datetime.strptime(s, fmt)
        except: continue
    return None

def parsear_linea(linea):
    linea = linea.strip()
    if not linea: return None
    match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})', linea)
    if not match: return None
    fecha_start_idx = match.start()
    nombre_part = linea[:fecha_start_idx].strip()
    fechahora_part = linea[fecha_start_idx:].strip()
    nombre_part = re.sub(r'[^\w\s]', '', nombre_part).strip().upper()
    dt_obj = convertir_str_a_datetime(fechahora_part)
    if dt_obj: return {'TRABAJADOR': nombre_part, 'dt_obj': dt_obj}
    return None

def clasificar_horas(inicio, fin, festivos_seleccionados=set()):
    descuento = 0
    if inicio.time() <= time(11, 30) and fin.time() >= time(12, 30):
        descuento = 1.0
    
    duracion_bruta = (fin - inicio).total_seconds() / 3600
    total_h_netas = max(0, duracion_bruta - descuento)

    wd = inicio.weekday()
    fecha_inicio = inicio.date()
    es_festivo = fecha_inicio in festivos_seleccionados
    es_sab = (wd == 5)
    es_dom = (wd == 6) or es_festivo 
    
    limite_ordinario_diario = HORAS_JORNADA_LV if not es_sab else 0

    res = {'ord_diu':0, 'rec_noc':0, 'ext_diu':0, 'ext_noc':0, 'ord_dom_fes':0, 'ext_dom':0}
    cursor = inicio
    acumulado_ordinario = 0
    
    while cursor < fin:
        next_hop = min(fin, cursor + timedelta(minutes=1))
        mid = cursor + timedelta(seconds=30)
        h = mid.hour
        es_noche_horario = (h >= 21 or h < 6)
        if h < 6:
            if inicio.time() >= time(5, 50) and cursor < inicio.replace(hour=6, minute=0, second=0):
                es_noche_horario = False
        fraccion = (next_hop - cursor).total_seconds() / 3600
        
        # LÓGICA CENTRAL
        if es_sab:
            if es_noche_horario: res['ext_noc'] += fraccion
            else: res['ext_diu'] += fraccion
        elif es_dom:
            if acumulado_ordinario < (limite_ordinario_diario + descuento):
                res['ord_dom_fes'] += fraccion
                acumulado_ordinario += fraccion
            else:
                res['ext_dom'] += fraccion
        else:
            if acumulado_ordinario < (limite_ordinario_diario + descuento):
                if es_noche_horario: res['rec_noc'] += fraccion
                else: res['ord_diu'] += fraccion
                acumulado_ordinario += fraccion
            else:
                if es_noche_horario: res['ext_noc'] += fraccion
                else: res['ext_diu'] += fraccion
        cursor = next_hop

    # DESCUENTOS
    if descuento > 0:
        restante = descuento
        if res['ord_dom_fes'] >= restante: res['ord_dom_fes'] -= restante; restante = 0
        else: restante -= res['ord_dom_fes']; res['ord_dom_fes'] = 0
        
        if restante > 0:
            if res['ord_diu'] >= restante: res['ord_diu'] -= restante; restante = 0
            else: restante -= res['ord_diu']; res['ord_diu'] = 0
        
        if restante > 0:
            if res['rec_noc'] >= restante: res['rec_noc'] -= restante; restante = 0
            else: restante -= res['rec_noc']; res['rec_noc'] = 0

        if restante > 0:
            if res['ext_dom'] >= restante: res['ext_dom'] -= restante; restante = 0
            elif res['ext_diu'] >= restante: res['ext_diu'] -= restante; restante = 0
            elif res['ext_noc'] >= restante: res['ext_noc'] -= restante

    return {'total': total_h_netas, **res, 'sabado': es_sab, 'domingo': es_dom, 'festivo': es_festivo}

# --- 4. INTERFAZ WEB ---

# Títulos
st.markdown('<p class="main-header">AGROLLANOS S.A.S</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">PLATAFORMA WEB DE GESTIÓN CALCULAHORA DEL DEPARTAMENTO RRHH</p>', unsafe_allow_html=True)

# Sidebar para Filtros
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2921/2921222.png", width=80) # Icono genérico o URL de tu logo
    st.header("⚙️ Configuración")
    
    st.write("Seleccione el rango de fechas para filtrar los datos:")
    col_a, col_b = st.columns(2)
    with col_a:
        f_ini = st.date_input("Inicio", value=datetime.today().replace(day=1))
    with col_b:
        f_fin = st.date_input("Fin", value=datetime.today())
    
    usar_filtro = st.checkbox("Aplicar Filtro de Fechas", value=True)
    st.info("Nota: Si desactivas el filtro, se procesarán todos los datos del archivo.")

# Área Principal
datos_raw = []

col1, col2 = st.columns([1, 2])

with col1:
    st.markdown("### 📂 Cargar Datos")
    tipo_ingreso = st.radio("Método de Ingreso:", ["Subir Archivo Excel/CSV", "Pegar Texto Manual"])
    
    if tipo_ingreso == "Subir Archivo Excel/CSV":
        uploaded_file = st.file_uploader("Arrastra tu archivo aquí", type=['csv', 'xlsx'])
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    try: df = pd.read_csv(uploaded_file, sep=';', quotechar='"', encoding='utf-8')
                    except: 
                        try: df = pd.read_csv(uploaded_file, sep=';', quotechar='"', encoding='latin1')
                        except: df = pd.read_csv(uploaded_file, sep=',', quotechar='"')
                else:
                    df = pd.read_excel(uploaded_file)
                
                # Normalización
                df.columns = df.columns.str.replace('"', '').str.strip().str.upper()
                
                c_fecha = next((c for c in df.columns if 'FECHA' in c), None)
                c_hora = next((c for c in df.columns if 'HORA' in c), None)
                c_trab = next((c for c in df.columns if 'TRABAJADOR' in c), None)
                
                if c_fecha and c_hora and c_trab:
                    c_id = next((c for c in df.columns if 'ID' in c), None)
                    df['dt_obj'] = df.apply(lambda x: convertir_str_a_datetime(f"{str(x[c_fecha])} {str(x[c_hora])}"), axis=1)
                    
                    temp = df.to_dict('records')
                    for r in temp:
                        if r['dt_obj']:
                            datos_raw.append({
                                'TRABAJADOR': str(r[c_trab]).strip().upper(),
                                'dt_obj': r['dt_obj'],
                                'ID': str(r[c_id]) if c_id else 'N/A'
                            })
                    st.success(f"✅ {len(datos_raw)} registros cargados.")
                else:
                    st.error("Error: El archivo debe tener columnas TRABAJADOR, FECHA y HORA.")
            except Exception as e:
                st.error(f"Error leyendo archivo: {e}")

    else:
        texto = st.text_area("Pega los datos (Nombre Fecha Hora):", height=200)
        if texto:
            lines = texto.split('\n')
            for l in lines:
                res = parsear_linea(l)
                if res:
                    res['ID'] = 'MANUAL'
                    datos_raw.append(res)
            st.info(f"{len(datos_raw)} registros detectados.")

with col2:
    if datos_raw:
        st.markdown("### 📊 Procesamiento y Resultados")
        
        df_proc = pd.DataFrame(datos_raw).sort_values('dt_obj')
        df_proc['fecha_solo'] = df_proc['dt_obj'].dt.date
        
        if usar_filtro:
            mask = (df_proc['fecha_solo'] >= f_ini) & (df_proc['fecha_solo'] <= f_fin)
            df_proc = df_proc.loc[mask]
        
        if df_proc.empty:
            st.warning("⚠️ No hay datos en el rango de fechas seleccionado.")
        else:
            # Selector de Festivos Inteligente
            fechas_unicas = sorted(df_proc['fecha_solo'].unique())
            posibles_festivos = [f for f in fechas_unicas if f.weekday() < 5]
            
            festivos_sel = []
            if posibles_festivos:
                st.write("Selecciona los días **FESTIVOS** (Lunes a Viernes):")
                festivos_sel = st.multiselect(
                    "Calendario de Días Hábiles Encontrados:",
                    options=posibles_festivos,
                    format_func=lambda x: x.strftime("%A %d/%m/%Y")
                )
            
            if st.button("🚀 CALCULAR LIQUIDACIÓN AHORA", type="primary"):
                set_festivos = set(festivos_sel)
                resultados = []
                grupos = df_proc.groupby(['TRABAJADOR', 'fecha_solo'])
                
                for (trabajador, fecha), grupo in grupos:
                    grupo = grupo.sort_values('dt_obj')
                    if len(grupo) < 2:
                        resultados.append({"ID": grupo.iloc[0]['ID'], "Trabajador": trabajador, "Fecha": fecha, "Entrada": grupo.iloc[0]['dt_obj'].strftime("%H:%M"), "Salida": "ERR", "Total": 0, "Estado": "INCOMPLETO"})
                        continue
                    
                    ini, fin = grupo.iloc[0]['dt_obj'], grupo.iloc[-1]['dt_obj']
                    
                    if fin <= ini:
                        resultados.append({"ID": grupo.iloc[0]['ID'], "Trabajador": trabajador, "Fecha": fecha, "Entrada": ini.strftime("%H:%M"), "Salida": fin.strftime("%H:%M"), "Total": 0, "Estado": "ERR TIEMPO"})
                        continue
                    
                    c = clasificar_horas(ini, fin, set_festivos)
                    
                    resultados.append({
                        "ID": grupo.iloc[0]['ID'],
                        "Trabajador": trabajador,
                        "Fecha": fecha,
                        "Entrada": ini.strftime("%H:%M"),
                        "Salida": fin.strftime("%H:%M"),
                        "Total": round(c['total'], 2),
                        "Ord. Diurna": round(c['ord_diu'], 2),
                        "Rec. Nocturno": round(c['rec_noc'], 2),
                        "Ext. Diurna": round(c['ext_diu'], 2),
                        "Ext. Nocturna": round(c['ext_noc'], 2),
                        "H. Dom/Fes": round(c['ord_dom_fes'], 2),
                        "Extra Dom": round(c['ext_dom'], 2),
                        "Estado": "OK"
                    })
                
                df_res = pd.DataFrame(resultados)
                
                # Mostrar Tabla
                st.dataframe(df_res, use_container_width=True, height=500)
                
                # Botón Descarga
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_res.to_excel(writer, index=False, sheet_name='Nomina')
                
                st.download_button(
                    label="💾 DESCARGAR EXCEL FINAL",
                    data=buffer.getvalue(),
                    file_name=f"Nomina_Agrollanos_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# Pie de página
st.markdown("---")

st.caption("© 2025 Agrollanos S.A.S | Versión Web 1.0 | Desarrollado por Oswald Izquierdo")
