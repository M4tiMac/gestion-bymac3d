import streamlit as st
import pandas as pd
import sqlite3
import json
import os
from datetime import datetime

# --- CONFIGURACIÓN Y DB ---
DB_NAME = 'gestion_bymac3d.db'

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS pedidos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  fecha TEXT,
                  comprador TEXT,
                  productos TEXT,
                  items_ready TEXT,
                  pago TEXT, 
                  canal TEXT,
                  estado TEXT)''')
    
    columnas = [col[1] for col in c.execute("PRAGMA table_info(pedidos)")]
    if 'items_ready' not in columnas:
        c.execute("ALTER TABLE pedidos ADD COLUMN items_ready TEXT")
    if 'pago' not in columnas:
        c.execute("ALTER TABLE pedidos ADD COLUMN pago TEXT DEFAULT 'No'")
    conn.commit()

init_db()

st.set_page_config(page_title="Panel BYMAC3D", layout="wide")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configuración")
    st.divider()
    st.subheader("🗑️ Zona de Peligro")
    confirmar_borrado = st.checkbox("Confirmar borrado total")
    if st.button("Borrar Base de Datos", type="primary", disabled=not confirmar_borrado):
        if os.path.exists(DB_NAME):
            os.remove(DB_NAME)
            st.rerun()

st.title("🚀 Panel de Producción BYMAC3D")

# --- NUEVA SECCIÓN: RESUMEN COMPACTO ---
df_activos_stats = pd.read_sql_query("SELECT items_ready FROM pedidos WHERE estado != 'Terminado'", get_connection())

if not df_activos_stats.empty:
    conteo_total = {}
    conteo_faltante = {}

    for idx, row in df_activos_stats.iterrows():
        try:
            items = json.loads(row['items_ready'])
            for nombre_item, listo in items.items():
                nombre_limpio = nombre_item.strip().capitalize()
                conteo_total[nombre_limpio] = conteo_total.get(nombre_limpio, 0) + 1
                if not listo:
                    conteo_faltante[nombre_limpio] = conteo_faltante.get(nombre_limpio, 0) + 1
        except:
            continue

    if conteo_total:
        st.subheader("📊 Producción Pendiente")
        # Usamos markdown para crear una lista compacta con estilo
        resumen_html = ""
        for item, total in conteo_total.items():
            faltan = conteo_faltante.get(item, 0)
            if faltan > 0:
                resumen_html += f"**{item}:** {faltan} faltantes (de {total} total) | "
        
        if resumen_html:
            st.write(resumen_html[:-3]) # Sacamos el último separador
        else:
            st.success("✅ ¡Todas las piezas impresas!")
        st.divider()

# --- SECCIÓN 1: CARGA DE PEDIDOS ---
with st.expander("➕ Cargar Nuevo Pedido"):
    with st.form("nuevo_pedido", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            comprador = st.text_input("Nombre del Comprador")
            canal = st.selectbox("Canal de Venta", ["Mercado Libre", "Instagram", "Otro"])
            pago_inicial = st.selectbox("¿Ya pagó?", ["Sí", "No"])
        with col2:
            productos_input = st.text_area("Productos (separados por coma)")
        
        if st.form_submit_button("Registrar Pedido"):
            if comprador and productos_input:
                estado_pago = "Sí" if canal == "Mercado Libre" else pago_inicial
                lista_items = [i.strip() for i in productos_input.split(",") if i.strip()]
                checks_iniciales = json.dumps({item: False for item in lista_items})
                fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
                conn = get_connection()
                conn.execute("""INSERT INTO pedidos (fecha, comprador, productos, items_ready, pago, canal, estado) 
                             VALUES (?, ?, ?, ?, ?, ?, ?)""",
                             (fecha_hoy, comprador, productos_input, checks_iniciales, estado_pago, canal, "Pendiente"))
                conn.commit()
                st.rerun()

# --- SECCIÓN 2: GESTIÓN OPERATIVA ---
st.header("🛠️ Pedidos en Curso")

df_activos = pd.read_sql_query("SELECT * FROM pedidos WHERE estado != 'Terminado' ORDER BY id DESC", get_connection())

if df_activos.empty:
    st.info("No hay pedidos activos.")
else:
    for index, row in df_activos.iterrows():
        try:
            items_status = json.loads(row['items_ready']) if row['items_ready'] else {}
        except:
            items_status = {}

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
            with c1:
                st.subheader(row['canal'])
                st.caption(f"📅 {row['fecha']}")
                color_pago = "green" if row['pago'] == "Sí" else "red"
                st.markdown(f"**Pago:** :{color_pago}[{row['pago']}]")
                es_ml = row['canal'] == "Mercado Libre"
                if st.button("Cambiar Pago", key=f"pago_{row['id']}", disabled=es_ml):
                    nuevo_pago = "Sí" if row['pago'] == "No" else "No"
                    conn = get_connection()
                    conn.execute("UPDATE pedidos SET pago = ? WHERE id = ?", (nuevo_pago, row['id']))
                    conn.commit()
                    st.rerun()
            with c2:
                st.markdown(f"👤 **{row['comprador']}**")
                st.write("---")
                todos_listos = True
                nuevos_checks = {}
                if items_status:
                    for i, (item, checked) in enumerate(items_status.items()):
                        res = st.checkbox(item, value=checked, key=f"chk_{row['id']}_{i}")
                        nuevos_checks[item] = res
                        if not res: todos_listos = False
                if nuevos_checks != items_status:
                    conn = get_connection()
                    conn.execute("UPDATE pedidos SET items_ready = ? WHERE id = ?", (json.dumps(nuevos_checks), row['id']))
                    conn.commit()
                    st.rerun()
            with c3:
                st.write("**Progreso:**")
                if items_status:
                    listos = sum(nuevos_checks.values())
                    total = len(items_status)
                    st.progress(listos/total)
                    st.write(f"{listos}/{total} piezas")
            with c4:
                st.write("Acción")
                btn_listo = (todos_listos and row['pago'] == "Sí")
                if st.button("✅ Finalizar", key=f"btn_{row['id']}", type="primary" if btn_listo else "secondary"):
                    conn = get_connection()
                    conn.execute("UPDATE pedidos SET estado = 'Terminado' WHERE id = ?", (row['id'],))
                    conn.commit()
                    st.rerun()

# --- SECCIÓN 3: HISTORIAL ---
st.divider()
st.header("📜 Historial de Pedidos Terminados")
df_historial = pd.read_sql_query("SELECT * FROM pedidos WHERE estado == 'Terminado' ORDER BY id DESC", get_connection())
if not df_historial.empty:
    st.dataframe(df_historial, use_container_width=True)
