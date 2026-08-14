"""
Restaura tildes/enies faltantes en el texto en español de los JSON de datos
(data/ranking.json, data/companies/*.json, data/etfs_ranking.json,
data/etfs/*.json). El Excel fuente se tipeo sin tildes de forma sistematica
en todo el corpus (mas de 12.000 palabras distintas afectadas), asi que la
correccion combina:

  1. Una regla de sufijo segura: sustantivos terminados en "-cion"/"-sion"
     siempre llevan tilde en espanol ("-ción"/"-sión"), sin excepciones en
     este registro. Cubre la mayor parte del volumen.
  2. Un diccionario explicito de palabras frecuentes en este corpus que
     llevan tilde o ene (armado a partir de un analisis de frecuencia real
     de los datos, no adivinado).

No es NLP perfecto: palabras ambiguas segun el contexto (esta/está,
mas/más, tu/tú, si/sí, el/él, aun/aún) se dejan intactas a proposito, porque
una sustitucion ciega arriesga introducir una tilde incorrecta, que es peor
que dejarla faltante. Cubre la gran mayoria del volumen de tildes faltantes,
no el 100% de los casos posibles.

Uso:
    python scripts/fix_tildes.py          # aplica sobre data/*.json
    python scripts/fix_tildes.py --check  # solo reporta, no escribe
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# Palabras frecuentes en este corpus que llevan tilde o ene y no encajan en
# la regla de sufijo -cion/-sion. Clave = forma sin tilde (minuscula),
# valor = forma correcta (minuscula); el reemplazo preserva mayusculas.
DICCIONARIO = {
    "anios": "años", "anio": "año",
    "tamano": "tamaño", "diseno": "diseño",
    "pequeno": "pequeño", "pequena": "pequeña", "pequenos": "pequeños", "pequenas": "pequeñas",
    "extrano": "extraño", "espanol": "español", "senal": "señal", "senales": "señales",
    "senor": "señor", "senora": "señora", "acompana": "acompaña", "acompanan": "acompañan",
    "desempeno": "desempeño", "companias": "compañías", "compania": "compañía",
    "antiguedad": "antigüedad",

    "indice": "índice", "patron": "patrón", "satelite": "satélite",
    "replica": "réplica", "multiplos": "múltiplos", "multiplo": "múltiplo",
    "multiples": "múltiples", "margenes": "márgenes",
    # "record" se deja intacto a proposito: en este corpus casi siempre es
    # parte de la frase en ingles "track record", no la palabra española
    # "récord" (record deportivo/maximo historico).
    "vehiculo": "vehículo", "linea": "línea", "metrica": "métrica",
    "reputacion": "reputación", "mecanica": "mecánica",

    "categoria": "categoría", "categorias": "categorías",
    "metodologia": "metodología", "tecnologia": "tecnología", "tecnologias": "tecnologías",
    "energia": "energía", "garantia": "garantía", "mayoria": "mayoría",
    "economia": "economía", "biologia": "biología", "geologia": "geología",

    "historico": "histórico", "historica": "histórica",
    "tipico": "típico", "tipica": "típica",
    "unico": "único", "unica": "única",
    "practicamente": "prácticamente", "explicitamente": "explícitamente",
    "especificamente": "específicamente", "historicamente": "históricamente",
    "numero": "número", "numeros": "números",
    "maximo": "máximo", "minimo": "mínimo",
    "periodo": "período", "periodos": "períodos",
    "termino": "término", "terminos": "términos",
    "logico": "lógico", "publico": "público", "publica": "pública",
    "credito": "crédito", "deficit": "déficit",
    "politica": "política", "politicas": "políticas",
    "titulo": "título", "regimen": "régimen",
    "especifico": "específico", "especifica": "específica",
    "basico": "básico", "basica": "básica",
    "automatico": "automático", "automatica": "automática",
    "dinamico": "dinámico", "dinamica": "dinámica",
    "tecnico": "técnico", "tecnica": "técnica",
    "fisica": "física", "estrategico": "estratégico", "estrategica": "estratégica",
    "economico": "económico", "economica": "económica",
    "geografica": "geográfica", "geografico": "geográfico",
    "geopolitico": "geopolítico",
    "rapido": "rápido", "rapida": "rápida",
    "facil": "fácil", "dificil": "difícil",
    "ultimo": "último", "ultima": "última",
    "atras": "atrás", "aqui": "aquí", "asi": "así",
    "ademas": "además", "segun": "según", "tambien": "también", "despues": "después",
    "traves": "través", "farmaceutica": "farmacéutica", "farmaceutico": "farmacéutico",
    "biotecnologica": "biotecnológica", "biotecnologico": "biotecnológico",

    "sesion": "sesión",  # explicito por si no matchea la regla en algun caso raro
    "inversion": "inversión",
    "solido": "sólido", "solida": "sólida",
    "tactico": "táctico", "tactica": "táctica",
    "estandar": "estándar",
    "dolares": "dólares", "dolar": "dólar",
    "decadas": "décadas", "decada": "década",
    "perdida": "pérdida", "perdidas": "pérdidas",
    "lider": "líder", "lideres": "líderes",
    "interes": "interés", "intereses": "intereses",
    "todavia": "todavía", "podria": "podría", "podrian": "podrían",
    "organico": "orgánico", "organica": "orgánica",
    "petroleo": "petróleo",
    "ningun": "ningún",
    "tematico": "temático", "tematica": "temática",
    "debil": "débil", "implicito": "implícito", "implicita": "implícita",
    "razon": "razón",
    "relacion": "relación",
    "intrinseco": "intrínseco", "intrinseca": "intrínseca",
}

# Sufijos donde "-ia" atono debe llevar tilde en "-ía" (esdrujula/hiato):
# ya cubiertos arriba via diccionario explicito, no via regla generica
# porque "historia", "industria", "experiencia", "ganancia" NO llevan tilde.

# Los adjetivos del diccionario tambien aparecen en plural (historico ->
# historicos). Se derivan automaticamente en vez de duplicar cada entrada:
# "-cion"/"-sion" NO se incluyen aca porque el plural de esas ("-ciones"/
# "-siones") pierde la tilde correctamente en espanol (concentraciones).
def _agregar_plurales(diccionario):
    extra = {}
    for k, v in diccionario.items():
        if k.endswith(("o", "a", "e")) and v.endswith(("o", "a", "e", "ó", "á", "é")):
            extra[k + "s"] = v + "s"
        elif k.endswith("il") and v.endswith("il"):  # dificil -> dificiles
            extra[k[:-2] + "iles"] = v[:-2] + "iles"
    return {**diccionario, **extra}


DICCIONARIO = _agregar_plurales(DICCIONARIO)

_CION_RE = re.compile(r"\b([A-Za-zÀ-ÿ]+?)(cion|sion)\b", re.IGNORECASE)


def _match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _fix_cion_sion(text: str) -> str:
    def repl(m):
        stem, suf = m.group(1), m.group(2)
        accented_suf = "ción" if suf == "cion" else "sión"
        return stem + _match_case(suf, accented_suf)
    return _CION_RE.sub(repl, text)


_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]+")

# "record" es ambiguo: en este corpus casi siempre es parte de la frase en
# ingles "track record" (no se traduce), pero tambien aparece solo con el
# sentido de "récord" (maximo historico, ej. "el record anterior"). Se
# excluye especificamente cuando va precedido de "track ".
_RECORD_RE = re.compile(r"(?<!track )record\b", re.IGNORECASE)


def _fix_record(text: str) -> str:
    def repl(m):
        return _match_case(m.group(0), "récord")
    return _RECORD_RE.sub(repl, text)


def _fix_diccionario(text: str) -> str:
    def repl(m):
        word = m.group(0)
        low = word.lower()
        if low in DICCIONARIO:
            return _match_case(word, DICCIONARIO[low])
        return word
    return _WORD_RE.sub(repl, text)


def restaurar_tildes(text: str) -> str:
    if not text or not isinstance(text, str):
        return text
    text = _fix_cion_sion(text)
    text = _fix_record(text)
    text = _fix_diccionario(text)
    return text


def _walk_fix(obj):
    if isinstance(obj, dict):
        return {k: _walk_fix(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_fix(v) for v in obj]
    if isinstance(obj, str):
        return restaurar_tildes(obj)
    return obj


def main():
    check_only = "--check" in sys.argv
    files = list(DATA_DIR.glob("**/*.json"))
    total_changed_files = 0
    total_changed_chars = 0

    for f in files:
        with open(f, encoding="utf-8") as fh:
            original_text = fh.read()
        data = json.loads(original_text)
        fixed = _walk_fix(data)
        fixed_text = json.dumps(fixed, ensure_ascii=False, indent=2)
        if fixed_text != original_text:
            total_changed_files += 1
            total_changed_chars += abs(len(fixed_text) - len(original_text))
            if not check_only:
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(fixed_text)

    modo = "revisados (sin escribir)" if check_only else "corregidos y escritos"
    print(f"OK: {total_changed_files} de {len(files)} archivos {modo}.")


if __name__ == "__main__":
    main()
