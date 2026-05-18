import streamlit as st
import yfinance as yf
import pandas as pd
from streamlit_searchbox import st_searchbox
from deep_translator import GoogleTranslator
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="Analizador de Bolsa",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        <h2 style="color:#e6f1ff;margin:12px 0 4px;font-size:22px">Analizador de Bolsa</h2>
        <p style="color:#8892b0;font-size:14px;margin-bottom:28px">Acceso restringido</p>
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

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"], .main, section.main {
    background-color: #0d1117 !important;
}
[data-testid="stHeader"] { display: none !important; }
[data-testid="stSidebar"] {
    background-color: #0d1117 !important;
    border-right: 1px solid #21262d;
}
.block-container { padding-top: 1.8rem !important; padding-bottom: 2rem !important; }

.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #161b2e;
    padding: 6px;
    border-radius: 10px;
    border: 1px solid #21262d;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 7px;
    padding: 7px 16px;
    color: #8b949e !important;
    font-weight: 600;
    font-size: 13px;
    border: none !important;
}
.stTabs [aria-selected="true"] {
    background: #21262d !important;
    color: #e6f1ff !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top: 20px; }

/* Las tarjetas usan estilos inline — sin clases .card-* */

div[data-testid="stExpander"] {
    background: #161b2e !important;
    border: 1px solid #21262d !important;
    border-radius: 10px !important;
}
hr { border-color: #21262d !important; margin: 1.2rem 0 !important; }
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
[data-testid="stToolbar"] { display: none !important; }

/* ── Botón título "Analizador de Bolsa" en el sidebar ── */
[data-testid="stSidebar"] .stButton:first-child > button {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #e6f1ff !important;
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
</style>
""", unsafe_allow_html=True)


# ── HELPERS ──────────────────────────────────────────────────────────────────

def fmt(val, decimals=2):
    if val is None:
        return "N/D"
    try:
        return f"{round(float(val), decimals)}"
    except:
        return "N/D"


def fmt_pct(val):
    if val is None:
        return "N/D"
    try:
        return f"{round(float(val) * 100, 1)}%"
    except:
        return "N/D"


def fmt_large(val):
    if val is None:
        return "N/D"
    try:
        v = float(val)
        if v >= 1e12:  return f"${v/1e12:.2f}T"
        elif v >= 1e9: return f"${v/1e9:.2f}B"
        elif v >= 1e6: return f"${v/1e6:.2f}M"
        return f"${v:,.0f}"
    except:
        return "N/D"


def semaforo(val, bueno, malo, menor_es_mejor=False):
    NEUTRO = (None,         "#3d4555")
    BUENO  = ("▲ Bueno",   "#2ea87e")
    MEDIO  = ("● Moderado","#b07d2a")
    MALO_M = ("▼ Elevado", "#c0392b")
    MALO_B = ("▼ Bajo",    "#c0392b")
    if val is None:
        return NEUTRO
    try:
        v = float(val)
        if menor_es_mejor:
            if v <= bueno:  return BUENO
            elif v >= malo: return MALO_M
            else:           return MEDIO
        else:
            if v >= bueno:  return BUENO
            elif v <= malo: return MALO_B
            else:           return MEDIO
    except:
        return NEUTRO


def _parse_rango(rango: str):
    """Convierte '25 – 40' o '20% – 40%' en (bajo, alto) como decimales si tiene %."""
    try:
        es_pct = "%" in rango
        partes = rango.replace("%", "").split("–")
        bajo = float(partes[0].strip())
        alto = float(partes[1].strip())
        if es_pct:
            bajo /= 100
            alto /= 100
        return bajo, alto
    except:
        return None, None


# Umbrales globales de respaldo cuando no hay dato de sector
_DEFAULTS = {
    "pe_t":  (15, 30, True),   "pe_f":  (15, 25, True),
    "peg":   (1,  2,  True),   "pb":    (1,  5,  True),
    "ps":    (2,  8,  True),   "ev_e":  (10, 20, True),
    "gm":    (0.40, 0.20, False), "om": (0.15, 0.05, False),
    "nm":    (0.10, 0.03, False), "roe": (0.15, 0.05, False),
    "roa":   (0.05, 0.02, False), "cr":  (1.5, 1.0, False),
    "qr":    (1.0, 0.5, False),   "de":  (50, 150, True),
    "div_y": (0.03, 0.005, False),"payout": (0.75, 1.0, True),
    "rev_g": (0.10, 0.0, False),  "earn_g": (0.10, 0.0, False),
    "eps_chg":(0.10, 0.0, False), "upside": (15, 0, False),
}


def semaforo_sector(val, sector: str, key: str):
    """
    Clasifica el indicador usando el rango típico del sector como referencia.
    - Por debajo del rango → Bueno (métricas donde menor es mejor) o Bajo (si mayor es mejor)
    - Dentro del rango    → Moderado
    - Por encima del rango→ Elevado (menor es mejor) o Bueno (mayor es mejor)
    """
    menor = key in {"pe_t", "pe_f", "peg", "pb", "ps", "ev_e", "de", "payout"}

    rango = _B.get(sector, {}).get(key)
    if rango and rango != "N/A":
        bajo, alto = _parse_rango(rango)
        if bajo is not None:
            return semaforo(val, bajo, alto, menor_es_mejor=menor)

    # Fallback a umbrales globales
    d = _DEFAULTS.get(key)
    if d:
        return semaforo(val, d[0], d[1], d[2])
    return (None, "#3d4555")


def interpretar(key, val):
    """Interpretación en lenguaje simple para cada indicador."""
    if val is None:
        return "Dato no disponible para este período."
    try:
        v = float(val)
    except:
        return ""

    tabla = {
        "pe_t": lambda v: (
            f"Pagas ${v:.1f} por cada $1 de ganancia anual. Precio muy atractivo." if v <= 15 else
            f"Pagas ${v:.1f} por cada $1 de ganancia anual. Valoración razonable." if v <= 30 else
            f"Pagas ${v:.1f} por cada $1 de ganancia. El mercado apuesta fuerte a su crecimiento futuro."
        ),
        "pe_f": lambda v: (
            f"Con ganancias estimadas, pagas ${v:.1f} por $1. Barato a futuro." if v <= 15 else
            f"Con ganancias estimadas, pagas ${v:.1f} por $1. Valoración normal a futuro." if v <= 25 else
            f"Con ganancias estimadas, pagas ${v:.1f} por $1. Caro incluso proyectando crecimiento."
        ),
        "peg": lambda v: (
            f"PEG {v:.2f}: barato ajustado por crecimiento. Señal de valor real." if v <= 1 else
            f"PEG {v:.2f}: valoración justa considerando el ritmo de crecimiento esperado." if v <= 2 else
            f"PEG {v:.2f}: caro incluso ajustando por el crecimiento proyectado por analistas."
        ),
        "pb": lambda v: (
            f"Cotiza a {v:.1f}x su valor contable. Por debajo del valor real de sus activos." if v <= 1 else
            f"Paga {v:.1f}x el valor en libros. Prima normal para una empresa rentable." if v <= 5 else
            f"Paga {v:.1f}x su valor contable. Prima muy elevada; se justifica solo con ROE alto."
        ),
        "ps": lambda v: (
            f"Pagas ${v:.1f} por cada $1 de ventas. Precio atractivo en relación a sus ingresos." if v <= 2 else
            f"Pagas ${v:.1f} por cada $1 de ventas. Nivel normal en el mercado." if v <= 8 else
            f"Pagas ${v:.1f} por cada $1 de ventas. Solo se justifica con márgenes muy altos."
        ),
        "ev_e": lambda v: (
            f"La empresa vale {v:.1f} veces su EBITDA. Valoración barata en términos absolutos." if v <= 10 else
            f"La empresa vale {v:.1f} veces su EBITDA. Rango típico del mercado." if v <= 20 else
            f"La empresa vale {v:.1f} veces su EBITDA. Múltiplo elevado; requiere fuerte crecimiento."
        ),
        "gm": lambda v: (
            f"De cada $100 vendidos, retiene ${v*100:.0f} tras costos directos. Ventaja competitiva clara." if v >= 0.40 else
            f"De cada $100 vendidos, retiene ${v*100:.0f} tras costos directos. Margen aceptable." if v >= 0.20 else
            f"De cada $100 vendidos, retiene apenas ${v*100:.0f}. Márgenes muy ajustados."
        ),
        "om": lambda v: (
            f"Después de gastos operativos, le queda un {v*100:.1f}% de margen. Negocio eficiente." if v >= 0.15 else
            f"Margen operativo del {v*100:.1f}%. Aceptable aunque con margen de mejora." if v >= 0.05 else
            f"Margen operativo del {v*100:.1f}%. Gastos operativos consumen casi todo el ingreso."
        ),
        "nm": lambda v: (
            f"Por cada $100 vendidos, se queda con ${v*100:.1f} netos. Rentabilidad sólida." if v >= 0.10 else
            f"Por cada $100 vendidos, retiene ${v*100:.1f} netos. Margen neto aceptable." if v >= 0.03 else
            f"Por cada $100 vendidos, solo retiene ${v*100:.1f} netos. Margen muy ajustado."
        ),
        "roe": lambda v: (
            f"Por cada $100 de capital propio, genera ${v*100:.1f} de ganancia. Retorno excelente." if v >= 0.15 else
            f"Genera {v*100:.1f}% de retorno sobre su capital propio. Rentabilidad moderada." if v >= 0.05 else
            f"Solo genera {v*100:.1f}% sobre su capital propio. Poco eficiente para el accionista."
        ),
        "roa": lambda v: (
            f"Por cada $100 en activos, genera ${v*100:.1f} de ganancia. Uso muy eficiente." if v >= 0.05 else
            f"Genera {v*100:.1f}% de retorno sobre sus activos totales. Eficiencia moderada." if v >= 0.02 else
            f"Solo {v*100:.1f}% de retorno sobre activos. Los activos generan poco valor."
        ),
        "rev_g": lambda v: (
            f"Las ventas crecieron {v*100:.1f}% vs el año anterior. Crecimiento sólido y sostenido." if v >= 0.10 else
            f"Las ventas crecieron {v*100:.1f}% vs el año anterior. Ritmo de crecimiento moderado." if v > 0 else
            f"Las ventas cayeron {abs(v)*100:.1f}%. Revisar si es temporal o tendencia."
        ),
        "earn_g": lambda v: (
            f"Las ganancias crecieron {v*100:.1f}% vs el año anterior. Expansión de beneficios fuerte." if v >= 0.10 else
            f"Las ganancias crecieron {v*100:.1f}% vs el año anterior. Crecimiento modesto." if v > 0 else
            f"Las ganancias cayeron {abs(v)*100:.1f}%. Importante identificar si es puntual."
        ),
        "eps_chg": lambda v: (
            f"Se espera que las ganancias por acción crezcan {v*100:.1f}%. Perspectiva positiva." if v >= 0.10 else
            f"Crecimiento esperado en EPS del {v*100:.1f}%. Estimación moderada." if v > 0 else
            f"Se espera una caída del {abs(v)*100:.1f}% en EPS. Analizar las causas."
        ),
        "de": lambda v: (
            f"Por cada $100 de capital, tiene ${v:.0f} en deuda. Carga muy baja y manejable." if v <= 50 else
            f"Por cada $100 de capital, tiene ${v:.0f} en deuda. Nivel manejable en condiciones normales." if v <= 150 else
            f"Por cada $100 de capital, tiene ${v:.0f} en deuda. Alta carga; vulnerable a subidas de tasas."
        ),
        "cr": lambda v: (
            f"Tiene ${v:.2f} en activos líquidos por cada $1 de deuda a corto plazo. Muy cómodo." if v >= 1.5 else
            f"Tiene ${v:.2f} por cada $1 de deuda a corto plazo. Liquidez ajustada pero manejable." if v >= 1.0 else
            f"Tiene solo ${v:.2f} por cada $1 de deuda inmediata. Riesgo de problemas de liquidez."
        ),
        "qr": lambda v: (
            f"Sin contar inventario, cubre ${v:.2f} por cada $1 de deuda inmediata. Posición sólida." if v >= 1.0 else
            f"Sin inventario, cubre ${v:.2f} por cada $1 de deuda inmediata. Algo justo." if v >= 0.5 else
            f"Sin inventario, solo cubre ${v:.2f} por $1 de deuda. Liquidez inmediata muy baja."
        ),
        "caja_neta": lambda v: (
            f"Tiene ${abs(v)/1e9:.1f}B más de caja que deuda. Fortaleza financiera sólida." if v > 1e9 else
            f"Caja neta positiva: tiene más efectivo que deuda total. Buena señal." if v > 0 else
            f"Tiene más deuda que caja disponible. Normal en muchas industrias, pero vigilar."
        ),
        "div_y": lambda v: (
            f"Por cada $100 invertidos, recibes ${v*100:.1f} en dividendos al año. Yield atractivo." if v >= 0.03 else
            f"Por cada $100 invertidos, recibes ${v*100:.1f} en dividendos al año. Yield modesto."
        ),
        "payout": lambda v: (
            f"Distribuye el {v*100:.0f}% de sus ganancias. Sostenible con margen para crecer." if v <= 0.60 else
            f"Distribuye el {v*100:.0f}% de sus ganancias. Payout elevado; vigilar si sube más." if v <= 1.0 else
            f"Paga más dividendos de lo que gana ({v*100:.0f}%). Insostenible a largo plazo."
        ),
        "upside": lambda v: (
            f"El consenso de analistas ve un potencial de +{v:.1f}%. Lo consideran infravalorado." if v >= 15 else
            f"El consenso ve un {v:+.1f}% de potencial. Upside limitado según los analistas." if v >= 0 else
            f"El consenso anticipa una caída del {abs(v):.1f}%. Posiblemente sobrevalorado hoy."
        ),
    }

    fn = tabla.get(key)
    return fn(v) if fn else ""


def card(titulo, valor, estado=None, color="#3d4555", interpretacion=None, sector_ref=None):
    tiene_color = color not in ("#3d4555", None)
    border      = color if (estado or tiene_color) else "#21262d"
    valor_color = color if (not estado and tiene_color) else "#f0f6ff"

    # Truncar en Python: evita que CSS webkit-clamp filtre HTML crudo
    if interpretacion and len(interpretacion) > 130:
        interpretacion = interpretacion[:127] + "…"

    bloques = [
        f'<p style="margin:0 0 5px;font-size:10.5px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.9px;color:#a0aec0;width:100%">{titulo}</p>',
        f'<p style="margin:0;font-size:22px;font-weight:700;color:{valor_color};'
        f'line-height:1.2;word-break:break-word">{valor}</p>',
    ]
    if estado:
        bloques.append(
            f'<p style="margin:5px 0 0;font-size:11.5px;font-weight:700;color:{color}">{estado}</p>'
        )
    if interpretacion:
        bloques.append(
            f'<p style="margin:6px 0 0;font-size:11.5px;color:#c0cfe0;line-height:1.45;text-align:left">{interpretacion}</p>'
        )
    if sector_ref:
        bloques.append(
            f'<p style="margin:6px 0 0;font-size:10.5px;color:#64748b;background:#0d1117;'
            f'border-radius:4px;padding:2px 7px;display:inline-block;'
            f'max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📊 {sector_ref}</p>'
        )

    inner = "".join(bloques)
    return (
        f'<div style="background:#161b2e;border:1px solid {border};border-radius:10px;'
        f'padding:14px 14px 12px;text-align:center;height:225px;overflow:hidden;'
        f'display:flex;flex-direction:column;align-items:center;box-sizing:border-box">'
        f'{inner}</div>'
    )


def score_punto(val, bueno, malo, menor=False):
    if val is None:
        return None
    try:
        v = float(val)
        if menor:
            if v <= bueno:  return 100
            elif v >= malo: return 30
            return 65
        else:
            if v >= bueno:  return 100
            elif v <= malo: return 30
            return 65
    except:
        return None


def calcular_subscores(info: dict):
    """
    Devuelve (score_negocio, score_valoracion, score_total).
    - score_negocio : calidad intrínseca (márgenes, ROE, crecimiento, solidez)
    - score_valoracion: precio relativo (P/E, PEG, P/B, P/S, EV/EBITDA)
    - score_total   : promedio ponderado 60 % negocio + 40 % valoración
    """
    pts_neg = [
        score_punto(info.get("grossMargins"),      0.40, 0.20),
        score_punto(info.get("operatingMargins"),  0.15, 0.05),
        score_punto(info.get("profitMargins"),     0.10, 0.03),
        score_punto(info.get("returnOnEquity"),    0.15, 0.05),
        score_punto(info.get("returnOnAssets"),    0.05, 0.02),
        score_punto(info.get("revenueGrowth"),     0.10, 0.00),
        score_punto(info.get("earningsGrowth"),    0.10, 0.00),
        score_punto(info.get("currentRatio"),      1.5,  1.0),
        score_punto(info.get("debtToEquity"),      50,   150, menor=True),
    ]
    pts_val = [
        score_punto(info.get("trailingPE"),                    15, 30, menor=True),
        score_punto(info.get("forwardPE"),                     15, 25, menor=True),
        score_punto(info.get("pegRatio"),                       1,  2, menor=True),
        score_punto(info.get("priceToBook"),                    1,  5, menor=True),
        score_punto(info.get("priceToSalesTrailing12Months"),   2,  8, menor=True),
        score_punto(info.get("enterpriseToEbitda"),            10, 20, menor=True),
    ]
    neg_v = [p for p in pts_neg if p is not None]
    val_v = [p for p in pts_val if p is not None]
    s_neg = round(sum(neg_v) / len(neg_v)) if neg_v else None
    s_val = round(sum(val_v) / len(val_v)) if val_v else None
    # Ponderación: calidad pesa más que precio para largo plazo
    if s_neg is not None and s_val is not None:
        s_total = round(s_neg * 0.6 + s_val * 0.4)
    elif s_neg is not None:
        s_total = s_neg
    elif s_val is not None:
        s_total = s_val
    else:
        s_total = None
    return s_neg, s_val, s_total


# ── BENCHMARKS POR SECTOR ────────────────────────────────────────────────────
_B = {
    "Technology": {
        "pe_t": "25 – 40", "pe_f": "20 – 32", "peg": "1.5 – 2.5",
        "pb": "5 – 12",    "ps": "4 – 10",    "ev_e": "20 – 35",
        "gm": "55% – 75%", "om": "15% – 28%", "nm": "12% – 25%",
        "roe": "20% – 40%","roa": "8% – 18%", "de": "20 – 60",
        "cr": "1.5 – 3.0", "qr": "1.2 – 2.5",
        "div_y": "0% – 1%","payout": "0% – 30%",
    },
    "Healthcare": {
        "pe_t": "18 – 28", "pe_f": "15 – 24", "peg": "1.2 – 2.0",
        "pb": "3 – 7",     "ps": "2 – 6",     "ev_e": "14 – 22",
        "gm": "50% – 70%", "om": "12% – 22%", "nm": "10% – 20%",
        "roe": "15% – 28%","roa": "6% – 14%", "de": "30 – 80",
        "cr": "1.5 – 2.5", "qr": "1.2 – 2.0",
        "div_y": "1% – 3%","payout": "20% – 50%",
    },
    "Financial Services": {
        "pe_t": "10 – 16", "pe_f": "9 – 14",  "peg": "1.0 – 1.8",
        "pb": "1 – 2",     "ps": "2 – 5",     "ev_e": "10 – 18",
        "gm": "N/A",       "om": "25% – 40%", "nm": "20% – 35%",
        "roe": "10% – 18%","roa": "1% – 3%",  "de": "150 – 400",
        "cr": "N/A",       "qr": "N/A",
        "div_y": "2% – 5%","payout": "25% – 45%",
    },
    "Consumer Cyclical": {
        "pe_t": "18 – 28", "pe_f": "15 – 24", "peg": "1.2 – 2.2",
        "pb": "3 – 7",     "ps": "1 – 3",     "ev_e": "12 – 20",
        "gm": "30% – 50%", "om": "8% – 18%",  "nm": "5% – 14%",
        "roe": "15% – 30%","roa": "5% – 12%", "de": "50 – 120",
        "cr": "1.2 – 2.0", "qr": "0.8 – 1.5",
        "div_y": "0% – 2%","payout": "0% – 35%",
    },
    "Consumer Defensive": {
        "pe_t": "18 – 26", "pe_f": "16 – 22", "peg": "2.0 – 3.5",
        "pb": "3 – 8",     "ps": "1 – 3",     "ev_e": "13 – 20",
        "gm": "35% – 55%", "om": "10% – 20%", "nm": "7% – 16%",
        "roe": "15% – 30%","roa": "6% – 12%", "de": "50 – 120",
        "cr": "0.8 – 1.5", "qr": "0.5 – 1.2",
        "div_y": "2% – 4%","payout": "40% – 65%",
    },
    "Energy": {
        "pe_t": "8 – 15",  "pe_f": "7 – 13",  "peg": "0.5 – 1.5",
        "pb": "1 – 2.5",   "ps": "0.5 – 2",   "ev_e": "6 – 12",
        "gm": "20% – 45%", "om": "8% – 18%",  "nm": "5% – 15%",
        "roe": "10% – 22%","roa": "4% – 10%", "de": "30 – 90",
        "cr": "1.0 – 1.8", "qr": "0.7 – 1.4",
        "div_y": "3% – 6%","payout": "30% – 60%",
    },
    "Industrials": {
        "pe_t": "18 – 26", "pe_f": "15 – 22", "peg": "1.5 – 2.5",
        "pb": "3 – 6",     "ps": "1 – 3",     "ev_e": "13 – 20",
        "gm": "25% – 45%", "om": "8% – 16%",  "nm": "6% – 12%",
        "roe": "12% – 22%","roa": "5% – 10%", "de": "50 – 120",
        "cr": "1.2 – 2.0", "qr": "0.8 – 1.5",
        "div_y": "1% – 3%","payout": "25% – 50%",
    },
    "Basic Materials": {
        "pe_t": "12 – 20", "pe_f": "10 – 17", "peg": "0.8 – 1.8",
        "pb": "1.5 – 3.5", "ps": "0.8 – 2",   "ev_e": "8 – 15",
        "gm": "20% – 40%", "om": "8% – 18%",  "nm": "5% – 14%",
        "roe": "10% – 20%","roa": "4% – 10%", "de": "30 – 80",
        "cr": "1.3 – 2.0", "qr": "0.8 – 1.5",
        "div_y": "2% – 4%","payout": "25% – 50%",
    },
    "Real Estate": {
        "pe_t": "30 – 50", "pe_f": "25 – 45", "peg": "2.0 – 4.0",
        "pb": "1.2 – 2.5", "ps": "4 – 10",    "ev_e": "18 – 30",
        "gm": "50% – 70%", "om": "20% – 35%", "nm": "15% – 30%",
        "roe": "5% – 12%", "roa": "2% – 6%",  "de": "80 – 200",
        "cr": "0.5 – 1.5", "qr": "0.4 – 1.2",
        "div_y": "3% – 6%","payout": "60% – 90%",
    },
    "Utilities": {
        "pe_t": "14 – 20", "pe_f": "12 – 18", "peg": "2.5 – 4.0",
        "pb": "1.3 – 2.2", "ps": "1.5 – 3",   "ev_e": "10 – 15",
        "gm": "30% – 50%", "om": "15% – 28%", "nm": "10% – 20%",
        "roe": "8% – 14%", "roa": "2% – 5%",  "de": "100 – 200",
        "cr": "0.6 – 1.2", "qr": "0.5 – 1.0",
        "div_y": "3% – 5%","payout": "60% – 85%",
    },
    "Communication Services": {
        "pe_t": "18 – 30", "pe_f": "15 – 25", "peg": "1.2 – 2.2",
        "pb": "2 – 6",     "ps": "2 – 6",     "ev_e": "12 – 22",
        "gm": "45% – 65%", "om": "12% – 25%", "nm": "8% – 20%",
        "roe": "12% – 25%","roa": "5% – 12%", "de": "50 – 130",
        "cr": "1.0 – 2.0", "qr": "0.8 – 1.8",
        "div_y": "0% – 3%","payout": "0% – 40%",
    },
}

def ref_sector(sector: str, key: str) -> str:
    val = _B.get(sector, {}).get(key)
    return f"Ref. {sector}: {val}" if val else ""


@st.cache_data(ttl=3600)
def traducir_es(texto: str) -> str:
    """Traduce un texto al español en fragmentos para respetar el límite de caracteres."""
    if not texto:
        return texto
    try:
        limite = 4500
        if len(texto) <= limite:
            return GoogleTranslator(source="auto", target="es").translate(texto)
        fragmentos, actual = [], ""
        for oracion in texto.split(". "):
            if len(actual) + len(oracion) < limite:
                actual += oracion + ". "
            else:
                fragmentos.append(actual.strip())
                actual = oracion + ". "
        if actual:
            fragmentos.append(actual.strip())
        return " ".join(
            GoogleTranslator(source="auto", target="es").translate(f) for f in fragmentos
        )
    except Exception:
        return texto


@st.cache_data(ttl=300)
def buscar_empresa(query: str):
    if not query or len(query) < 2:
        return []
    try:
        resultados = yf.Search(query, max_results=8, news_count=0).quotes
        sugerencias = []
        tipos_validos = {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}
        for r in resultados:
            symbol   = r.get("symbol", "")
            nombre   = r.get("longname") or r.get("shortname") or ""
            tipo     = r.get("quoteType", "EQUITY")
            exchange = r.get("exchange", "")
            if not symbol or tipo not in tipos_validos:
                continue
            label = f"{symbol}  —  {nombre}" if nombre else symbol
            if exchange:
                label += f"  ({exchange})"
            sugerencias.append((label, symbol))
        return sugerencias
    except Exception:
        return []


# ── RANKING DE EMPRESAS ───────────────────────────────────────────────────────
# Candidatos: lista amplia; el filtro real (> $150 B) se aplica en cargar_ranking()
_TICKERS_CANDIDATOS = [
    # ── Tecnología ──────────────────────────────────────────────────────────
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","AVGO","ORCL","AMD",
    "CRM","ADBE","CSCO","QCOM","IBM","NOW","INTU","TXN","AMAT","ACN",
    "UBER","PLTR","ARM","APP","MU","PANW","LRCX","KLAC","SNPS",
    # ── Servicios Financieros ────────────────────────────────────────────────
    "BRK-B","JPM","V","MA","BAC","WFC","GS","MS","AXP","BX",
    "BLK","SPGI","C","PGR","SCHW","CME","ICE","COF","CB",
    # ── Salud ────────────────────────────────────────────────────────────────
    "LLY","UNH","JNJ","ABBV","MRK","TMO","ABT","DHR","PFE","AMGN",
    "ISRG","SYK","VRTX","ELV","HCA","BSX","MDT","ZTS","CI","REGN",
    # ── Consumo Defensivo ────────────────────────────────────────────────────
    "WMT","COST","PG","KO","PEP","PM","MDLZ","MO",
    # ── Consumo Discrecional ────────────────────────────────────────────────
    "HD","MCD","BKNG","NKE","LOW","TJX","SBUX","AMZN",
    # ── Comunicaciones ──────────────────────────────────────────────────────
    "NFLX","TMUS","DIS","CMCSA","VZ","T","CHTR",
    # ── Energía ─────────────────────────────────────────────────────────────
    "XOM","CVX","COP","EOG","SLB","PSX","VLO","MPC",
    # ── Industriales ────────────────────────────────────────────────────────
    "CAT","GE","RTX","ETN","HON","DE","UNP","LMT","BA","UPS",
    "CSX","NSC","WM","RSG","CTAS","EMR","ITW",
    # ── Materiales ──────────────────────────────────────────────────────────
    "LIN","SHW","ECL","APD","NEM","FCX",
    # ── Real Estate ─────────────────────────────────────────────────────────
    "PLD","AMT","EQIX","WELL","SPG",
    # ── Utilities ────────────────────────────────────────────────────────────
    "NEE","SO","DUK","D","EXC","SRE",
    # ── Internacional (cotizadas en EE.UU.) ─────────────────────────────────
    "TSM","NVO","ASML","SAP","SHEL","BABA","TM","HDB","HSBC","BP",
    "RIO","BHP","DEO","UL","BTI","SNY","AZN","NOVO-B.CO",
]
# Eliminar duplicados manteniendo orden
_TICKERS_CANDIDATOS = list(dict.fromkeys(_TICKERS_CANDIDATOS))


@st.cache_data(ttl=3600 * 4, show_spinner=False)
def cargar_ranking():
    def _fetch(tk):
        try:
            info = yf.Ticker(tk).info
            if not info or not info.get("sector"):
                return None
            # Filtro dinámico: solo empresas > $150 B de capitalización
            mcap = info.get("marketCap") or 0
            if mcap < 150_000_000_000:
                return None
            s_neg, s_val, score = calcular_subscores(info)
            if score is None:
                return None
            retorno_52s = info.get("52WeekChange")
            return {
                "ticker":      tk,
                "nombre":      info.get("shortName", tk),
                "sector":      info.get("sector", "N/D"),
                "score":       score,
                "s_neg":       s_neg,
                "s_val":       s_val,
                "mcap":        mcap,
                "mcap_fmt":    fmt_large(mcap),
                "retorno_52s": retorno_52s,
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(_fetch, tk) for tk in _TICKERS_CANDIDATOS]
        resultados = [f.result() for f in as_completed(futures) if f.result()]

    return sorted(resultados, key=lambda x: x["score"], reverse=True)


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_tecnicos(ticker: str):
    import numpy as np
    t_obj = yf.Ticker(ticker)

    # ── Datos diarios (2 años) ────────────────────────────────────────────────
    hist_d = t_obj.history(period="2y", interval="1d")
    if hist_d.empty or len(hist_d) < 20:
        return None
    c = hist_d["Close"]

    def _ma(series, n):
        return float(series.rolling(n).mean().iloc[-1]) if len(series) >= n else None

    ma20_d  = _ma(c, 20)
    ma50_d  = _ma(c, 50)
    ma200_d = _ma(c, 200)

    # RSI(14)
    d   = c.diff()
    avg_g = d.clip(lower=0).rolling(14).mean()
    avg_l = (-d.clip(upper=0)).rolling(14).mean()
    avg_l_safe = avg_l.replace(0, 1e-10)
    rsi = float((100 - 100 / (1 + avg_g / avg_l_safe)).iloc[-1])

    # Bollinger Bands (20, 2)
    bm  = c.rolling(20).mean()
    bs  = c.rolling(20).std()
    bb_up = float((bm + 2 * bs).iloc[-1])
    bb_lo = float((bm - 2 * bs).iloc[-1])

    # MACD (12, 26, 9)
    macd_l  = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    macd_s  = macd_l.ewm(span=9, adjust=False).mean()
    macd_v  = float(macd_l.iloc[-1])
    macd_sv = float(macd_s.iloc[-1])

    # Fibonacci sobre rango 52 semanas
    n_days = min(252, len(c))
    hi52 = float(c.iloc[-n_days:].max())
    lo52 = float(c.iloc[-n_days:].min())
    rng  = hi52 - lo52

    # ── Datos 4h (desde 1h, 730 días) ────────────────────────────────────────
    ma20_4h = ma50_4h = ma200_4h = None
    try:
        h1 = t_obj.history(period="730d", interval="1h")
        if not h1.empty:
            c4 = h1["Close"].resample("4h").last().dropna()
            ma20_4h  = _ma(c4, 20)
            ma50_4h  = _ma(c4, 50)
            ma200_4h = _ma(c4, 200)
    except Exception:
        pass

    return {
        "precio":   float(c.iloc[-1]),
        "ma20_d":   ma20_d,  "ma50_d":   ma50_d,  "ma200_d":  ma200_d,
        "ma20_4h":  ma20_4h, "ma50_4h":  ma50_4h, "ma200_4h": ma200_4h,
        "bb_up":    bb_up,   "bb_lo":    bb_lo,
        "rsi":      round(rsi, 1),
        "macd_bull": macd_v > macd_sv,
        "macd_v":   macd_v,  "macd_sv":  macd_sv,
        "hi52":     hi52,    "lo52":     lo52,
        "fib_786":  hi52 - 0.786 * rng,
        "fib_618":  hi52 - 0.618 * rng,
        "fib_500":  hi52 - 0.500 * rng,
        "fib_382":  hi52 - 0.382 * rng,
        "fib_236":  hi52 - 0.236 * rng,
    }


# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    # Título clicable → vuelve al ranking principal
    if st.button("📊 Analizador de Bolsa", key="btn_home", use_container_width=True):
        st.session_state.ticker_click = None
        for k in [k for k in st.session_state if k.startswith("buscador")]:
            del st.session_state[k]
        st.rerun()
    st.caption("Análisis fundamental · mediano y largo plazo")
    st.markdown("---")
    ticker_input = st_searchbox(
        buscar_empresa,
        placeholder="Apple, AAPL, Microsoft...",
        label="Buscar empresa o ticker",
        key="buscador",
        default=None,
        clear_on_submit=False,
    )
    st.caption("Datos en tiempo real · Yahoo Finance")
    st.markdown("---")
    st.markdown("""
**Secciones disponibles:**
- 📊 Valoración
- 💰 Rentabilidad
- 📈 Crecimiento
- 🏦 Solidez Financiera
- 💵 Dividendos
- 🎯 Analistas
- 📐 Niveles Técnicos
""")
    st.markdown("---")
    st.caption("Los semáforos usan benchmarks generales. Ajusta siempre según el sector específico.")
    # Botón "Volver al ranking" cuando se navegó desde una tarjeta
    if st.session_state.ticker_click and not ticker_input:
        st.markdown("---")
        if st.button("← Volver al ranking", use_container_width=True):
            st.session_state.ticker_click = None
            st.rerun()

# Ticker activo: searchbox tiene prioridad sobre click del ranking
if ticker_input:
    st.session_state.ticker_click = None   # searchbox siempre prevalece
ticker_activo = ticker_input or st.session_state.ticker_click


# ── PANTALLA INICIAL ─────────────────────────────────────────────────────────
if not ticker_activo:
    st.markdown("""
    <div style="text-align:center;padding:32px 0 10px">
        <div style="font-size:52px">📊</div>
        <h2 style="color:#e6f1ff;margin-top:12px;font-size:26px;font-weight:700">Analizador de Bolsa</h2>
        <p style="font-size:15px;color:#8892b0;margin-top:6px">
            Análisis fundamental · mediano y largo plazo
        </p>
    </div>
    """, unsafe_allow_html=True)

    _, hero_col, _ = st.columns([1, 2, 1])
    with hero_col:
        ticker_home = st_searchbox(
            buscar_empresa,
            placeholder="Apple, AAPL, Microsoft...",
            label="Buscar empresa o ticker",
            key="buscador_home",
            default=None,
            clear_on_submit=True,
        )
        if ticker_home:
            st.session_state.ticker_click = ticker_home
            st.rerun()

    # CSS para botones de tarjeta del ranking (solo aplica en esta pantalla)
    st.markdown("""
    <style>
    div[data-testid="stButton"] > button[kind="secondary"] {
        background: #0d1117 !important;
        border: 1px solid #21262d !important;
        border-top: none !important;
        border-radius: 0 0 6px 6px !important;
        color: #64748b !important;
        font-size: 11.5px !important;
        font-weight: 600 !important;
        padding: 5px 0 !important;
        margin-top: -10px !important;
        width: 100% !important;
        transition: color .15s, border-color .15s !important;
    }
    div[data-testid="stButton"] > button[kind="secondary"]:hover {
        border-color: #00c896 !important;
        color: #00c896 !important;
        background: #0d1117 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("---")

    with st.spinner("Cargando ranking · puede tomar 20–30 s la primera vez..."):
        ranking = cargar_ranking()

    if not ranking:
        st.warning("No se pudo cargar el ranking. Intenta recargar la página.")
        st.stop()

    # ── Filtros ─────────────────────────────────────────────────────────────────
    sectores_disponibles = sorted({e["sector"] for e in ranking if e.get("sector")})

    fcol1, fcol2, fcol3, fcol4 = st.columns([1.1, 1.1, 1.4, 1.4])
    with fcol1:
        f_neg = st.selectbox(
            "Calidad del negocio",
            ["Todas", "Sólido (Neg ≥ 65)", "Bueno (Neg ≥ 75)", "Excelente (Neg ≥ 85)"],
            key="f_neg",
        )
    with fcol2:
        f_val = st.selectbox(
            "Valoración actual",
            ["Cualquier precio", "Razonable (Val ≥ 55)", "Atractivo (Val ≥ 65)", "Muy atractivo (Val ≥ 75)"],
            key="f_val",
        )
    with fcol3:
        f_sector = st.multiselect(
            "Sector",
            options=sectores_disponibles,
            default=[],
            placeholder="Todos los sectores",
            key="f_sector",
        )
    with fcol4:
        f_combo = st.selectbox(
            "Búsqueda rápida",
            [
                "Sin filtro",
                "💎 Oportunidades (Neg+Val ≥ 65)",
                "⭐ Calidad accesible (Neg ≥ 80 · Val ≥ 60)",
                "🔥 Top picks (Neg ≥ 85 · Val ≥ 70)",
            ],
            key="f_combo",
        )

    rcol1, rcol2 = st.columns([1.1, 3.9])
    with rcol1:
        f_ret52 = st.selectbox(
            "Retorno últimas 52 sem.",
            ["Todos", "En baja fuerte (< –20%)", "En baja (< 0%)", "Positivo (> 0%)", "Alza fuerte (> +25%)"],
            key="f_ret52",
        )

    _RET52_MAP = {
        "Todos":                   (None, None),
        "En baja fuerte (< –20%)": (None, -0.20),
        "En baja (< 0%)":          (None,  0.00),
        "Positivo (> 0%)":         (0.00,  None),
        "Alza fuerte (> +25%)":    (0.25,  None),
    }
    _ret_lo, _ret_hi = _RET52_MAP[f_ret52]

    def _ok_ret52(val):
        if val is None:
            return f_ret52 == "Todos"
        if _ret_lo is not None and val <= _ret_lo:
            return False
        if _ret_hi is not None and val >= _ret_hi:
            return False
        return True

    # Aplicar combo preset (sobreescribe f_neg / f_val)
    _neg_min = 0
    _val_min = 0
    if f_combo == "💎 Oportunidades (Neg+Val ≥ 65)":
        _neg_min, _val_min = 65, 65
    elif f_combo == "⭐ Calidad accesible (Neg ≥ 80 · Val ≥ 60)":
        _neg_min, _val_min = 80, 60
    elif f_combo == "🔥 Top picks (Neg ≥ 85 · Val ≥ 70)":
        _neg_min, _val_min = 85, 70
    else:
        _neg_min = {"Todas": 0, "Sólido (Neg ≥ 65)": 65, "Bueno (Neg ≥ 75)": 75, "Excelente (Neg ≥ 85)": 85}[f_neg]
        _val_min = {"Cualquier precio": 0, "Razonable (Val ≥ 55)": 55, "Atractivo (Val ≥ 65)": 65, "Muy atractivo (Val ≥ 75)": 75}[f_val]

    ranking_filtrado = [
        e for e in ranking
        if (e.get("s_neg") or 0) >= _neg_min
        and (e.get("s_val") or 0) >= _val_min
        and (not f_sector or e.get("sector") in f_sector)
        and _ok_ret52(e.get("retorno_52s"))
    ]

    hay_filtro = _neg_min > 0 or _val_min > 0 or f_sector or f_ret52 != "Todos"
    conteo_txt = (
        f"{len(ranking_filtrado)} de {len(ranking)} empresas"
        if hay_filtro else
        f"{len(ranking)} empresas"
    )
    if hay_filtro and not ranking_filtrado:
        st.info("Ninguna empresa cumple los filtros seleccionados. Prueba con criterios menos estrictos.")
        st.stop()

    st.markdown("---")
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:6px">'
        f'<span style="font-size:20px;font-weight:700;color:#e6f1ff">🏆 Clasificación Fundamental</span>'
        f'<span style="font-size:13px;color:#4a5270">'
        f'{conteo_txt} · cap. bursátil &gt; $150 B · datos actualizados cada 4 h'
        f'</span></div>',
        unsafe_allow_html=True,
    )
    st.caption("11 indicadores evaluados: valoración, rentabilidad, crecimiento, solidez financiera y liquidez.")

    _BANDAS = [
        (90, 100, "#2ea87e", "EXCELENTE", "Fundamentos muy sólidos en la mayoría de categorías"),
        (80,  89, "#3dba90", "SÓLIDA",    "Buenos fundamentos con pocas señales de alerta"),
        (70,  79, "#8db03a", "BUENA",     "Fundamentos positivos, algunos indicadores moderados"),
        (60,  69, "#b07d2a", "MODERADA",  "Mezcla de fortalezas y debilidades"),
        (50,  59, "#c06030", "MIXTA",     "Más señales de alerta que positivas"),
        ( 0,  49, "#c0392b", "DÉBIL",     "Múltiples indicadores en zona negativa"),
    ]

    for lo, hi, color, etiqueta, descripcion in _BANDAS:
        empresas = [e for e in ranking_filtrado if lo <= e["score"] <= hi]
        if not empresas:
            continue

        st.markdown(
            f'<div style="background:{color}1a;border-left:4px solid {color};'
            f'border-radius:0 8px 8px 0;padding:10px 18px;margin:24px 0 14px">'
            f'<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">'
            f'<span style="color:{color};font-weight:700;font-size:15px">{etiqueta}</span>'
            f'<span style="color:#8b949e;font-size:13px">{lo} – {hi} pts</span>'
            f'<span style="color:#4a5270;font-size:12px">· {len(empresas)} empresa{"s" if len(empresas)!=1 else ""}</span>'
            f'<span style="color:#3d4555;font-size:11.5px;margin-left:6px">{descripcion}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        cols_n = 5
        for i in range(0, len(empresas), cols_n):
            grupo = empresas[i : i + cols_n]
            cols  = st.columns(cols_n)
            for j, emp in enumerate(grupo):
                r52       = emp.get("retorno_52s")
                r52_color = "#2ea87e" if (r52 or 0) >= 0 else "#c0392b"
                r52_str   = (f'+{r52*100:.1f}%' if (r52 or 0) >= 0 else f'{r52*100:.1f}%') if r52 is not None else ""
                s_neg = emp.get("s_neg")
                s_val = emp.get("s_val")

                # color sub-scores
                def _sc(v):
                    if v is None: return "#3d4555", "N/D"
                    c = "#2ea87e" if v >= 70 else ("#b07d2a" if v >= 50 else "#c0392b")
                    return c, str(v)

                neg_c, neg_s = _sc(s_neg)
                val_c, val_s = _sc(s_val)

                with cols[j]:
                    # Tarjeta visual (bordes inferiores planos para unirse al botón)
                    st.markdown(
                        f'<div style="background:#161b2e;border:1px solid #21262d;border-bottom:none;'
                        f'border-left:3px solid {color};border-radius:6px 6px 0 0;'
                        f'padding:11px 12px 10px">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center">'
                        f'<span style="font-weight:700;color:#e6f1ff;font-size:15px">{emp["ticker"]}</span>'
                        f'<span style="background:{color};color:#fff;font-size:12px;font-weight:700;'
                        f'border-radius:4px;padding:2px 7px">{emp["score"]}</span>'
                        f'</div>'
                        f'<div style="font-size:11px;color:#8b949e;margin-top:3px;white-space:nowrap;'
                        f'overflow:hidden;text-overflow:ellipsis" title="{emp["nombre"]}">{emp["nombre"]}</div>'
                        f'<div style="font-size:10.5px;color:#4a5270;margin-top:2px">{emp["sector"]}</div>'
                        f'<div style="display:flex;gap:5px;margin-top:7px">'
                        f'<span style="flex:1;text-align:center;font-size:10.5px;font-weight:700;'
                        f'color:{neg_c};background:{neg_c}22;border-radius:4px;padding:2px 0">'
                        f'Neg {neg_s}</span>'
                        f'<span style="flex:1;text-align:center;font-size:10.5px;font-weight:700;'
                        f'color:{val_c};background:{val_c}22;border-radius:4px;padding:2px 0">'
                        f'Val {val_s}</span>'
                        f'</div>'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-top:7px">'
                        f'<span style="font-size:11.5px;font-weight:600;color:#c0cfe0">{emp["mcap_fmt"]}</span>'
                        f'<span style="font-size:10.5px;color:{r52_color}">'
                        f'{"52s " + r52_str if r52_str else ""}</span>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    # Botón-pie de tarjeta: al hacer click carga el análisis
                    if st.button("Ver análisis →", key=f"r_{emp['ticker']}", use_container_width=True):
                        st.session_state.ticker_click = emp["ticker"]
                        st.rerun()

    st.markdown("---")
    st.caption("La puntuación usa umbrales globales de referencia. El análisis individual aplica benchmarks específicos por sector.")
    st.stop()


# ── CARGA DE DATOS ────────────────────────────────────────────────────────────
with st.spinner(f"Cargando análisis de **{ticker_activo.upper()}**..."):
    try:
        t    = yf.Ticker(ticker_activo.strip().upper())
        info = t.info

        if not info or info.get("quoteType") is None:
            st.error("Ticker no encontrado. Verifica el símbolo e inténtalo de nuevo.")
            st.stop()

        precio      = info.get("currentPrice") or info.get("regularMarketPrice")
        precio_prev = info.get("previousClose")
        cambio_pct  = ((precio - precio_prev) / precio_prev * 100) if precio and precio_prev else None
        eps_t       = info.get("trailingEps")
        eps_f       = info.get("forwardEps")
        eps_chg     = ((eps_f - eps_t) / abs(eps_t)) if eps_t and eps_f and eps_t != 0 else None
        cash        = info.get("totalCash")
        debt        = info.get("totalDebt")
        caja_neta   = (cash or 0) - (debt or 0) if (cash is not None or debt is not None) else None

        # ── SCORE GENERAL ────────────────────────────────────────────────────
        score_neg, score_val, score = calcular_subscores(info)

        def _score_meta(v):
            if v is None: return "#3d4555", "N/D"
            if v >= 75: return "#2ea87e", "SÓLIDA"
            if v >= 55: return "#b07d2a", "MIXTA"
            return "#c0392b", "DÉBIL"

        score_color, score_label = _score_meta(score)
        neg_color,   neg_label   = _score_meta(score_neg)
        val_color,   val_label   = _score_meta(score_val)

        # Mensaje combinado según las dos dimensiones
        if score_neg is not None and score_val is not None:
            if score_neg >= 70 and score_val >= 70:
                score_msg = "Negocio de calidad a precio razonable. Combinación ideal para largo plazo."
            elif score_neg >= 70 and score_val < 55:
                score_msg = "Excelente negocio, pero cotiza con prima elevada. Espera mejor punto de entrada o acepta pagar por calidad."
            elif score_neg < 55 and score_val >= 70:
                score_msg = "Precio atractivo, pero los fundamentos del negocio son débiles. Riesgo de trampa de valor."
            else:
                score_msg = "Fundamentos y valoración mixtos. Profundiza en el contexto del sector antes de decidir."
        elif score:
            score_msg = "Fundamentos sólidos." if score >= 75 else "Fundamentos mixtos." if score >= 55 else "Múltiples señales de alerta."
        else:
            score_msg = ""

        # ── CABECERA ─────────────────────────────────────────────────────────
        cambio_color = "#2ea87e" if (cambio_pct or 0) >= 0 else "#c0392b"
        signo        = "+" if (cambio_pct or 0) >= 0 else ""
        flecha       = "▲" if (cambio_pct or 0) >= 0 else "▼"
        nombre       = info.get("longName", ticker_activo.upper())
        sector       = info.get("sector", "")

        st.markdown(f"""
        <div style="display:flex;justify-content:space-between;align-items:flex-start;
                    flex-wrap:wrap;gap:12px;padding-bottom:16px">
            <div style="flex:1;min-width:260px">
                <div style="font-size:24px;font-weight:700;color:#e6f1ff;">
                    {nombre}
                    <span style="font-size:14px;color:#8b949e;font-weight:500;margin-left:8px">{ticker_activo.upper()}</span>
                </div>
                <div style="font-size:13px;color:#8b949e;margin-top:4px">
                    {info.get('sector','N/D')} &nbsp;·&nbsp; {info.get('industry','N/D')} &nbsp;·&nbsp; {info.get('country','N/D')}
                </div>
            </div>
            <div style="text-align:right;white-space:nowrap">
                <div style="font-size:32px;font-weight:700;color:#e6f1ff;line-height:1">${fmt(precio)}</div>
                <div style="color:{cambio_color};font-size:13px;font-weight:600;margin-top:4px">
                    {flecha} {signo}{fmt(cambio_pct)}% hoy
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── TARJETAS RESUMEN ─────────────────────────────────────────────────
        c1, c2, c3, c4, c5 = st.columns(5)

        with c1:
            if score:
                sn = score_neg if score_neg is not None else "–"
                sv = score_val if score_val is not None else "–"
                st.markdown(
                    f'<div style="background:#161b2e;border:2px solid {score_color};border-radius:10px;'
                    f'padding:12px 10px;text-align:center;min-height:90px;box-sizing:border-box">'
                    f'<div style="font-size:9.5px;font-weight:700;text-transform:uppercase;'
                    f'letter-spacing:1px;color:#8b949e">Puntuación global</div>'
                    f'<div style="font-size:34px;font-weight:700;color:{score_color};line-height:1.1;margin-top:2px">{score}</div>'
                    f'<div style="display:flex;gap:4px;margin-top:5px;justify-content:center">'
                    f'<span style="font-size:10px;font-weight:700;color:{neg_color};background:{neg_color}22;'
                    f'border-radius:3px;padding:1px 5px" title="Calidad del negocio">Neg {sn}</span>'
                    f'<span style="font-size:10px;font-weight:700;color:{val_color};background:{val_color}22;'
                    f'border-radius:3px;padding:1px 5px" title="Atractivo de valoración">Val {sv}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

        for col, label, value in [
            (c2, "Market Cap",    fmt_large(info.get("marketCap"))),
            (c3, "Vol. Promedio", fmt_large(info.get("averageVolume"))),
            (c4, "Máx. 52 sem.", f"${fmt(info.get('fiftyTwoWeekHigh'))}"),
            (c5, "Mín. 52 sem.", f"${fmt(info.get('fiftyTwoWeekLow'))}"),
        ]:
            with col:
                st.markdown(
                    f'<div style="background:#161b2e;border:1px solid #21262d;border-radius:10px;'
                    f'padding:14px;text-align:center;min-height:90px;box-sizing:border-box">'
                    f'<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
                    f'letter-spacing:1px;color:#8b949e">{label}</div>'
                    f'<div style="font-size:20px;font-weight:700;color:#e6f1ff;margin-top:6px">{value}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        if score_msg:
            st.markdown(
                f'<div style="background:#161b2e;border-left:3px solid {score_color};border-radius:0 8px 8px 0;'
                f'padding:10px 16px;margin:14px 0 6px 0">'
                f'<span style="color:{score_color};font-weight:700;font-size:13px">Negocio {neg_label} · Valoración {val_label} &nbsp;— &nbsp;</span>'
                f'<span style="color:#8b949e;font-size:13px">{score_msg}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        with st.expander("ℹ️ ¿Qué miden los dos sub-scores?"):
            st.markdown("""
La puntuación se divide en **dos dimensiones independientes** para responder preguntas distintas:

---

### 🏭 Neg (Calidad del Negocio) — ¿Es una buena empresa?
Mide la solidez intrínseca: márgenes, eficiencia, crecimiento y solidez financiera.
Un **Neg alto** significa que el negocio genera valor, crece y tiene buenas defensas.

| Indicador        | ¿Qué evalúa?                                   |
|------------------|------------------------------------------------|
| Margen Bruto     | Ventaja competitiva en costos                  |
| Margen Operativo | Eficiencia en la operación del negocio         |
| Margen Neto      | % final que queda como ganancia                |
| ROE              | Retorno generado sobre el capital del accionista |
| ROA              | Eficiencia usando todos los activos            |
| Crec. Ingresos   | Velocidad de crecimiento de ventas             |
| Crec. Ganancias  | Expansión de beneficios                        |
| Current Ratio    | Capacidad de pagar deuda a corto plazo         |
| Deuda / Capital  | Nivel de apalancamiento financiero             |

---

### 💲 Val (Atractivo de Valoración) — ¿Está a buen precio ahora?
Mide cuánto pagas por ese negocio comparado con sus fundamentales.
Un **Val alto** significa que el precio actual es razonable o barato.

| Indicador   | ¿Qué evalúa?                                    |
|-------------|--------------------------------------------------|
| P/E Trailing | Precio vs ganancias reales (últimos 12 meses)   |
| P/E Forward  | Precio vs ganancias estimadas                   |
| PEG Ratio    | P/E ajustado por la tasa de crecimiento         |
| P/B          | Precio vs valor contable de los activos         |
| P/S          | Precio vs ingresos totales                      |
| EV/EBITDA    | Valor total de la empresa vs su flujo operativo |

---

### Cómo interpretar la combinación

| Neg | Val | Significado |
|-----|-----|-------------|
| 🟢 Alto | 🟢 Alto | **Oportunidad**: excelente negocio a precio razonable |
| 🟢 Alto | 🔴 Bajo | **Premium justificado**: gran empresa pero cara — espera o paga por calidad |
| 🔴 Bajo | 🟢 Alto | **Trampa de valor**: precio bajo pero fundamentos débiles |
| 🔴 Bajo | 🔴 Bajo | **Evitar**: ni el negocio ni el precio son atractivos |

> La puntuación global pondera 60% Negocio + 40% Valoración, porque la calidad del negocio es más determinante en el largo plazo.
""")

        with st.expander("📋 Descripción de la empresa"):
            desc_original = info.get("longBusinessSummary", "")
            if desc_original:
                with st.spinner("Traduciendo descripción..."):
                    desc_es = traducir_es(desc_original)
                st.write(desc_es)
            else:
                st.write("No disponible.")

        st.markdown("---")

        # ── TABS ─────────────────────────────────────────────────────────────
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "📊 Valoración", "💰 Rentabilidad", "📈 Crecimiento",
            "🏦 Solidez Financiera", "💵 Dividendos", "🎯 Analistas",
            "📐 Niveles Técnicos",
        ])

        # ── TAB 1: VALORACIÓN ─────────────────────────────────────────────────
        with tab1:
            st.markdown("#### ¿A qué precio estás comprando?")
            st.caption("Compara lo que pagas hoy frente a los beneficios, activos y flujos de la empresa.")
            st.markdown("")

            pe_t = info.get("trailingPE")
            pe_f = info.get("forwardPE")
            peg  = info.get("pegRatio")
            pb   = info.get("priceToBook")
            ps   = info.get("priceToSalesTrailing12Months")
            ev_e = info.get("enterpriseToEbitda")

            v_cards = [
                ("P/E Trailing", fmt(pe_t),  *semaforo_sector(pe_t, sector, "pe_t"), interpretar("pe_t",  pe_t),  ref_sector(sector, "pe_t")),
                ("P/E Forward",  fmt(pe_f),  *semaforo_sector(pe_f, sector, "pe_f"), interpretar("pe_f",  pe_f),  ref_sector(sector, "pe_f")),
                ("PEG Ratio",    fmt(peg),   *semaforo_sector(peg,  sector, "peg"),  interpretar("peg",   peg),   ref_sector(sector, "peg")),
                ("P/B",          fmt(pb),    *semaforo_sector(pb,   sector, "pb"),   interpretar("pb",    pb),    ref_sector(sector, "pb")),
                ("P/S",          fmt(ps),    *semaforo_sector(ps,   sector, "ps"),   interpretar("ps",    ps),    ref_sector(sector, "ps")),
                ("EV / EBITDA",  fmt(ev_e),  *semaforo_sector(ev_e, sector, "ev_e"), interpretar("ev_e", ev_e),  ref_sector(sector, "ev_e")),
            ]
            cols = st.columns(6)
            for i, (lbl, val, est, col_, interp, sref) in enumerate(v_cards):
                with cols[i]:
                    st.markdown(card(lbl, val, est, col_, interp, sref), unsafe_allow_html=True)

        # ── TAB 2: RENTABILIDAD ───────────────────────────────────────────────
        with tab2:
            st.markdown("#### ¿Cuánto genera la empresa por cada dólar vendido o invertido?")
            st.caption("Márgenes altos y ROE sólido indican una ventaja competitiva duradera.")
            st.markdown("")

            gm  = info.get("grossMargins")
            om  = info.get("operatingMargins")
            nm  = info.get("profitMargins")
            roe = info.get("returnOnEquity")
            roa = info.get("returnOnAssets")

            r_cards = [
                ("Margen Bruto",     fmt_pct(gm),  *semaforo_sector(gm,  sector, "gm"),  interpretar("gm",  gm),  ref_sector(sector, "gm")),
                ("Margen Operativo", fmt_pct(om),  *semaforo_sector(om,  sector, "om"),  interpretar("om",  om),  ref_sector(sector, "om")),
                ("Margen Neto",      fmt_pct(nm),  *semaforo_sector(nm,  sector, "nm"),  interpretar("nm",  nm),  ref_sector(sector, "nm")),
                ("ROE",              fmt_pct(roe), *semaforo_sector(roe, sector, "roe"), interpretar("roe", roe), ref_sector(sector, "roe")),
                ("ROA",              fmt_pct(roa), *semaforo_sector(roa, sector, "roa"), interpretar("roa", roa), ref_sector(sector, "roa")),
                ("EPS TTM / Fwd",    f"{fmt(eps_t)} / {fmt(eps_f)}", None, "#3d4555",
                 "Ganancia por acción real vs estimada. Permite ver la evolución esperada del beneficio.", None),
            ]
            cols = st.columns(6)
            for i, (lbl, val, est, col_, interp, sref) in enumerate(r_cards):
                with cols[i]:
                    st.markdown(card(lbl, val, est, col_, interp, sref), unsafe_allow_html=True)

        # ── TAB 3: CRECIMIENTO ────────────────────────────────────────────────
        with tab3:
            st.markdown("#### ¿A qué ritmo está creciendo el negocio?")
            st.caption("Para largo plazo, el crecimiento sostenido de ingresos y EPS es uno de los factores más determinantes.")
            st.markdown("")

            rev_g  = info.get("revenueGrowth")
            earn_g = info.get("earningsGrowth")

            s_epsc = semaforo_sector(eps_chg, sector, "eps_chg") if eps_chg is not None else (None, "#3d4555")

            g_cards = [
                ("Crec. Ingresos (YoY)",  fmt_pct(rev_g),  *semaforo_sector(rev_g,  sector, "rev_g"),  interpretar("rev_g",  rev_g),  None),
                ("Crec. Ganancias (YoY)", fmt_pct(earn_g), *semaforo_sector(earn_g, sector, "earn_g"), interpretar("earn_g", earn_g), None),
                ("EPS Trailing (TTM)",    f"${fmt(eps_t)}", None, "#3d4555",
                 "Lo que ganó por acción en los últimos 12 meses. Base para calcular el P/E real.", None),
                ("EPS Forward (est.)",    f"${fmt(eps_f)}", *s_epsc, interpretar("eps_chg", eps_chg), None),
            ]
            cols = st.columns(4)
            for i, (lbl, val, est, col_, interp, sref) in enumerate(g_cards):
                with cols[i]:
                    st.markdown(card(lbl, val, est, col_, interp, sref), unsafe_allow_html=True)

        # ── TAB 4: SOLIDEZ FINANCIERA ─────────────────────────────────────────
        with tab4:
            st.markdown("#### ¿Qué tan sólida es la estructura financiera?")
            st.caption("Una empresa con poca deuda, buena liquidez y flujo de caja positivo resiste mejor las recesiones.")
            st.markdown("")

            de_r = info.get("debtToEquity")
            cr   = info.get("currentRatio")
            qr   = info.get("quickRatio")
            fcf  = info.get("freeCashflow")

            if caja_neta is not None:
                cn_est, cn_col = ("▲ Positiva", "#2ea87e") if caja_neta > 0 else ("▼ Negativa", "#c0392b")
            else:
                cn_est, cn_col = None, "#3d4555"

            f_cards = [
                ("Deuda / Capital",  fmt(de_r),            *semaforo_sector(de_r, sector, "de"), interpretar("de", de_r), ref_sector(sector, "de")),
                ("Current Ratio",    fmt(cr),               *semaforo_sector(cr,   sector, "cr"), interpretar("cr", cr),   ref_sector(sector, "cr")),
                ("Quick Ratio",      fmt(qr),               *semaforo_sector(qr,   sector, "qr"), interpretar("qr", qr),   ref_sector(sector, "qr")),
                ("Flujo Caja Libre", fmt_large(fcf),        None, "#3d4555",
                 "Dinero que le queda a la empresa después de todos sus gastos e inversiones. Cuanto más, mejor.", None),
                ("Caja Total",       fmt_large(cash),       None, "#3d4555",
                 "Efectivo y equivalentes disponibles. Indica capacidad para afrontar imprevistos.", None),
                ("Caja Neta",        fmt_large(caja_neta),  cn_est, cn_col, interpretar("caja_neta", caja_neta), None),
            ]
            cols = st.columns(6)
            for i, (lbl, val, est, col_, interp, sref) in enumerate(f_cards):
                with cols[i]:
                    st.markdown(card(lbl, val, est, col_, interp, sref), unsafe_allow_html=True)

        # ── TAB 5: DIVIDENDOS ─────────────────────────────────────────────────
        with tab5:
            st.markdown("#### ¿Cuánto paga la empresa a sus accionistas?")
            st.caption("Dividendos estables y crecientes son señal de solidez financiera en el largo plazo.")
            st.markdown("")

            div_y  = info.get("dividendYield")
            payout = info.get("payoutRatio")
            div5y  = info.get("fiveYearAvgDividendYield")
            div_r  = info.get("dividendRate")

            if not div_y:
                st.info("Esta empresa no distribuye dividendos actualmente. Puede que reinvierta sus ganancias en crecimiento.")

            s_divy   = semaforo_sector(div_y,  sector, "div_y")  if div_y  else (None, "#3d4555")
            s_payout = semaforo_sector(payout, sector, "payout") if payout else (None, "#3d4555")

            d_cards = [
                ("Dividend Yield",    fmt_pct(div_y) if div_y else "No paga", *s_divy,   interpretar("div_y",  div_y),  ref_sector(sector, "div_y")),
                ("Dividendo / Acción",f"${fmt(div_r)}" if div_r else "N/D",   None, "#3d4555",
                 "Pago anual en efectivo por cada acción que posees.", None),
                ("Payout Ratio",      fmt_pct(payout) if payout else "N/D",   *s_payout, interpretar("payout", payout), ref_sector(sector, "payout")),
                ("Yield Prom. 5 años",f"{fmt(div5y)}%" if div5y else "N/D",   None, "#3d4555",
                 "Yield histórico promedio. Compara con el actual para ver si está barato o caro.", None),
            ]
            cols = st.columns(4)
            for i, (lbl, val, est, col_, interp, sref) in enumerate(d_cards):
                with cols[i]:
                    st.markdown(card(lbl, val, est, col_, interp, sref), unsafe_allow_html=True)

        # ── TAB 6: ANALISTAS ──────────────────────────────────────────────────
        with tab6:
            st.markdown("#### ¿Qué dice el consenso del mercado?")
            st.caption("El precio objetivo y la recomendación del consenso reflejan la expectativa del mercado institucional.")
            st.markdown("")

            target     = info.get("targetMeanPrice")
            target_low = info.get("targetLowPrice")
            target_med = info.get("targetMedianPrice")
            target_hi  = info.get("targetHighPrice")
            n_anal     = info.get("numberOfAnalystOpinions")
            upside     = ((target - precio) / precio * 100) if target and precio else None
            rec        = info.get("recommendationKey", "N/D").upper().replace("_", " ")
            rec_color  = "#2ea87e" if "BUY" in rec else ("#b07d2a" if "HOLD" in rec or "NEUTRAL" in rec else "#c0392b")

            s_upside = semaforo(upside, 15, 0) if upside is not None else (None, "#3d4555")

            a_cards = [
                ("Precio Actual",     f"${fmt(precio)}",                                   None, "#3d4555",
                 "Precio de mercado en este momento.", None),
                ("Precio Obj. Prom.", f"${fmt(target)}" if target else "N/D",              None, "#3d4555",
                 "Promedio de los precios objetivo fijados por analistas institucionales.", None),
                ("Upside Potencial",  f"{fmt(upside)}%" if upside is not None else "N/D",  *s_upside,
                 interpretar("upside", upside), None),
                ("Consenso",          rec,                                                  None, rec_color,
                 "Recomendación mayoritaria: Strong Buy · Buy · Hold · Sell · Strong Sell.", None),
                ("Nº Analistas",      str(n_anal) if n_anal else "N/D",                    None, "#3d4555",
                 "Cuántos analistas cubren esta acción. A más cobertura, mayor fiabilidad del consenso.", None),
            ]
            cols = st.columns(5)
            for i, (lbl, val, est, col_, interp, sref) in enumerate(a_cards):
                with cols[i]:
                    st.markdown(card(lbl, val, est, col_, interp, sref), unsafe_allow_html=True)

            if any([target_low, target_med, target, target_hi]):
                st.markdown("")
                st.markdown("**Rango completo de precios objetivo**")
                rango_df = pd.DataFrame({
                    "Mínimo":     [f"${fmt(target_low)}"],
                    "Mediana":    [f"${fmt(target_med)}"],
                    "Promedio":   [f"${fmt(target)}"],
                    "Máximo":     [f"${fmt(target_hi)}"],
                    "Precio hoy": [f"${fmt(precio)}"],
                })
                st.dataframe(rango_df, hide_index=True, use_container_width=True)

        # ── TAB 7: NIVELES TÉCNICOS ───────────────────────────────────────────
        with tab7:
            st.markdown("#### ¿A qué precios entrar y cuándo tomar beneficios?")
            st.caption("Niveles calculados sobre datos reales: medias móviles, Fibonacci y Bandas de Bollinger.")
            st.markdown("")

            with st.spinner("Calculando niveles técnicos..."):
                tec = calcular_tecnicos(ticker_activo.strip().upper())

            if tec is None:
                st.warning("No hay suficientes datos históricos para calcular niveles técnicos.")
            else:
                px = tec["precio"]

                def _pct(nivel):
                    return ((nivel / px) - 1) * 100 if nivel and px else None

                # ── Resumen indicadores ───────────────────────────────────────
                rsi_v = tec["rsi"]
                if rsi_v > 70:
                    rsi_col, rsi_est, rsi_int = "#c0392b", "Sobrecomprado", "RSI > 70: el precio ha subido rápido; posible corrección a corto plazo."
                elif rsi_v < 30:
                    rsi_col, rsi_est, rsi_int = "#2ea87e", "Sobrevendido",  "RSI < 30: el precio ha caído rápido; posible rebote técnico."
                else:
                    rsi_col, rsi_est, rsi_int = "#b07d2a", "Neutro",        "RSI en zona neutra: no hay señal extrema de momentum."

                macd_col = "#2ea87e" if tec["macd_bull"] else "#c0392b"
                macd_est = "Alcista" if tec["macd_bull"] else "Bajista"
                macd_int = ("Línea MACD sobre señal: momentum comprador dominante."
                            if tec["macd_bull"] else
                            "Línea MACD bajo señal: momentum vendedor dominante.")

                sobre_50  = tec["ma50_d"]  and px > tec["ma50_d"]
                sobre_200 = tec["ma200_d"] and px > tec["ma200_d"]
                if sobre_50 and sobre_200:
                    tend_col, tend_txt, tend_int = "#2ea87e", "Alcista", "Precio sobre MA50 y MA200 diario: tendencia principal positiva."
                elif not sobre_50 and not sobre_200:
                    tend_col, tend_txt, tend_int = "#c0392b", "Bajista", "Precio bajo MA50 y MA200 diario: tendencia principal negativa."
                else:
                    tend_col, tend_txt, tend_int = "#b07d2a", "Mixta",   "Precio entre MA50 y MA200: zona de transición, sin tendencia clara."

                dist_200 = _pct(tec["ma200_d"])
                dist_col = "#2ea87e" if (dist_200 or 0) >= 0 else "#c0392b"

                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown(card("RSI (14) · Diario", f"{rsi_v}", rsi_est, rsi_col, rsi_int), unsafe_allow_html=True)
                with c2:
                    st.markdown(card("MACD · Diario", f"{tec['macd_v']:.3f}", macd_est, macd_col, macd_int), unsafe_allow_html=True)
                with c3:
                    st.markdown(card("Tendencia (MAs D)", tend_txt, None, tend_col, tend_int), unsafe_allow_html=True)
                with c4:
                    st.markdown(card("Dist. MA200 Diario",
                                     f"{dist_200:+.1f}%" if dist_200 is not None else "N/D",
                                     None, dist_col,
                                     "Distancia porcentual del precio a la media de 200 días."),
                                unsafe_allow_html=True)

                st.markdown("")

                # ── Tabla niveles de entrada ──────────────────────────────────
                st.markdown("**🟢 Soportes y zonas de entrada**")
                st.caption("Niveles donde el precio históricamente encuentra compradores. Los que están por debajo del precio actual son los más relevantes para una entrada en pullback.")

                _entradas = [
                    ("MA200 Diario",    tec["ma200_d"],  "Media 200 días · soporte estructural más importante",           "D",   "★★★★★"),
                    ("MA50 Diario",     tec["ma50_d"],   "Media 50 días · soporte de tendencia intermedia",               "D",   "★★★★"),
                    ("MA20 Diario",     tec["ma20_d"],   "Media 20 días · soporte de corto plazo",                        "D",   "★★★"),
                    ("MA200 (4h)",      tec["ma200_4h"], "Media 200 períodos en 4h · soporte técnico medio",              "4h",  "★★★★"),
                    ("MA50 (4h)",       tec["ma50_4h"],  "Media 50 períodos en 4h",                                       "4h",  "★★★"),
                    ("MA20 (4h)",       tec["ma20_4h"],  "Media 20 períodos en 4h · soporte de muy corto plazo",          "4h",  "★★"),
                    ("Fibonacci 78.6%", tec["fib_786"],  "Retroceso profundo · zona de último soporte antes del mínimo",  "Fib", "★★★★"),
                    ("Fibonacci 61.8%", tec["fib_618"],  "Zona dorada de Fibonacci · soporte clave en correcciones",      "Fib", "★★★★★"),
                    ("Fibonacci 50%",   tec["fib_500"],  "Nivel medio del rango 52 semanas · equilibrio técnico",         "Fib", "★★★"),
                    ("Fibonacci 38.2%", tec["fib_382"],  "Primer retroceso significativo · soporte en correcciones leves","Fib", "★★★"),
                    ("BB Inferior (D)", tec["bb_lo"],    "Banda de Bollinger inferior · zona de sobreventa estadística",  "D",   "★★★"),
                    ("Mínimo 52 sem.",  tec["lo52"],     "Mínimo anual · soporte extremo de referencia",                  "–",   "★★"),
                ]
                filas_e = []
                for nombre, nivel, desc, tf, stars in _entradas:
                    if nivel is None:
                        continue
                    pct = _pct(nivel)
                    filas_e.append({
                        "Nivel": nombre, "TF": tf,
                        "Precio": f"${nivel:,.2f}",
                        "Diferencia": f"{pct:+.1f}%" if pct is not None else "–",
                        "Descripción": desc, "Relevancia": stars,
                        "_sort": abs(pct) if pct is not None else 9999,
                    })
                filas_e.sort(key=lambda x: x["_sort"])
                df_e = pd.DataFrame([{k: v for k, v in r.items() if k != "_sort"} for r in filas_e])
                st.dataframe(df_e, hide_index=True, use_container_width=True,
                             column_config={"Diferencia": st.column_config.TextColumn("Δ precio actual")})

                st.markdown("")

                # ── Tabla niveles de salida ───────────────────────────────────
                st.markdown("**🔴 Resistencias y zonas de salida**")
                st.caption("Zonas donde el precio puede encontrar vendedores. Útiles para fijar take-profit o stop parcial.")

                target_anal = info.get("targetMeanPrice")
                _salidas = [
                    ("BB Superior (D)",  tec["bb_up"],   "Banda de Bollinger superior · sobrecompra estadística",         "D",   "★★★"),
                    ("Fibonacci 23.6%",  tec["fib_236"], "Primer retroceso leve · primera resistencia en recuperación",   "Fib", "★★"),
                    ("Máximo 52 sem.",   tec["hi52"],    "Máximo anual · resistencia psicológica más relevante",           "–",   "★★★★"),
                    ("Obj. Analistas",   target_anal,    "Precio objetivo consenso institucional",                        "Fund","★★★★★"),
                ]
                # MAs como resistencia si el precio está por debajo
                for nombre, nivel, tf, stars in [
                    ("MA20 Diario",  tec["ma20_d"],   "D",  "★★★"),
                    ("MA50 Diario",  tec["ma50_d"],   "D",  "★★★★"),
                    ("MA200 Diario", tec["ma200_d"],  "D",  "★★★★★"),
                    ("MA20 (4h)",    tec["ma20_4h"],  "4h", "★★"),
                    ("MA50 (4h)",    tec["ma50_4h"],  "4h", "★★★"),
                    ("MA200 (4h)",   tec["ma200_4h"], "4h", "★★★★"),
                ]:
                    if nivel and px < nivel:
                        _salidas.append((nombre, nivel,
                                         f"{nombre} actuando como resistencia (precio por debajo)",
                                         tf, stars))

                filas_s = []
                for item in _salidas:
                    nombre, nivel, desc, tf, stars = item[0], item[1], item[2], item[3], item[4]
                    if nivel is None:
                        continue
                    pct = _pct(nivel)
                    filas_s.append({
                        "Nivel": nombre, "TF": tf,
                        "Precio": f"${nivel:,.2f}",
                        "Potencial": f"{pct:+.1f}%" if pct is not None else "–",
                        "Descripción": desc, "Relevancia": stars,
                        "_sort": pct if pct is not None else 9999,
                    })
                filas_s.sort(key=lambda x: x["_sort"])
                df_s = pd.DataFrame([{k: v for k, v in r.items() if k != "_sort"} for r in filas_s])
                st.dataframe(df_s, hide_index=True, use_container_width=True,
                             column_config={"Potencial": st.column_config.TextColumn("Δ precio actual")})

                st.markdown("")
                st.caption("⚠️ El análisis técnico es orientativo. Siempre combínalo con el análisis fundamental y el contexto macroeconómico antes de tomar decisiones de inversión.")

    except Exception as e:
        st.error(f"Error al obtener datos: {e}")
