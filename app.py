import json
import re
import streamlit as st
from pathlib import Path
from streamlit_searchbox import st_searchbox

DATA_DIR = Path(__file__).resolve().parent / "data"

st.set_page_config(
    page_title="Analizador de Bolsa",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"], .main, section.main {
    background-color: #f4f6fa !important;
}
/* No ocultar stHeader entero: ahí vive el botón para abrir/cerrar el sidebar.
   Solo se lo hace transparente y bajito; el menú "Deploy"/hamburguesa se
   oculta aparte via stToolbar más abajo. */
[data-testid="stHeader"] {
    background: transparent !important;
    box-shadow: none !important;
    height: 2.75rem;
}
[data-testid="stSidebar"] {
    background-color: #ffffff !important;
    border-right: 1px solid #e2e6ee;
}
[data-testid="stSidebarCollapsedControl"] {
    color: #111827 !important;
}
.block-container { padding-top: 1.8rem !important; padding-bottom: 2rem !important; }

.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #ffffff;
    padding: 6px;
    border-radius: 10px;
    border: 1px solid #e2e6ee;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 7px;
    padding: 7px 16px;
    color: #4b5563 !important;
    font-weight: 600;
    font-size: 13px;
    border: none !important;
}
.stTabs [aria-selected="true"] {
    background: #e2e6ee !important;
    color: #111827 !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top: 20px; }

/* Las tarjetas usan estilos inline — sin clases .card-* */

div[data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1px solid #e2e6ee !important;
    border-radius: 10px !important;
}
hr { border-color: #e2e6ee !important; margin: 1.2rem 0 !important; }
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
[data-testid="stToolbar"] { display: none !important; }

/* ── Botón título "Analizador de Bolsa" en el sidebar ── */
[data-testid="stSidebar"] .stButton:first-child > button {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #111827 !important;
    font-size: 19px !important;
    font-weight: 700 !important;
    letter-spacing: 0 !important;
    padding: 2px 0 !important;
    text-align: left !important;
    width: 100% !important;
    line-height: 1.3 !important;
}
[data-testid="stSidebar"] .stButton:first-child > button:hover {
    color: #00c896 !important;
    background: transparent !important;
}

/* ── Switch grande Acciones / ETFs (esquina superior izquierda, sidebar) ── */
[data-testid="stSidebar"] [data-testid="stSegmentedControl"] {
    margin: 4px 0 2px;
}
[data-testid="stSidebar"] [data-testid="stSegmentedControl"] button,
[data-testid="stSidebar"] div[role="radiogroup"] label {
    font-size: 16px !important;
    font-weight: 800 !important;
    padding: 14px 8px !important;
    min-height: 48px !important;
}
[data-testid="stSidebar"] [data-testid="stSegmentedControl"] [aria-checked="true"] {
    background: #00c896 !important;
    color: #f4f6fa !important;
}
</style>
""", unsafe_allow_html=True)

# ── AUTENTICACIÓN ─────────────────────────────────────────────────────────────
try:
    _CLAVE = st.secrets["access_key"]
except Exception:
    _CLAVE = "bolsa123"

if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False

if not st.session_state.auth_ok:
    st.markdown("""
    <div style="max-width:360px;margin:120px auto 0;text-align:center">
        <div style="font-size:48px">📊</div>
        <h2 style="color:#111827;margin:12px 0 4px;font-size:22px">Analizador de Bolsa</h2>
        <p style="color:#64748b;font-size:14px;margin-bottom:28px">Acceso restringido</p>
    </div>
    """, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        pwd = st.text_input("Contraseña", type="password", placeholder="••••••••", label_visibility="collapsed")
        if st.button("Entrar →", use_container_width=True, type="primary"):
            if pwd == _CLAVE:
                st.session_state.auth_ok = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta")
    st.stop()

# Estado de sesión: ticker seleccionado desde el ranking
if "ticker_click" not in st.session_state:
    st.session_state.ticker_click = None
# Modo global: "acciones" o "etfs" — controla toda la página (switch del sidebar)
if "modo" not in st.session_state:
    st.session_state.modo = "acciones"



# ── HELPERS ──────────────────────────────────────────────────────────────────

def fmt(val, decimals=2):
    if val is None:
        return "N/D"
    try:
        return f"{round(float(val), decimals)}"
    except:
        return "N/D"


def card(titulo, valor, estado=None, color="#64748b", interpretacion=None, sector_ref=None):
    tiene_color = color not in ("#64748b", None)
    border      = color if (estado or tiene_color) else "#e2e6ee"
    valor_color = color if (not estado and tiene_color) else "#111827"

    # Truncar en Python: evita que CSS webkit-clamp filtre HTML crudo
    if interpretacion and len(interpretacion) > 130:
        interpretacion = interpretacion[:127] + "…"

    bloques = [
        f'<p style="margin:0 0 5px;font-size:10.5px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.9px;color:#6b7280;width:100%">{titulo}</p>',
        f'<p style="margin:0;font-size:22px;font-weight:700;color:{valor_color};'
        f'line-height:1.2;word-break:break-word">{valor}</p>',
    ]
    if estado:
        bloques.append(
            f'<p style="margin:5px 0 0;font-size:11.5px;font-weight:700;color:{color}">{estado}</p>'
        )
    if interpretacion:
        bloques.append(
            f'<p style="margin:6px 0 0;font-size:11.5px;color:#374151;line-height:1.45;text-align:left">{interpretacion}</p>'
        )
    if sector_ref:
        bloques.append(
            f'<p style="margin:6px 0 0;font-size:10.5px;color:#64748b;background:#f4f6fa;'
            f'border-radius:4px;padding:2px 7px;display:inline-block;'
            f'max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📊 {sector_ref}</p>'
        )

    inner = "".join(bloques)
    return (
        f'<div style="background:#ffffff;border:1px solid {border};border-radius:10px;'
        f'padding:14px 14px 12px;text-align:center;height:225px;overflow:hidden;'
        f'display:flex;flex-direction:column;align-items:center;box-sizing:border-box">'
        f'{inner}</div>'
    )


# El campo "Sector / Industria" del Excel de acciones es muy granular (161
# valores únicos para 173 empresas: casi todas quedan solas). Para agrupar
# "competencia" real se usa el sector amplio (lo que precede al primer " - "
# o " / "), con sinónimos evidentes normalizados a un mismo bucket.
_SECTOR_AMPLIO_SINONIMOS = {
    "FINANCIERO": "Servicios Financieros",
    "MATERIALES": "Materiales Basicos",
    "INDUSTRIAL": "Industriales",
    "INDUSTRIAL-TECNOLOGIA": "Industriales",
    "CONSUMO BASICO": "Consumo Defensivo",
    "SEMICONDUCTORES": "Tecnologia",
    "TECNOLOGIA/COMUNICACION": "Tecnologia",
    "TECNOLOGÍA/SEMICONDUCTORES": "Tecnologia",
    "TELECOMUNICACIONES (COMMUNICATION SERVICES)": "Servicios de Comunicacion",
    "COMMUNICATION SERVICES": "Servicios de Comunicacion",
    "MEDIOS": "Servicios de Comunicacion",
}


def _sector_amplio(sector_raw):
    if not sector_raw:
        return None
    bruto = re.split(r"\s[-/]\s", sector_raw, maxsplit=1)[0].strip()
    return _SECTOR_AMPLIO_SINONIMOS.get(bruto.upper(), bruto)


def _peers_navegacion(datos, ticker_actual, key_fn):
    """Devuelve (anterior, siguiente, pares, indice) del mismo grupo (según
    key_fn) que ticker_actual, ordenados por ticker, para la navegación
    de "activos similares" en la ficha detallada."""
    grupo_val = next((key_fn(e) for e in datos if e["ticker"] == ticker_actual), None)
    if not grupo_val:
        return None, None, [], None
    pares = sorted((e for e in datos if key_fn(e) == grupo_val), key=lambda e: e["ticker"])
    idx = next((i for i, e in enumerate(pares) if e["ticker"] == ticker_actual), None)
    if idx is None:
        return None, None, pares, None
    anterior = pares[idx - 1] if idx > 0 else None
    siguiente = pares[idx + 1] if idx < len(pares) - 1 else None
    return anterior, siguiente, pares, idx


def _barra_navegacion_ficha(anterior, siguiente, pares, idx, grupo_label, key_prefix):
    nav1, nav2 = st.columns([1.4, 3.6])
    with nav1:
        if st.button("← Volver al inicio", key=f"{key_prefix}_volver_inicio", use_container_width=True, type="primary"):
            st.session_state.ticker_click = None
            st.rerun()
    with nav2:
        if pares and idx is not None:
            st.caption(f"Competencia · {grupo_label} · {idx + 1} de {len(pares)}")

    if anterior or siguiente:
        pcol1, pcol2 = st.columns(2)
        with pcol1:
            if anterior:
                if st.button(
                    f"◀ {anterior['ticker']} · {(anterior.get('empresa') or anterior.get('nombre') or '')[:28]}",
                    key=f"{key_prefix}_peer_prev", use_container_width=True,
                ):
                    st.session_state.ticker_click = anterior["ticker"]
                    st.rerun()
        with pcol2:
            if siguiente:
                if st.button(
                    f"{(siguiente.get('empresa') or siguiente.get('nombre') or '')[:28]} · {siguiente['ticker']} ▶",
                    key=f"{key_prefix}_peer_next", use_container_width=True,
                ):
                    st.session_state.ticker_click = siguiente["ticker"]
                    st.rerun()

    st.markdown("---")


# ── DATOS DEL ANÁLISIS FUNDAMENTAL PROPIO (Excel) ──────────────────────────────
# Generados localmente por scripts/export_excel.py a partir del Excel de
# análisis fundamental del usuario. No se leen en vivo: son JSON estáticos
# commiteados en data/, se resincronizan corriendo el script de nuevo.

@st.cache_data(show_spinner=False)
def cargar_datos_excel():
    path = DATA_DIR / "ranking.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def cargar_ficha_excel(ticker: str):
    path = DATA_DIR / "companies" / f"{ticker}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── DATOS DEL ANÁLISIS FUNDAMENTAL PROPIO DE ETFs (Excel) ──────────────────────
# Generados localmente por scripts/export_excel_etfs.py. Mismo mecanismo que
# los de acciones, pero sin DCF/WACC: valoracion via Costo Total Real y
# percentil historico en vez de Margen de Seguridad.

@st.cache_data(show_spinner=False)
def cargar_datos_etfs():
    path = DATA_DIR / "etfs_ranking.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def cargar_ficha_etf(ticker: str):
    path = DATA_DIR / "etfs" / f"{ticker}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── BUSCADOR (acciones + ETFs, sobre los datos de Mi Análisis) ─────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _indice_busqueda():
    idx = []
    for e in cargar_datos_excel():
        idx.append(("acciones", e["ticker"], e.get("empresa") or "", e.get("sector") or ""))
    for e in cargar_datos_etfs():
        idx.append(("etfs", e["ticker"], e.get("nombre") or "", e.get("categoria") or ""))
    return idx


def buscar_activo(query: str):
    if not query or len(query.strip()) < 1:
        return []
    q = query.strip().upper()
    resultados = []
    for modo, ticker, nombre, tag in _indice_busqueda():
        if q in ticker.upper() or q in nombre.upper():
            etiqueta_modo = "Acción" if modo == "acciones" else "ETF"
            label = f"{ticker} — {nombre}  ({etiqueta_modo})" if nombre else f"{ticker}  ({etiqueta_modo})"
            resultados.append((label, f"{modo}|{ticker}"))
    resultados.sort(key=lambda r: (not r[1].split("|", 1)[1].upper().startswith(q), r[0]))
    return resultados[:15]


# ── ANÁLISIS FUNDAMENTAL PROPIO (Excel) ─────────────────────────────────────────

def _fmt_pct_directo(val):
    """A diferencia de fmt_pct() (piensa en fracciones tipo 0.15 de yfinance),
    los campos porcentuales de data/ranking.json ya vienen normalizados a
    puntos porcentuales (71.07 = 71.07%) por scripts/export_excel.py."""
    if val is None:
        return "N/D"
    try:
        return f"{round(float(val), 1)}%"
    except (TypeError, ValueError):
        return "N/D"


def _banda_valoracion(mos):
    if mos is None:
        return "sin_dato"
    if mos >= 15:
        return "infravalorada"
    if mos <= -15:
        return "sobrevalorada"
    return "razonable"


def _rating_emoji(rating):
    if rating is None:
        return "⚪"
    if rating <= 2:
        return "🔴"
    if rating < 4:
        return "🟡"
    return "🟢"


def _score_color(score):
    if score is None:
        return "#64748b"
    if score >= 4:
        return "#2ea87e"
    if score >= 3:
        return "#b07d2a"
    return "#c0392b"


def _mostrar_analisis_fundamental():
    st.markdown("---")

    datos = cargar_datos_excel()
    if not datos:
        st.warning(
            "No se encontraron datos del análisis fundamental propio "
            "(falta `data/ranking.json`). Corré `scripts/export_excel.py` "
            "sobre el Excel y volvé a desplegar."
        )
        return

    sectores_disponibles = sorted({e["sector"] for e in datos if e.get("sector")})
    badges_disponibles = sorted({e["decision_badge"] for e in datos if e.get("decision_badge")})

    fcol1, fcol2, fcol3 = st.columns([1.3, 1.3, 1.6])
    with fcol1:
        f_val = st.selectbox(
            "Valoración (Margen de Seguridad)",
            ["Todas", "💎 Infravalorada (MoS ≥ +15%)", "⚖️ Rango razonable (-15% a +15%)",
             "🔺 Sobrevalorada (MoS ≤ -15%)", "❓ Sin dato de valoración"],
            key="fx_val",
        )
    with fcol2:
        f_sector = st.multiselect(
            "Sector", options=sectores_disponibles, default=[],
            placeholder="Todos los sectores", key="fx_sector",
        )
    with fcol3:
        f_decision = st.multiselect(
            "Decisión", options=badges_disponibles, default=[],
            placeholder="Todas las decisiones", key="fx_decision",
        )

    _VAL_MAP = {
        "Todas": None,
        "💎 Infravalorada (MoS ≥ +15%)": "infravalorada",
        "⚖️ Rango razonable (-15% a +15%)": "razonable",
        "🔺 Sobrevalorada (MoS ≤ -15%)": "sobrevalorada",
        "❓ Sin dato de valoración": "sin_dato",
    }
    banda_filtro = _VAL_MAP[f_val]

    filtrados = [
        e for e in datos
        if (banda_filtro is None or _banda_valoracion(e.get("margen_seguridad_pct")) == banda_filtro)
        and (not f_sector or e.get("sector") in f_sector)
        and (not f_decision or e.get("decision_badge") in f_decision)
    ]

    conteo_txt = f"{len(filtrados)} de {len(datos)} empresas" if len(filtrados) != len(datos) else f"{len(datos)} empresas"
    if not filtrados:
        st.info("Ninguna empresa cumple los filtros seleccionados.")
        return

    st.markdown("---")
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:6px">'
        f'<span style="font-size:20px;font-weight:700;color:#111827">🧭 Mi Análisis Fundamental</span>'
        f'<span style="font-size:13px;color:#94a3b8">{conteo_txt} · basado en tu propio DCF, no en datos en vivo</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.caption("Clasificadas por Margen de Seguridad (precio actual vs. valor intrínseco de tu DCF).")

    _BANDAS_VAL = [
        ("infravalorada",  "#2ea87e", "💎 INFRAVALORADA",      "Margen de Seguridad ≥ +15%"),
        ("razonable",      "#b07d2a", "⚖️ RANGO RAZONABLE",    "Margen de Seguridad entre -15% y +15%"),
        ("sobrevalorada",  "#c0392b", "🔺 SOBREVALORADA",      "Margen de Seguridad ≤ -15%"),
        ("sin_dato",       "#64748b", "❓ SIN DATO DE VALORACIÓN", "Especulativas, situaciones especiales u otras sin DCF"),
    ]

    for clave, color, etiqueta, descripcion in _BANDAS_VAL:
        empresas = [e for e in filtrados if _banda_valoracion(e.get("margen_seguridad_pct")) == clave]
        if not empresas:
            continue
        empresas = sorted(
            empresas,
            key=lambda e: (e.get("margen_seguridad_pct") is None, -(e.get("margen_seguridad_pct") or 0)),
        )

        st.markdown(
            f'<div style="background:{color}1a;border-left:4px solid {color};'
            f'border-radius:0 8px 8px 0;padding:10px 18px;margin:24px 0 14px">'
            f'<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">'
            f'<span style="color:{color};font-weight:700;font-size:15px">{etiqueta}</span>'
            f'<span style="color:#94a3b8;font-size:12px">· {len(empresas)} empresa{"s" if len(empresas) != 1 else ""}</span>'
            f'<span style="color:#64748b;font-size:11.5px;margin-left:6px">{descripcion}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        cols_n = 5
        for i in range(0, len(empresas), cols_n):
            grupo = empresas[i: i + cols_n]
            cols = st.columns(cols_n)
            for j, emp in enumerate(grupo):
                mos = emp.get("margen_seguridad_pct")
                mos_str = "N/D" if mos is None else f'{"+" if mos >= 0 else ""}{mos:.1f}%{" ≈" if emp.get("mos_approx") else ""}'
                mos_color = "#64748b" if mos is None else ("#2ea87e" if mos >= 0 else "#c0392b")
                score = emp.get("score_total")
                score_str = f"{score:.2f}" if score is not None else "N/D"

                with cols[j]:
                    st.markdown(
                        f'<div style="background:#ffffff;border:1px solid #e2e6ee;border-bottom:none;'
                        f'border-left:3px solid {color};border-radius:6px 6px 0 0;'
                        f'padding:11px 12px 10px">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center">'
                        f'<span style="font-weight:700;color:#111827;font-size:15px">{emp["ticker"]}</span>'
                        f'<span style="background:{_score_color(score)};color:#fff;font-size:12px;font-weight:700;'
                        f'border-radius:4px;padding:2px 7px">{score_str}</span>'
                        f'</div>'
                        f'<div style="font-size:11px;color:#4b5563;margin-top:3px;white-space:nowrap;'
                        f'overflow:hidden;text-overflow:ellipsis" title="{emp.get("empresa", "")}">{emp.get("empresa", "")}</div>'
                        f'<div style="font-size:10.5px;color:#94a3b8;margin-top:2px;white-space:nowrap;'
                        f'overflow:hidden;text-overflow:ellipsis">{emp.get("sector", "")}</div>'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-top:9px">'
                        f'<span style="font-size:12px;font-weight:700;color:{mos_color}">{mos_str}</span>'
                        f'<span style="font-size:10px;color:#4b5563;text-align:right;max-width:60%;'
                        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{emp.get("decision_badge", "")}">'
                        f'{emp.get("decision_badge", "")}</span>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("Ver ficha →", key=f"fx_{emp['ticker']}", use_container_width=True):
                        st.session_state.ticker_click = emp["ticker"]
                        st.rerun()

    st.markdown("---")
    st.caption("Margen de Seguridad = (Valor Intrínseco DCF − Precio Actual) / Precio Actual. \"≈\" indica un valor normalizado por heurística durante la exportación del Excel — verificar contra la Ficha si está cerca de un umbral.")


def _mostrar_detalle_excel(ticker: str):
    ficha = cargar_ficha_excel(ticker)
    datos_excel = cargar_datos_excel()
    emp = next((e for e in datos_excel if e["ticker"] == ticker), None)

    if not ficha or not emp:
        st.error(f"No se encontró el análisis de **{ticker}** en tus datos.")
        if st.button("← Volver al inicio"):
            st.session_state.ticker_click = None
            st.rerun()
        return

    anterior, siguiente, pares, idx = _peers_navegacion(
        datos_excel, ticker, lambda e: _sector_amplio(e.get("sector"))
    )
    _barra_navegacion_ficha(anterior, siguiente, pares, idx, _sector_amplio(emp.get("sector")) or "", "excel")

    score = emp.get("score_total")
    mos = emp.get("margen_seguridad_pct")
    mos_str = "N/D" if mos is None else f'{"+" if mos >= 0 else ""}{mos:.1f}%{" ≈" if emp.get("mos_approx") else ""}'
    mos_color = "#64748b" if mos is None else ("#2ea87e" if mos >= 0 else "#c0392b")
    tesis = (ficha.get("conclusion") or {}).get("tesis") or emp.get("decision_full") or ""

    st.markdown(
        f'<div style="background:#ffffff;border:1px solid #e2e6ee;border-radius:12px;padding:20px 24px;margin-bottom:18px">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">'
        f'<div>'
        f'<div style="font-size:24px;font-weight:700;color:#111827">{emp.get("ticker")} '
        f'<span style="font-size:15px;font-weight:400;color:#4b5563">· {emp.get("empresa", "")}</span></div>'
        f'<div style="font-size:12.5px;color:#94a3b8;margin-top:4px">{emp.get("sector", "")} · Análisis del {emp.get("fecha_analisis", "N/D")}</div>'
        f'</div>'
        f'<div style="display:flex;gap:8px">'
        f'<span style="background:{_score_color(score)};color:#fff;font-weight:700;font-size:14px;border-radius:6px;padding:5px 12px">'
        f'Score {score:.2f}/5</span>'
        f'<span style="background:#f4f6fa;border:1px solid #e2e6ee;color:#374151;font-weight:700;font-size:13px;'
        f'border-radius:6px;padding:5px 12px">{emp.get("decision_badge", "")}</span>'
        f'</div>'
        f'</div>'
        f'<p style="margin:14px 0 0;font-size:13.5px;color:#374151;line-height:1.5">{tesis}</p>'
        f'<div style="display:flex;gap:24px;margin-top:16px;flex-wrap:wrap">'
        f'<div><div style="font-size:10.5px;color:#4b5563;text-transform:uppercase">Precio Actual</div>'
        f'<div style="font-size:17px;font-weight:700;color:#111827">${fmt(emp.get("precio_actual"))}</div></div>'
        f'<div><div style="font-size:10.5px;color:#4b5563;text-transform:uppercase">Valor Intrínseco (DCF)</div>'
        f'<div style="font-size:17px;font-weight:700;color:#111827">${fmt(emp.get("valor_intrinseco"))}</div></div>'
        f'<div><div style="font-size:10.5px;color:#4b5563;text-transform:uppercase">Margen de Seguridad</div>'
        f'<div style="font-size:17px;font-weight:700;color:{mos_color}">{mos_str}</div></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.link_button("📡 Ver cotización en vivo en Yahoo Finance →", f"https://finance.yahoo.com/quote/{ticker}")

    st.markdown("#### Métricas clave del Dashboard")
    _m_cards = [
        ("P/E", fmt(emp.get("pe"))),
        ("EV/EBITDA", fmt(emp.get("ev_ebitda"))),
        ("P/FCF", fmt(emp.get("p_fcf"))),
        ("Deuda Neta/EBITDA", fmt(emp.get("deuda_neta_ebitda"))),
        ("Margen Bruto", _fmt_pct_directo(emp.get("margen_bruto"))),
        ("Margen Operativo", _fmt_pct_directo(emp.get("margen_operativo"))),
        ("Margen Neto", _fmt_pct_directo(emp.get("margen_neto"))),
        ("ROE", _fmt_pct_directo(emp.get("roe"))),
        ("ROIC", _fmt_pct_directo(emp.get("roic"))),
        ("CAGR Ingresos 5y", _fmt_pct_directo(emp.get("cagr_ingresos_5y"))),
        ("FCF Yield", _fmt_pct_directo(emp.get("fcf_yield"))),
        ("Razón Corriente", fmt(emp.get("razon_corriente"))),
    ]
    for i in range(0, len(_m_cards), 4):
        cols = st.columns(4)
        for j, (lbl, val) in enumerate(_m_cards[i:i + 4]):
            with cols[j]:
                st.markdown(card(lbl, val), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### Ficha detallada — 10 secciones del análisis")

    secciones = ficha.get("secciones", [])
    if secciones:
        tab_labels = [s["titulo"] for s in secciones]
        tabs = st.tabs(tab_labels)
        for tab, sec in zip(tabs, secciones):
            with tab:
                avg = sec.get("rating_promedio")
                if avg is not None:
                    st.markdown(
                        f'<div style="display:inline-block;background:{_score_color(avg)};color:#fff;'
                        f'font-weight:700;font-size:13px;border-radius:6px;padding:4px 10px;margin-bottom:14px">'
                        f'Promedio de la sección: {avg}/5</div>',
                        unsafe_allow_html=True,
                    )
                for asp in sec.get("aspectos", []):
                    rating = asp.get("calificacion")
                    label = f'{_rating_emoji(rating)} {asp["aspecto"]}  ({rating if rating is not None else "N/D"}/5)'
                    with st.expander(label):
                        st.write(asp.get("notas") or "Sin notas registradas.")
    else:
        st.info("Esta empresa no tiene secciones de Ficha detallada registradas.")


# ── ANÁLISIS FUNDAMENTAL PROPIO DE ETFs (Excel) ─────────────────────────────────
# Mismo formato que _mostrar_analisis_fundamental() / _mostrar_detalle_excel(),
# pero sin DCF/WACC: se agrupa por postura de portafolio (decision_badge) en
# vez de por Margen de Seguridad, y las tarjetas muestran métricas de ETF
# (AUM, TER, rendimiento, riesgo) en vez de márgenes/ROE/DCF.

_BANDAS_ETF = [
    ("MANTENER",         "#2ea87e", "✅ MANTENER / ACUMULAR",  "Postura de portafolio: continuar o sumar gradualmente"),
    ("ESPERAR ENTRADA",  "#b07d2a", "⏳ ESPERAR MEJOR ENTRADA", "Fundamentos ok, pero la valoración actual no es el punto de entrada ideal"),
    ("SATÉLITE TÁCTICO", "#6b5ecd", "🛰️ SATÉLITE TÁCTICO",    "Solo como posición táctica pequeña, no como core del portafolio"),
    ("REDUCIR/VENDER",   "#c0392b", "🔻 REDUCIR / VENDER",     "Señales para reducir exposición o salir de la posición"),
    ("NO APTO",          "#7c2d3a", "⛔ NO APTO",              "Riesgo estructural (decay, apalancamiento, etc.) descarta el ETF para el core"),
    ("SIN CLASIFICAR",   "#64748b", "❓ SIN CLASIFICAR",       "Decisión no clasificada automáticamente"),
]


def _fmt_aum(v):
    if v is None:
        return "N/D"
    try:
        return f"${round(float(v), 1)}B"
    except (TypeError, ValueError):
        return "N/D"


def _mostrar_analisis_fundamental_etfs():
    st.markdown("---")

    datos = cargar_datos_etfs()
    if not datos:
        st.warning(
            "No se encontraron datos del análisis fundamental de ETFs "
            "(falta `data/etfs_ranking.json`). Corré `scripts/export_excel_etfs.py` "
            "sobre el Excel y volvé a desplegar."
        )
        return

    categorias_disponibles = sorted({e["categoria"] for e in datos if e.get("categoria")})
    emisores_disponibles = sorted({e["emisor"] for e in datos if e.get("emisor")})

    fcol1, fcol2, fcol3 = st.columns([1.3, 1.3, 1.6])
    with fcol1:
        f_postura = st.selectbox(
            "Postura",
            ["Todas"] + [b[0] for b in _BANDAS_ETF],
            key="fx_etf_postura",
        )
    with fcol2:
        f_categoria = st.multiselect(
            "Categoría", options=categorias_disponibles, default=[],
            placeholder="Todas las categorías", key="fx_etf_categoria",
        )
    with fcol3:
        f_emisor = st.multiselect(
            "Emisor", options=emisores_disponibles, default=[],
            placeholder="Todos los emisores", key="fx_etf_emisor",
        )

    filtrados = [
        e for e in datos
        if (f_postura == "Todas" or e.get("decision_badge") == f_postura)
        and (not f_categoria or e.get("categoria") in f_categoria)
        and (not f_emisor or e.get("emisor") in f_emisor)
    ]

    conteo_txt = f"{len(filtrados)} de {len(datos)} ETFs" if len(filtrados) != len(datos) else f"{len(datos)} ETFs"
    if not filtrados:
        st.info("Ningún ETF cumple los filtros seleccionados.")
        return

    st.markdown("---")
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:6px">'
        f'<span style="font-size:20px;font-weight:700;color:#111827">🧭 Mi Análisis de ETFs</span>'
        f'<span style="font-size:13px;color:#94a3b8">{conteo_txt} · basado en tu propio análisis, no en datos en vivo</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.caption("Clasificados por postura de portafolio (sin DCF/WACC: un ETF es una canasta, no un negocio con flujos propios).")

    for clave, color, etiqueta, descripcion in _BANDAS_ETF:
        etfs = [e for e in filtrados if e.get("decision_badge") == clave]
        if not etfs:
            continue
        etfs = sorted(
            etfs,
            key=lambda e: (e.get("score_total") is None, -(e.get("score_total") or 0)),
        )

        st.markdown(
            f'<div style="background:{color}1a;border-left:4px solid {color};'
            f'border-radius:0 8px 8px 0;padding:10px 18px;margin:24px 0 14px">'
            f'<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">'
            f'<span style="color:{color};font-weight:700;font-size:15px">{etiqueta}</span>'
            f'<span style="color:#94a3b8;font-size:12px">· {len(etfs)} ETF{"s" if len(etfs) != 1 else ""}</span>'
            f'<span style="color:#64748b;font-size:11.5px;margin-left:6px">{descripcion}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        cols_n = 5
        for i in range(0, len(etfs), cols_n):
            grupo = etfs[i: i + cols_n]
            cols = st.columns(cols_n)
            for j, emp in enumerate(grupo):
                score = emp.get("score_total")
                score_str = f"{score:.2f}" if score is not None else "N/D"
                r1y = emp.get("rent_1y_pct")
                r1y_str = "N/D" if r1y is None else f'{"+" if r1y >= 0 else ""}{r1y:.1f}%'
                r1y_color = "#64748b" if r1y is None else ("#2ea87e" if r1y >= 0 else "#c0392b")

                with cols[j]:
                    st.markdown(
                        f'<div style="background:#ffffff;border:1px solid #e2e6ee;border-bottom:none;'
                        f'border-left:3px solid {color};border-radius:6px 6px 0 0;'
                        f'padding:11px 12px 10px">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center">'
                        f'<span style="font-weight:700;color:#111827;font-size:15px">{emp["ticker"]}</span>'
                        f'<span style="background:{_score_color(score)};color:#fff;font-size:12px;font-weight:700;'
                        f'border-radius:4px;padding:2px 7px">{score_str}</span>'
                        f'</div>'
                        f'<div style="font-size:11px;color:#4b5563;margin-top:3px;white-space:nowrap;'
                        f'overflow:hidden;text-overflow:ellipsis" title="{emp.get("nombre", "")}">{emp.get("nombre", "")}</div>'
                        f'<div style="font-size:10.5px;color:#94a3b8;margin-top:2px;white-space:nowrap;'
                        f'overflow:hidden;text-overflow:ellipsis">{emp.get("categoria", "")} · {emp.get("emisor", "")}</div>'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-top:9px">'
                        f'<span style="font-size:12px;font-weight:700;color:{r1y_color}">Rent. 1Y {r1y_str}</span>'
                        f'<span style="font-size:10px;color:#4b5563;text-align:right;max-width:55%;'
                        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{emp.get("decision_full", "")}">'
                        f'{_fmt_aum(emp.get("aum_b"))} AUM</span>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("Ver ficha →", key=f"fxetf_{emp['ticker']}", use_container_width=True):
                        st.session_state.ticker_click = emp["ticker"]
                        st.rerun()

    st.markdown("---")
    st.caption("Costo Total Real = TER + spread + tracking difference estimados. La postura de portafolio refleja tu propio análisis, no una recomendación genérica.")


def _mostrar_detalle_etf(ticker: str):
    ficha = cargar_ficha_etf(ticker)
    datos_etfs = cargar_datos_etfs()
    emp = next((e for e in datos_etfs if e["ticker"] == ticker), None)

    if not ficha or not emp:
        st.warning(f"No se encontró análisis propio para **{ticker}** en `data/etfs/`.")
        if st.button("← Volver al inicio"):
            st.session_state.ticker_click = None
            st.rerun()
        return

    anterior, siguiente, pares, idx = _peers_navegacion(
        datos_etfs, ticker, lambda e: e.get("categoria")
    )
    _barra_navegacion_ficha(anterior, siguiente, pares, idx, emp.get("categoria", ""), "etf")

    score = emp.get("score_total")
    score_str = f"{score:.2f}/5" if score is not None else "N/D"
    tesis = (ficha.get("conclusion") or {}).get("tesis") or emp.get("decision_full") or ""

    st.markdown(
        f'<div style="background:#ffffff;border:1px solid #e2e6ee;border-radius:12px;padding:20px 24px;margin-bottom:18px">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">'
        f'<div>'
        f'<div style="font-size:24px;font-weight:700;color:#111827">{emp.get("ticker")} '
        f'<span style="font-size:15px;font-weight:400;color:#4b5563">· {emp.get("nombre", "")}</span></div>'
        f'<div style="font-size:12.5px;color:#94a3b8;margin-top:4px">{emp.get("categoria", "")} · {emp.get("emisor", "")} · Análisis del {emp.get("fecha_analisis", "N/D")}</div>'
        f'</div>'
        f'<div style="display:flex;gap:8px">'
        f'<span style="background:{_score_color(score)};color:#fff;font-weight:700;font-size:14px;border-radius:6px;padding:5px 12px">'
        f'Score {score_str}</span>'
        f'<span style="background:#f4f6fa;border:1px solid #e2e6ee;color:#374151;font-weight:700;font-size:13px;'
        f'border-radius:6px;padding:5px 12px">{emp.get("decision_badge", "")}</span>'
        f'</div>'
        f'</div>'
        f'<p style="margin:14px 0 0;font-size:13.5px;color:#374151;line-height:1.5">{tesis}</p>'
        f'<div style="display:flex;gap:24px;margin-top:16px;flex-wrap:wrap">'
        f'<div><div style="font-size:10.5px;color:#4b5563;text-transform:uppercase">AUM</div>'
        f'<div style="font-size:17px;font-weight:700;color:#111827">{_fmt_aum(emp.get("aum_b"))}</div></div>'
        f'<div><div style="font-size:10.5px;color:#4b5563;text-transform:uppercase">Expense Ratio (TER)</div>'
        f'<div style="font-size:17px;font-weight:700;color:#111827">{_fmt_pct_directo(emp.get("ter_pct"))}</div></div>'
        f'<div><div style="font-size:10.5px;color:#4b5563;text-transform:uppercase">Dividend Yield</div>'
        f'<div style="font-size:17px;font-weight:700;color:#111827">{_fmt_pct_directo(emp.get("dividend_yield_pct"))}</div></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.link_button("📡 Ver cotización en vivo en Yahoo Finance →", f"https://finance.yahoo.com/quote/{ticker}")

    st.markdown("#### Métricas clave del ETF")
    _m_cards = [
        ("AUM", _fmt_aum(emp.get("aum_b"))),
        ("Expense Ratio (TER)", _fmt_pct_directo(emp.get("ter_pct"))),
        ("Costo Total Real Est.", _fmt_pct_directo(emp.get("costo_total_real_pct"))),
        ("Dividend Yield", _fmt_pct_directo(emp.get("dividend_yield_pct"))),
        ("Rent. 1 año", _fmt_pct_directo(emp.get("rent_1y_pct"))),
        ("Rent. 5 años (anual.)", _fmt_pct_directo(emp.get("rent_5y_pct"))),
        ("Rent. 10Y/Incepción (anual.)", _fmt_pct_directo(emp.get("rent_10y_pct"))),
        ("Volatilidad anualizada", _fmt_pct_directo(emp.get("volatilidad_pct"))),
        ("Máx. Drawdown", _fmt_pct_directo(emp.get("max_drawdown_pct"))),
        ("Sharpe Ratio", fmt(emp.get("sharpe_ratio"))),
        ("Beta vs S&P 500", fmt(emp.get("beta_sp500"))),
        ("P/E Ponderado", fmt(emp.get("pe_ponderado"))),
        ("Top 10 Holdings", _fmt_pct_directo(emp.get("top10_holdings_pct"))),
        ("N° Holdings", "N/D" if emp.get("n_holdings") is None else str(int(emp.get("n_holdings")))),
    ]
    for i in range(0, len(_m_cards), 4):
        cols = st.columns(4)
        for j, (lbl, val) in enumerate(_m_cards[i:i + 4]):
            with cols[j]:
                st.markdown(card(lbl, val), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### Ficha detallada")

    secciones = ficha.get("secciones", [])
    if secciones:
        tab_labels = [s["titulo"] for s in secciones]
        tabs = st.tabs(tab_labels)
        for tab, sec in zip(tabs, secciones):
            with tab:
                avg = sec.get("rating_promedio")
                if avg is not None:
                    st.markdown(
                        f'<div style="display:inline-block;background:{_score_color(avg)};color:#fff;'
                        f'font-weight:700;font-size:13px;border-radius:6px;padding:4px 10px;margin-bottom:14px">'
                        f'Promedio de la sección: {avg}/5</div>',
                        unsafe_allow_html=True,
                    )
                for asp in sec.get("aspectos", []):
                    rating = asp.get("calificacion")
                    label = f'{_rating_emoji(rating)} {asp["aspecto"]}  ({rating if rating is not None else "N/D"}/5)'
                    with st.expander(label):
                        st.write(asp.get("notas") or "Sin notas registradas.")
    else:
        st.info("Este ETF no tiene secciones de Ficha detallada registradas.")


# ── RANKING (basado en el score 1-5 de tu propio análisis) ─────────────────────
# Único sistema de puntuación de toda la app: el score_total que sale de tus
# Excels. "Mi Análisis" agrupa por valoración/postura; "Ranking" agrupa por
# calidad global del score, para dar dos lecturas del mismo dato, no dos
# fuentes distintas.

_BANDAS_SCORE = [
    (4.5, 5.01, "#2ea87e", "EXCELENTE", "Score ≥ 4.5"),
    (4.0, 4.5,  "#3dba90", "SÓLIDA",    "Score entre 4.0 y 4.49"),
    (3.5, 4.0,  "#8db03a", "BUENA",     "Score entre 3.5 y 3.99"),
    (3.0, 3.5,  "#b07d2a", "MODERADA",  "Score entre 3.0 y 3.49"),
    (2.5, 3.0,  "#c06030", "MIXTA",     "Score entre 2.5 y 2.99"),
    (0,   2.5,  "#c0392b", "DÉBIL",     "Score menor a 2.5"),
]


def _mostrar_ranking_excel():
    st.markdown("---")

    datos = cargar_datos_excel()
    if not datos:
        st.warning("No se encontraron datos del análisis fundamental propio (falta `data/ranking.json`).")
        return

    sectores_disponibles = sorted({e["sector"] for e in datos if e.get("sector")})

    fcol1, fcol2 = st.columns([1.3, 2.7])
    with fcol1:
        f_score = st.selectbox(
            "Score mínimo", ["Todos", "≥ 3.0", "≥ 3.5", "≥ 4.0", "≥ 4.5"], key="fr_score",
        )
    with fcol2:
        f_sector = st.multiselect(
            "Sector", options=sectores_disponibles, default=[],
            placeholder="Todos los sectores", key="fr_sector",
        )
    _min = {"Todos": 0, "≥ 3.0": 3.0, "≥ 3.5": 3.5, "≥ 4.0": 4.0, "≥ 4.5": 4.5}[f_score]

    filtrados = [
        e for e in datos
        if (e.get("score_total") or 0) >= _min
        and (not f_sector or e.get("sector") in f_sector)
    ]
    filtrados = sorted(filtrados, key=lambda e: (e.get("score_total") is None, -(e.get("score_total") or 0)))

    conteo_txt = f"{len(filtrados)} de {len(datos)} empresas" if len(filtrados) != len(datos) else f"{len(datos)} empresas"
    if not filtrados:
        st.info("Ninguna empresa cumple los filtros seleccionados.")
        return

    st.markdown("---")
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:6px">'
        f'<span style="font-size:20px;font-weight:700;color:#111827">🏆 Ranking por Score</span>'
        f'<span style="font-size:13px;color:#94a3b8">{conteo_txt} · basado en tu propio análisis (1–5)</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.caption("Ordenadas de mayor a menor score global de tu Excel.")

    for lo, hi, color, etiqueta, descripcion in _BANDAS_SCORE:
        empresas = [e for e in filtrados if e.get("score_total") is not None and lo <= e["score_total"] < hi]
        if not empresas:
            continue

        st.markdown(
            f'<div style="background:{color}1a;border-left:4px solid {color};'
            f'border-radius:0 8px 8px 0;padding:10px 18px;margin:24px 0 14px">'
            f'<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">'
            f'<span style="color:{color};font-weight:700;font-size:15px">{etiqueta}</span>'
            f'<span style="color:#4b5563;font-size:13px">{lo:.2f} – {min(hi, 5.0):.2f}</span>'
            f'<span style="color:#94a3b8;font-size:12px">· {len(empresas)} empresa{"s" if len(empresas) != 1 else ""}</span>'
            f'<span style="color:#64748b;font-size:11.5px;margin-left:6px">{descripcion}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        cols_n = 5
        for i in range(0, len(empresas), cols_n):
            grupo = empresas[i: i + cols_n]
            cols = st.columns(cols_n)
            for j, emp in enumerate(grupo):
                mos = emp.get("margen_seguridad_pct")
                mos_str = "N/D" if mos is None else f'{"+" if mos >= 0 else ""}{mos:.1f}%'
                mos_color = "#64748b" if mos is None else ("#2ea87e" if mos >= 0 else "#c0392b")
                score = emp.get("score_total")

                with cols[j]:
                    st.markdown(
                        f'<div style="background:#ffffff;border:1px solid #e2e6ee;border-bottom:none;'
                        f'border-left:3px solid {color};border-radius:6px 6px 0 0;'
                        f'padding:11px 12px 10px">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center">'
                        f'<span style="font-weight:700;color:#111827;font-size:15px">{emp["ticker"]}</span>'
                        f'<span style="background:{color};color:#fff;font-size:12px;font-weight:700;'
                        f'border-radius:4px;padding:2px 7px">{score:.2f}</span>'
                        f'</div>'
                        f'<div style="font-size:11px;color:#4b5563;margin-top:3px;white-space:nowrap;'
                        f'overflow:hidden;text-overflow:ellipsis" title="{emp.get("empresa", "")}">{emp.get("empresa", "")}</div>'
                        f'<div style="font-size:10.5px;color:#94a3b8;margin-top:2px">{emp.get("sector", "")}</div>'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-top:9px">'
                        f'<span style="font-size:12px;font-weight:700;color:{mos_color}">MoS {mos_str}</span>'
                        f'<span style="font-size:10px;color:#4b5563;text-align:right;max-width:55%;'
                        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{emp.get("decision_badge", "")}">'
                        f'{emp.get("decision_badge", "")}</span>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("Ver ficha →", key=f"rk_{emp['ticker']}", use_container_width=True):
                        st.session_state.ticker_click = emp["ticker"]
                        st.rerun()

    st.markdown("---")
    st.caption("El score y el Margen de Seguridad (MoS) provienen de tu propio análisis en Excel.")


def _mostrar_ranking_etfs():
    st.markdown("---")

    datos = cargar_datos_etfs()
    if not datos:
        st.warning("No se encontraron datos del análisis de ETFs (falta `data/etfs_ranking.json`).")
        return

    categorias_disponibles = sorted({e["categoria"] for e in datos if e.get("categoria")})

    fcol1, fcol2 = st.columns([1.3, 2.7])
    with fcol1:
        f_score = st.selectbox(
            "Score mínimo", ["Todos", "≥ 3.0", "≥ 3.5", "≥ 4.0", "≥ 4.5"], key="fretf_score",
        )
    with fcol2:
        f_categoria = st.multiselect(
            "Categoría", options=categorias_disponibles, default=[],
            placeholder="Todas las categorías", key="fretf_categoria",
        )
    _min = {"Todos": 0, "≥ 3.0": 3.0, "≥ 3.5": 3.5, "≥ 4.0": 4.0, "≥ 4.5": 4.5}[f_score]

    filtrados = [
        e for e in datos
        if (e.get("score_total") or 0) >= _min
        and (not f_categoria or e.get("categoria") in f_categoria)
    ]
    filtrados = sorted(filtrados, key=lambda e: (e.get("score_total") is None, -(e.get("score_total") or 0)))

    conteo_txt = f"{len(filtrados)} de {len(datos)} ETFs" if len(filtrados) != len(datos) else f"{len(datos)} ETFs"
    if not filtrados:
        st.info("Ningún ETF cumple los filtros seleccionados.")
        return

    st.markdown("---")
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:6px">'
        f'<span style="font-size:20px;font-weight:700;color:#111827">🏆 Ranking de ETFs por Score</span>'
        f'<span style="font-size:13px;color:#94a3b8">{conteo_txt} · basado en tu propio análisis (1–5)</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.caption("Ordenados de mayor a menor score global de tu Excel.")

    for lo, hi, color, etiqueta, descripcion in _BANDAS_SCORE:
        etfs = [e for e in filtrados if e.get("score_total") is not None and lo <= e["score_total"] < hi]
        if not etfs:
            continue

        st.markdown(
            f'<div style="background:{color}1a;border-left:4px solid {color};'
            f'border-radius:0 8px 8px 0;padding:10px 18px;margin:24px 0 14px">'
            f'<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">'
            f'<span style="color:{color};font-weight:700;font-size:15px">{etiqueta}</span>'
            f'<span style="color:#4b5563;font-size:13px">{lo:.2f} – {min(hi, 5.0):.2f}</span>'
            f'<span style="color:#94a3b8;font-size:12px">· {len(etfs)} ETF{"s" if len(etfs) != 1 else ""}</span>'
            f'<span style="color:#64748b;font-size:11.5px;margin-left:6px">{descripcion}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        cols_n = 5
        for i in range(0, len(etfs), cols_n):
            grupo = etfs[i: i + cols_n]
            cols = st.columns(cols_n)
            for j, emp in enumerate(grupo):
                r1y = emp.get("rent_1y_pct")
                r1y_str = "N/D" if r1y is None else f'{"+" if r1y >= 0 else ""}{r1y:.1f}%'
                r1y_color = "#64748b" if r1y is None else ("#2ea87e" if r1y >= 0 else "#c0392b")
                score = emp.get("score_total")

                with cols[j]:
                    st.markdown(
                        f'<div style="background:#ffffff;border:1px solid #e2e6ee;border-bottom:none;'
                        f'border-left:3px solid {color};border-radius:6px 6px 0 0;'
                        f'padding:11px 12px 10px">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center">'
                        f'<span style="font-weight:700;color:#111827;font-size:15px">{emp["ticker"]}</span>'
                        f'<span style="background:{color};color:#fff;font-size:12px;font-weight:700;'
                        f'border-radius:4px;padding:2px 7px">{score:.2f}</span>'
                        f'</div>'
                        f'<div style="font-size:11px;color:#4b5563;margin-top:3px;white-space:nowrap;'
                        f'overflow:hidden;text-overflow:ellipsis" title="{emp.get("nombre", "")}">{emp.get("nombre", "")}</div>'
                        f'<div style="font-size:10.5px;color:#94a3b8;margin-top:2px">{emp.get("categoria", "")}</div>'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-top:9px">'
                        f'<span style="font-size:12px;font-weight:700;color:{r1y_color}">Rent. 1Y {r1y_str}</span>'
                        f'<span style="font-size:10px;color:#4b5563;text-align:right;max-width:55%;'
                        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{emp.get("decision_full", "")}">'
                        f'{_fmt_aum(emp.get("aum_b"))} AUM</span>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("Ver ficha →", key=f"rketf_{emp['ticker']}", use_container_width=True):
                        st.session_state.ticker_click = emp["ticker"]
                        st.rerun()

    st.markdown("---")
    st.caption("El score y las métricas provienen de tu propio análisis en Excel.")


# ── SIDEBAR ──────────────────────────────────────────────────────────────────
_SECCIONES_ACCIONES = [
    "1. Modelo de Negocio y Ventaja Competitiva",
    "2. Calidad del Management y Gobierno Corporativo",
    "3. Salud Financiera (Balance General)",
    "4. Rentabilidad y Eficiencia",
    "5. Crecimiento",
    "6. Generación y Uso de Flujo de Caja",
    "7. Valoración",
    "8. Industria y Entorno Competitivo",
    "9. Riesgos",
    "10. Catalizadores y Sentimiento",
]
_SECCIONES_ETFS = [
    "A. Estructura y Mecánica del ETF",
    "B. Costos",
    "C. Liquidez y Ejecución",
    "D. Composición y Concentración",
    "E. Riesgo / Retorno Histórico",
    "F. Valoración Agregada",
    "G. Cualitativo / Tesis",
]

with st.sidebar:
    # Título clicable → vuelve a la pantalla principal
    if st.button("📊 Analizador de Bolsa", key="btn_home", use_container_width=True):
        st.session_state.ticker_click = None
        for k in [k for k in st.session_state if k.startswith("buscador_activo")]:
            del st.session_state[k]
        st.rerun()
    st.caption("Análisis fundamental · mediano y largo plazo")
    st.markdown("---")

    ticker_buscado = st_searchbox(
        buscar_activo,
        placeholder="Ticker o nombre (acción o ETF)...",
        label="Buscar en Mi Análisis",
        key="buscador_activo",
        default=None,
        clear_on_submit=True,
    )
    if ticker_buscado:
        _modo_busq, _tk_busq = ticker_buscado.split("|", 1)
        st.session_state.modo = _modo_busq
        st.session_state["modo_selector"] = "📊 Acciones" if _modo_busq == "acciones" else "📦 ETFs"
        st.session_state.ticker_click = _tk_busq
        st.rerun()
    st.markdown("---")

    st.markdown("**Modo**")
    _modo_label = st.segmented_control(
        "Modo de análisis",
        options=["📊 Acciones", "📦 ETFs"],
        default="📊 Acciones" if st.session_state.modo == "acciones" else "📦 ETFs",
        key="modo_selector",
        label_visibility="collapsed",
    )
    _nuevo_modo = "acciones" if _modo_label == "📊 Acciones" else "etfs"
    if _nuevo_modo != st.session_state.modo:
        st.session_state.modo = _nuevo_modo
        st.session_state.ticker_click = None
        st.rerun()

    st.markdown("---")
    _secciones_sb = _SECCIONES_ACCIONES if st.session_state.modo == "acciones" else _SECCIONES_ETFS
    st.markdown("**Aspectos evaluados en el análisis:**\n" + "\n".join(f"- {s}" for s in _secciones_sb))
    st.markdown("---")
    st.caption("Análisis 100% basado en tu propia investigación — sin datos genéricos en vivo.")

    # Botón "Volver" cuando se navegó desde una tarjeta
    if st.session_state.ticker_click:
        st.markdown("---")
        if st.button("← Volver", use_container_width=True):
            st.session_state.ticker_click = None
            st.rerun()

ticker_activo = st.session_state.ticker_click


# ── PANTALLA INICIAL ─────────────────────────────────────────────────────────
if not ticker_activo:
    _es_acciones = st.session_state.modo == "acciones"
    _titulo = "Analizador de Bolsa" if _es_acciones else "Analizador de ETFs"
    _icono = "📊" if _es_acciones else "📦"
    st.markdown(f"""
    <div style="text-align:center;padding:32px 0 10px">
        <div style="font-size:52px">{_icono}</div>
        <h2 style="color:#111827;margin-top:12px;font-size:26px;font-weight:700">{_titulo}</h2>
        <p style="font-size:15px;color:#64748b;margin-top:6px">
            Análisis fundamental · mediano y largo plazo
        </p>
    </div>
    """, unsafe_allow_html=True)

    home_tab0, home_tab1 = st.tabs(["📊 Análisis Fundamental", "📈 Ranking"])
    with home_tab0:
        if _es_acciones:
            _mostrar_analisis_fundamental()
        else:
            _mostrar_analisis_fundamental_etfs()
    with home_tab1:
        if _es_acciones:
            _mostrar_ranking_excel()
        else:
            _mostrar_ranking_etfs()
    st.stop()


# ── FICHA DETALLADA ──────────────────────────────────────────────────────────
if st.session_state.modo == "acciones":
    _mostrar_detalle_excel(ticker_activo.strip().upper())
else:
    _mostrar_detalle_etf(ticker_activo.strip().upper())
st.stop()
