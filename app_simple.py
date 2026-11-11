"""
ApuntaYa - Versión simple para publicar en Streamlit Cloud.

Instalar:  pip install streamlit pandas
Ejecutar:  streamlit run apuntaya_real.py

Se crean junto al archivo:
  - apuntaya.db  -> base de datos (usuarios, apuntes, ventas)
  - archivos/    -> PDFs, QRs y comprobantes subidos
"""
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

# ---------- Configuración (cámbiala a tu gusto) ----------
DB = "apuntaya.db"
CARPETA = "archivos"
COMISION = 0.15          # 15% para la plataforma
MONEDA = "Bs"
try:
    PIN_ADMIN = str(st.secrets["PIN_ADMIN"])   # el PIN va en Secrets (no en el código)
except Exception:
    PIN_ADMIN = "1234"                          # solo para pruebas en tu laptop

os.makedirs(CARPETA, exist_ok=True)
st.set_page_config(page_title="ApuntaYa", page_icon="📚")


# ---------- Base de datos ----------
def conectar():
    return sqlite3.connect(DB)


def iniciar_db():
    with conectar() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS apuntes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT, materia TEXT, docente TEXT,
            vendedor TEXT, tel_vendedor TEXT, precio REAL,
            archivo TEXT, qr TEXT, fecha TEXT);
        CREATE TABLE IF NOT EXISTS ventas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apunte_id INTEGER, comprador TEXT, tel_comprador TEXT,
            monto REAL, metodo TEXT, comprobante TEXT,
            estado TEXT, fecha TEXT);
        """)


def consulta(sql, params=()):
    with conectar() as con:
        return pd.read_sql_query(sql, con, params=params)


def ejecutar(sql, params=()):
    with conectar() as con:
        con.execute(sql, params)


def guardar_archivo(archivo):
    if archivo is None:
        return None
    ruta = os.path.join(CARPETA, f"{uuid.uuid4().hex}_{archivo.name}")
    with open(ruta, "wb") as f:
        f.write(archivo.getbuffer())
    return ruta


def ahora():
    return (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M")  # hora de Bolivia


iniciar_db()

st.title("📚 ApuntaYa")
st.caption("Aprobó el que ya sabe. Aprende de él.")

t1, t2, t3, t4 = st.tabs(["🔎 Catálogo", "💸 Publicar", "🧾 Mis compras", "🔐 Admin"])

# ---------- 1. Catálogo y compra ----------
with t1:
    ap = consulta("SELECT * FROM apuntes ORDER BY id DESC")
    materias = ["Todas"] + sorted(ap["materia"].unique().tolist()) if not ap.empty else ["Todas"]
    filtro = st.selectbox("Materia", materias)
    if filtro != "Todas":
        ap = ap[ap["materia"] == filtro]
    if ap.empty:
        st.info("Aún no hay apuntes. Publica el primero en la pestaña Publicar.")
    for _, r in ap.iterrows():
        with st.container(border=True):
            st.subheader(r["titulo"])
            st.write(f"{r['materia']} · {r['docente']} · Vendedor: {r['vendedor']}")
            st.write(f"**{MONEDA}{r['precio']:.2f}**")
            with st.expander("Comprar"):
                if r["qr"] and os.path.exists(r["qr"]):
                    st.image(r["qr"], caption="Si pagas por QR, escanea este código", width=220)
                with st.form(f"compra{r['id']}"):
                    nom = st.text_input("Tu nombre")
                    tel = st.text_input("Tu teléfono")
                    metodo = st.radio("Forma de pago", ["Efectivo", "QR"], horizontal=True)
                    comp = st.file_uploader("Comprobante (solo si pagaste por QR)",
                                            type=["png", "jpg", "jpeg"],
                                            key=f"comp{r['id']}")
                    ok = st.form_submit_button("Registrar compra")
                if ok:
                    if not nom or not tel:
                        st.error("Escribe tu nombre y teléfono.")
                    elif metodo == "QR" and comp is None:
                        st.error("Sube el comprobante del pago por QR.")
                    else:
                        ejecutar(
                            "INSERT INTO ventas(apunte_id, comprador, tel_comprador, monto, "
                            "metodo, comprobante, estado, fecha) VALUES (?,?,?,?,?,?,?,?)",
                            (int(r["id"]), nom, tel, float(r["precio"]), metodo,
                             guardar_archivo(comp), "Pendiente", ahora()))
                        st.success("Compra registrada. Cuando se confirme tu pago "
                                   "podrás descargar el apunte en 'Mis compras'.")

# ---------- 2. Publicar ----------
with t2:
    with st.form("publicar"):
        titulo = st.text_input("Título del apunte")
        materia = st.text_input("Materia")
        docente = st.text_input("Docente")
        vendedor = st.text_input("Tu nombre")
        tel_v = st.text_input("Tu teléfono")
        precio = st.number_input(f"Precio ({MONEDA})", min_value=0.5, value=2.0, step=0.5)
        pdf = st.file_uploader("Archivo del apunte (PDF)", type=["pdf"])
        qr = st.file_uploader("Tu QR de cobro (imagen, opcional)", type=["png", "jpg", "jpeg"])
        enviar = st.form_submit_button("Publicar apunte")
    if enviar:
        if not (titulo and materia and vendedor and tel_v and pdf):
            st.error("Completa todos los campos y sube el PDF.")
        else:
            ejecutar(
                "INSERT INTO apuntes(titulo, materia, docente, vendedor, tel_vendedor, "
                "precio, archivo, qr, fecha) VALUES (?,?,?,?,?,?,?,?,?)",
                (titulo, materia, docente, vendedor, tel_v, float(precio),
                 guardar_archivo(pdf), guardar_archivo(qr), ahora()))
            st.success("¡Apunte publicado!")

# ---------- 3. Mis compras ----------
with t3:
    tel = st.text_input("Escribe el teléfono con el que compraste")
    if tel:
        mis = consulta(
            "SELECT v.id, a.titulo, a.archivo, v.monto, v.metodo, v.estado, v.fecha "
            "FROM ventas v JOIN apuntes a ON a.id = v.apunte_id "
            "WHERE v.tel_comprador = ? ORDER BY v.id DESC", (tel,))
        if mis.empty:
            st.info("No hay compras con ese teléfono.")
        for _, r in mis.iterrows():
            with st.container(border=True):
                st.write(f"**{r['titulo']}** · {MONEDA}{r['monto']:.2f} · {r['metodo']}")
                st.write(f"Estado: **{r['estado']}** · {r['fecha']}")
                if r["estado"] == "Pagado" and r["archivo"] and os.path.exists(r["archivo"]):
                    with open(r["archivo"], "rb") as f:
                        st.download_button("⬇️ Descargar apunte", f.read(),
                                           file_name=os.path.basename(r["archivo"]),
                                           key=f"dl{r['id']}")

# ---------- 4. Admin: confirmar pagos y caja ----------
with t4:
    pin = st.text_input("PIN de administrador", type="password")
    if pin and pin != PIN_ADMIN:
        st.error("PIN incorrecto.")
    if pin == PIN_ADMIN:
        v = consulta(
            "SELECT v.id, a.titulo, a.vendedor, v.comprador, v.tel_comprador, "
            "v.monto, v.metodo, v.comprobante, v.estado, v.fecha "
            "FROM ventas v JOIN apuntes a ON a.id = v.apunte_id ORDER BY v.id DESC")

        st.subheader("Pagos por confirmar")
        pend = v[v["estado"] == "Pendiente"]
        if pend.empty:
            st.info("No hay pagos pendientes.")
        for _, r in pend.iterrows():
            with st.container(border=True):
                st.write(f"**{r['titulo']}** · {r['comprador']} ({r['tel_comprador']}) · "
                         f"{MONEDA}{r['monto']:.2f} · {r['metodo']}")
                if r["comprobante"] and os.path.exists(r["comprobante"]):
                    st.image(r["comprobante"], width=200)
                if st.button("✅ Confirmar pago", key=f"ok{r['id']}"):
                    ejecutar("UPDATE ventas SET estado='Pagado' WHERE id=?", (int(r["id"]),))
                    st.rerun()

        st.subheader("Caja")
        pag = v[v["estado"] == "Pagado"]
        efectivo = pag.loc[pag["metodo"] == "Efectivo", "monto"].sum()
        por_qr = pag.loc[pag["metodo"] == "QR", "monto"].sum()
        total = efectivo + por_qr
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Efectivo", f"{MONEDA}{efectivo:.2f}")
        c2.metric("QR", f"{MONEDA}{por_qr:.2f}")
        c3.metric("Total", f"{MONEDA}{total:.2f}")
        c4.metric("Comisión", f"{MONEDA}{total * COMISION:.2f}")

        st.subheader("Historial de ventas")
        st.dataframe(v.drop(columns=["comprobante"]), hide_index=True)
        st.download_button("Descargar ventas (CSV)",
                           v.drop(columns=["comprobante"]).to_csv(index=False).encode("utf-8-sig"),
                           file_name="ventas.csv", mime="text/csv")
