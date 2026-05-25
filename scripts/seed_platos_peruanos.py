#!/usr/bin/env python3
"""
Seed 20 platos peruanos con ingredientes reales.

Uso:
    python scripts/seed_platos_peruanos.py

Idempotente: usa nombre_normalizado como clave — no duplica si ya existe.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.alimento import Alimento
from app.models.plato import Plato, PlatoIngrediente


# ---------------------------------------------------------------------------
# Alimentos base (valores por 100 g)
# ---------------------------------------------------------------------------
ALIMENTOS = [
    {"nombre": "Arroz blanco cocido",    "nombre_normalizado": "arroz blanco cocido",
     "calorias_100g": 130.0, "proteina_100g": 2.7,  "carbohidratos_100g": 28.2, "grasas_100g": 0.3,
     "categoria": "cereales", "fuente": "seed"},
    {"nombre": "Papa blanca cocida",     "nombre_normalizado": "papa blanca cocida",
     "calorias_100g": 77.0,  "proteina_100g": 2.0,  "carbohidratos_100g": 17.5, "grasas_100g": 0.1,
     "categoria": "tuberculos", "fuente": "seed"},
    {"nombre": "Papa amarilla cocida",   "nombre_normalizado": "papa amarilla cocida",
     "calorias_100g": 83.0,  "proteina_100g": 2.1,  "carbohidratos_100g": 18.8, "grasas_100g": 0.1,
     "categoria": "tuberculos", "fuente": "seed"},
    {"nombre": "Pechuga de pollo cocida","nombre_normalizado": "pechuga de pollo cocida",
     "calorias_100g": 165.0, "proteina_100g": 31.0, "carbohidratos_100g": 0.0,  "grasas_100g": 3.6,
     "categoria": "carnes", "fuente": "seed"},
    {"nombre": "Muslo de pollo cocido",  "nombre_normalizado": "muslo de pollo cocido",
     "calorias_100g": 209.0, "proteina_100g": 26.0, "carbohidratos_100g": 0.0,  "grasas_100g": 11.0,
     "categoria": "carnes", "fuente": "seed"},
    {"nombre": "Lomo de res",            "nombre_normalizado": "lomo de res",
     "calorias_100g": 183.0, "proteina_100g": 26.0, "carbohidratos_100g": 0.0,  "grasas_100g": 8.0,
     "categoria": "carnes", "fuente": "seed"},
    {"nombre": "Carne res molida",       "nombre_normalizado": "carne res molida",
     "calorias_100g": 254.0, "proteina_100g": 17.2, "carbohidratos_100g": 0.0,  "grasas_100g": 20.0,
     "categoria": "carnes", "fuente": "seed"},
    {"nombre": "Cebolla",                "nombre_normalizado": "cebolla",
     "calorias_100g": 40.0,  "proteina_100g": 1.1,  "carbohidratos_100g": 9.3,  "grasas_100g": 0.1,
     "categoria": "verduras", "fuente": "seed"},
    {"nombre": "Tomate",                 "nombre_normalizado": "tomate",
     "calorias_100g": 18.0,  "proteina_100g": 0.9,  "carbohidratos_100g": 3.9,  "grasas_100g": 0.2,
     "categoria": "verduras", "fuente": "seed"},
    {"nombre": "Zanahoria",              "nombre_normalizado": "zanahoria",
     "calorias_100g": 41.0,  "proteina_100g": 0.9,  "carbohidratos_100g": 9.6,  "grasas_100g": 0.2,
     "categoria": "verduras", "fuente": "seed"},
    {"nombre": "Aceite vegetal",         "nombre_normalizado": "aceite vegetal",
     "calorias_100g": 884.0, "proteina_100g": 0.0,  "carbohidratos_100g": 0.0,  "grasas_100g": 100.0,
     "categoria": "grasas", "fuente": "seed"},
    {"nombre": "Ají amarillo",           "nombre_normalizado": "aji amarillo",
     "calorias_100g": 30.0,  "proteina_100g": 1.5,  "carbohidratos_100g": 6.0,  "grasas_100g": 0.3,
     "categoria": "condimentos", "fuente": "seed"},
    {"nombre": "Quinua cocida",          "nombre_normalizado": "quinua cocida",
     "calorias_100g": 120.0, "proteina_100g": 4.4,  "carbohidratos_100g": 21.3, "grasas_100g": 1.9,
     "categoria": "cereales", "fuente": "seed"},
    {"nombre": "Avena",                  "nombre_normalizado": "avena",
     "calorias_100g": 389.0, "proteina_100g": 16.9, "carbohidratos_100g": 66.3, "grasas_100g": 6.9,
     "categoria": "cereales", "fuente": "seed"},
    {"nombre": "Leche entera",           "nombre_normalizado": "leche entera",
     "calorias_100g": 61.0,  "proteina_100g": 3.2,  "carbohidratos_100g": 4.8,  "grasas_100g": 3.3,
     "categoria": "lacteos", "fuente": "seed"},
    {"nombre": "Queso fresco",           "nombre_normalizado": "queso fresco",
     "calorias_100g": 98.0,  "proteina_100g": 7.0,  "carbohidratos_100g": 1.5,  "grasas_100g": 7.0,
     "categoria": "lacteos", "fuente": "seed"},
    {"nombre": "Huevo entero",           "nombre_normalizado": "huevo entero",
     "calorias_100g": 155.0, "proteina_100g": 12.6, "carbohidratos_100g": 1.1,  "grasas_100g": 10.6,
     "categoria": "proteinas", "fuente": "seed"},
    {"nombre": "Palta",                  "nombre_normalizado": "palta",
     "calorias_100g": 160.0, "proteina_100g": 2.0,  "carbohidratos_100g": 9.0,  "grasas_100g": 15.0,
     "categoria": "frutas", "fuente": "seed"},
    {"nombre": "Camote cocido",          "nombre_normalizado": "camote cocido",
     "calorias_100g": 76.0,  "proteina_100g": 1.4,  "carbohidratos_100g": 17.7, "grasas_100g": 0.1,
     "categoria": "tuberculos", "fuente": "seed"},
    {"nombre": "Espinaca",               "nombre_normalizado": "espinaca",
     "calorias_100g": 23.0,  "proteina_100g": 2.9,  "carbohidratos_100g": 3.6,  "grasas_100g": 0.4,
     "categoria": "verduras", "fuente": "seed"},
    {"nombre": "Brócoli",                "nombre_normalizado": "brocoli",
     "calorias_100g": 34.0,  "proteina_100g": 2.8,  "carbohidratos_100g": 6.6,  "grasas_100g": 0.4,
     "categoria": "verduras", "fuente": "seed"},
    {"nombre": "Atún en lata al agua",   "nombre_normalizado": "atun en lata al agua",
     "calorias_100g": 116.0, "proteina_100g": 25.5, "carbohidratos_100g": 0.0,  "grasas_100g": 0.8,
     "categoria": "proteinas", "fuente": "seed"},
    {"nombre": "Trucha cocida",          "nombre_normalizado": "trucha cocida",
     "calorias_100g": 190.0, "proteina_100g": 26.6, "carbohidratos_100g": 0.0,  "grasas_100g": 8.6,
     "categoria": "proteinas", "fuente": "seed"},
    {"nombre": "Jugo de limón",          "nombre_normalizado": "jugo de limon",
     "calorias_100g": 22.0,  "proteina_100g": 0.4,  "carbohidratos_100g": 7.1,  "grasas_100g": 0.2,
     "categoria": "condimentos", "fuente": "seed"},
    {"nombre": "Fideos cocidos",         "nombre_normalizado": "fideos cocidos",
     "calorias_100g": 158.0, "proteina_100g": 5.8,  "carbohidratos_100g": 30.9, "grasas_100g": 0.9,
     "categoria": "cereales", "fuente": "seed"},
    {"nombre": "Lentejas cocidas",       "nombre_normalizado": "lentejas cocidas",
     "calorias_100g": 116.0, "proteina_100g": 9.0,  "carbohidratos_100g": 20.1, "grasas_100g": 0.4,
     "categoria": "legumbres", "fuente": "seed"},
    {"nombre": "Pan de molde",           "nombre_normalizado": "pan de molde",
     "calorias_100g": 265.0, "proteina_100g": 9.0,  "carbohidratos_100g": 49.0, "grasas_100g": 3.2,
     "categoria": "cereales", "fuente": "seed"},
    {"nombre": "Choclo cocido",          "nombre_normalizado": "choclo cocido",
     "calorias_100g": 96.0,  "proteina_100g": 3.4,  "carbohidratos_100g": 21.0, "grasas_100g": 1.5,
     "categoria": "verduras", "fuente": "seed"},
    {"nombre": "Plátano",                "nombre_normalizado": "platano",
     "calorias_100g": 89.0,  "proteina_100g": 1.1,  "carbohidratos_100g": 23.0, "grasas_100g": 0.3,
     "categoria": "frutas", "fuente": "seed"},
]


# ---------------------------------------------------------------------------
# Platos (nombre_ingrediente → gramos)
# ---------------------------------------------------------------------------
PLATOS = [
    {
        "nombre": "Lomo saltado",
        "nombre_normalizado": "lomo saltado",
        "tipo_plato": "almuerzo",
        "budget_level": "moderado",
        "meal_style": "peruano",
        "ingredientes": [
            ("lomo de res",         150.0),
            ("papa blanca cocida",  100.0),
            ("tomate",               50.0),
            ("cebolla",              50.0),
            ("aceite vegetal",       15.0),
        ],
    },
    {
        "nombre": "Arroz con pollo",
        "nombre_normalizado": "arroz con pollo",
        "tipo_plato": "almuerzo",
        "budget_level": "economico",
        "meal_style": "peruano",
        "ingredientes": [
            ("arroz blanco cocido",    150.0),
            ("pechuga de pollo cocida",120.0),
            ("zanahoria",               30.0),
            ("cebolla",                 20.0),
            ("aceite vegetal",          10.0),
        ],
    },
    {
        "nombre": "Ají de gallina",
        "nombre_normalizado": "aji de gallina",
        "tipo_plato": "almuerzo",
        "budget_level": "moderado",
        "meal_style": "peruano",
        "ingredientes": [
            ("pechuga de pollo cocida",150.0),
            ("pan de molde",            30.0),
            ("aji amarillo",            20.0),
            ("leche entera",            50.0),
            ("queso fresco",            20.0),
            ("papa amarilla cocida",   100.0),
        ],
    },
    {
        "nombre": "Ceviche de trucha",
        "nombre_normalizado": "ceviche de trucha",
        "tipo_plato": "almuerzo",
        "budget_level": "moderado",
        "meal_style": "peruano",
        "ingredientes": [
            ("trucha cocida",          150.0),
            ("jugo de limon",           60.0),
            ("cebolla",                 50.0),
            ("aji amarillo",            15.0),
            ("camote cocido",           80.0),
        ],
    },
    {
        "nombre": "Papa rellena",
        "nombre_normalizado": "papa rellena",
        "tipo_plato": "almuerzo",
        "budget_level": "economico",
        "meal_style": "peruano",
        "ingredientes": [
            ("papa blanca cocida",  150.0),
            ("carne res molida",     80.0),
            ("cebolla",              20.0),
            ("aceite vegetal",       10.0),
        ],
    },
    {
        "nombre": "Causa limeña de atún",
        "nombre_normalizado": "causa limena de atun",
        "tipo_plato": "almuerzo",
        "budget_level": "economico",
        "meal_style": "peruano",
        "ingredientes": [
            ("papa amarilla cocida",   130.0),
            ("atun en lata al agua",    50.0),
            ("aji amarillo",            10.0),
            ("palta",                   30.0),
        ],
    },
    {
        "nombre": "Pollo a la plancha con arroz",
        "nombre_normalizado": "pollo a la plancha con arroz",
        "tipo_plato": "almuerzo",
        "budget_level": "economico",
        "meal_style": "alto_proteina",
        "ingredientes": [
            ("pechuga de pollo cocida",180.0),
            ("arroz blanco cocido",    150.0),
            ("aceite vegetal",           5.0),
        ],
    },
    {
        "nombre": "Trucha al vapor con papa",
        "nombre_normalizado": "trucha al vapor con papa",
        "tipo_plato": "almuerzo",
        "budget_level": "moderado",
        "meal_style": "alto_proteina",
        "ingredientes": [
            ("trucha cocida",         170.0),
            ("papa blanca cocida",    150.0),
        ],
    },
    {
        "nombre": "Quinua con verduras",
        "nombre_normalizado": "quinua con verduras",
        "tipo_plato": "almuerzo",
        "budget_level": "economico",
        "meal_style": "vegetariano",
        "ingredientes": [
            ("quinua cocida",   180.0),
            ("zanahoria",        50.0),
            ("brocoli",          60.0),
            ("aceite vegetal",    5.0),
        ],
    },
    {
        "nombre": "Estofado de pollo",
        "nombre_normalizado": "estofado de pollo",
        "tipo_plato": "almuerzo",
        "budget_level": "economico",
        "meal_style": "peruano",
        "ingredientes": [
            ("muslo de pollo cocido",  150.0),
            ("papa blanca cocida",     100.0),
            ("zanahoria",               50.0),
            ("tomate",                  30.0),
            ("aceite vegetal",          10.0),
        ],
    },
    {
        "nombre": "Seco de res con arroz",
        "nombre_normalizado": "seco de res con arroz",
        "tipo_plato": "almuerzo",
        "budget_level": "moderado",
        "meal_style": "peruano",
        "ingredientes": [
            ("lomo de res",            150.0),
            ("arroz blanco cocido",    120.0),
            ("zanahoria",               30.0),
            ("cebolla",                 30.0),
            ("aceite vegetal",          10.0),
        ],
    },
    {
        "nombre": "Sopa de lentejas",
        "nombre_normalizado": "sopa de lentejas",
        "tipo_plato": "almuerzo",
        "budget_level": "economico",
        "meal_style": "vegetariano",
        "ingredientes": [
            ("lentejas cocidas",  100.0),
            ("zanahoria",          50.0),
            ("cebolla",            30.0),
            ("aceite vegetal",      5.0),
        ],
    },
    {
        "nombre": "Tallarín saltado con pollo",
        "nombre_normalizado": "tallarin saltado con pollo",
        "tipo_plato": "almuerzo",
        "budget_level": "economico",
        "meal_style": "peruano",
        "ingredientes": [
            ("fideos cocidos",         120.0),
            ("pechuga de pollo cocida",100.0),
            ("tomate",                  50.0),
            ("cebolla",                 50.0),
            ("aceite vegetal",          15.0),
        ],
    },
    {
        "nombre": "Avena con leche",
        "nombre_normalizado": "avena con leche",
        "tipo_plato": "desayuno",
        "budget_level": "economico",
        "meal_style": "ligero",
        "ingredientes": [
            ("avena",         50.0),
            ("leche entera", 200.0),
        ],
    },
    {
        "nombre": "Huevos revueltos",
        "nombre_normalizado": "huevos revueltos",
        "tipo_plato": "desayuno",
        "budget_level": "economico",
        "meal_style": "alto_proteina",
        "ingredientes": [
            ("huevo entero",   150.0),
            ("cebolla",         30.0),
            ("aceite vegetal",   5.0),
        ],
    },
    {
        "nombre": "Ensalada de quinua y palta",
        "nombre_normalizado": "ensalada de quinua y palta",
        "tipo_plato": "almuerzo",
        "budget_level": "economico",
        "meal_style": "vegetariano",
        "ingredientes": [
            ("quinua cocida",  100.0),
            ("palta",           60.0),
            ("tomate",          60.0),
            ("cebolla",         30.0),
        ],
    },
    {
        "nombre": "Pollo a la brasa (porción)",
        "nombre_normalizado": "pollo a la brasa porcion",
        "tipo_plato": "almuerzo",
        "budget_level": "moderado",
        "meal_style": "peruano",
        "ingredientes": [
            ("muslo de pollo cocido",  200.0),
            ("papa amarilla cocida",    80.0),
        ],
    },
    {
        "nombre": "Choclo con queso",
        "nombre_normalizado": "choclo con queso",
        "tipo_plato": "snack",
        "budget_level": "economico",
        "meal_style": "peruano",
        "ingredientes": [
            ("choclo cocido",   150.0),
            ("queso fresco",     50.0),
        ],
    },
    {
        "nombre": "Ensalada de espinaca y palta",
        "nombre_normalizado": "ensalada de espinaca y palta",
        "tipo_plato": "almuerzo",
        "budget_level": "economico",
        "meal_style": "ligero",
        "ingredientes": [
            ("espinaca",       100.0),
            ("palta",           50.0),
            ("tomate",          60.0),
            ("jugo de limon",   15.0),
        ],
    },
    {
        "nombre": "Menú del día económico",
        "nombre_normalizado": "menu del dia economico",
        "tipo_plato": "almuerzo",
        "budget_level": "economico",
        "meal_style": "peruano",
        "ingredientes": [
            ("arroz blanco cocido",    150.0),
            ("pechuga de pollo cocida",120.0),
            ("papa blanca cocida",      80.0),
            ("zanahoria",               30.0),
            ("aceite vegetal",           8.0),
        ],
    },
]


def get_or_create_alimento(db, data: dict) -> Alimento:
    alimento = db.query(Alimento).filter(
        Alimento.nombre_normalizado == data["nombre_normalizado"]
    ).first()
    if alimento:
        return alimento
    alimento = Alimento(**data)
    db.add(alimento)
    db.flush()
    return alimento


def seed(db: SessionLocal):
    print("Seeding alimentos...")
    alimento_map: dict[str, Alimento] = {}
    for a in ALIMENTOS:
        obj = get_or_create_alimento(db, a)
        alimento_map[a["nombre_normalizado"]] = obj
    db.flush()
    print(f"  {len(alimento_map)} alimentos listos.")

    print("Seeding platos...")
    creados = 0
    for p_data in PLATOS:
        existe = db.query(Plato).filter(
            Plato.nombre_normalizado == p_data["nombre_normalizado"]
        ).first()
        if existe:
            print(f"  SKIP (existe): {p_data['nombre']}")
            continue

        plato = Plato(
            nombre=p_data["nombre"],
            nombre_normalizado=p_data["nombre_normalizado"],
            tipo_plato=p_data["tipo_plato"],
            budget_level=p_data["budget_level"],
            meal_style=p_data["meal_style"],
            origen="manual",
        )
        db.add(plato)
        db.flush()

        for orden, (nombre_norm, gramos) in enumerate(p_data["ingredientes"]):
            alimento = alimento_map.get(nombre_norm)
            if not alimento:
                print(f"  WARN: alimento '{nombre_norm}' no encontrado para '{p_data['nombre']}'")
                continue
            ing = PlatoIngrediente(
                plato_id=plato.id,
                alimento_id=alimento.id,
                gramos=gramos,
                orden=orden,
            )
            db.add(ing)

        creados += 1
        print(f"  CREADO: {p_data['nombre']}  ({p_data['meal_style']}, {p_data['budget_level']})")

    db.commit()
    print(f"\nDone. {creados} platos nuevos creados.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed(db)
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()
