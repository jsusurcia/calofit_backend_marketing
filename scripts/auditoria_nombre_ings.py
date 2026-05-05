"""
auditoria_nombre_ingredientes.py
Detecta todos los platos de BD donde el nombre menciona ingredientes
que no están realmente en plato_ingredientes.
"""
import re
import unicodedata
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

engine = create_engine("postgresql://postgres:leomeflo09@calofit_db:5432/BD_Calofit")
s = sessionmaker(bind=engine)()


def norm(t):
    t = (t or "").strip().lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", t).strip()


IGNORAR = {
    "con", "sin", "del", "los", "las", "una", "unos", "unas",
    "horno", "plancha", "parrilla", "vapor", "frito", "cocido", "asado",
    "ligera", "ligero", "saludable", "natural", "fresco", "fresca",
    "estilo", "tipo", "especial", "peruano", "casero", "salsa",
    "tostado", "sancochado", "hervido",
}

rows = s.execute(text("""
    SELECT p.id, p.nombre,
           STRING_AGG(a.nombre, '|' ORDER BY pi.orden) AS ings
    FROM platos p
    JOIN plato_ingredientes pi ON pi.plato_id = p.id
    JOIN alimentos a ON a.id = pi.alimento_id
    GROUP BY p.id, p.nombre
    ORDER BY p.id
""")).fetchall()

problemas = []
for r in rows:
    nombre_n = norm(r.nombre)
    ings_tokens = set()
    for ing in (r.ings or "").split("|"):
        for tok in norm(ing).split():
            if len(tok) >= 4:
                ings_tokens.add(tok)

    tokens_nombre = [
        t for t in nombre_n.split()
        if len(t) >= 5 and t not in IGNORAR
    ]
    if len(tokens_nombre) < 2:
        continue

    ausentes = [
        t for t in tokens_nombre
        if not any(t in it or it in t for it in ings_tokens)
    ]

    if len(ausentes) > len(tokens_nombre) * 0.5:
        problemas.append({
            "id": r.id,
            "nombre": r.nombre,
            "ausentes": ausentes,
            "tokens": tokens_nombre,
            "ings": r.ings,
        })

print(f"Platos con nombre/ingrediente inconsistente: {len(problemas)}")
for p in problemas:
    print(f"  ID={p['id']}: [{p['nombre']}]")
    print(f"    tokens={p['tokens']}  ausentes={p['ausentes']}")
    print(f"    ings={p['ings'][:100]}")
