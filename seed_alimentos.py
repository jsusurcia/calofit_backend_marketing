import os
import csv
import re
from sqlalchemy.orm import Session
from app.core.database import engine, Base
# Importar TODOS los modelos para que Base.metadata los reconozca
from app.models.user import User
from app.models.role import Role
from app.models.client import Client
from app.models.nutricion import PlanNutricional, PlanDiario
from app.models.alimento import Alimento
# Agrega aquí cualquier otro modelo si es necesario, pero Alimento, User y Role son los principales para el seed.
import app.models  # Para asegurar que todos se registren si hay imports automáticos

def clean_float(val):
    if not val:
        return 0.0
    val = re.sub(r'[^\d.-]', '', val)
    try:
        f = float(val)
        if f == -1.0:
            return 0.0
        return f
    except:
        return 0.0

def reset_db_postgres():
    print("Borrando todo el esquema public y recreándolo...")
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        conn.commit()
    print("Esquema limpiado.")

def run_alembic_upgrade():
    print("Creando tablas con SQLAlchemy (create_all)...")
    Base.metadata.create_all(bind=engine)
    print("Tablas creadas.")

def seed_admin_and_role(db: Session):
    print("Creando rol de Admin...")
    admin_role = Role(
        id=1,
        name="admin",
        description="acceso total al sistema"
    )
    db.add(admin_role)
    db.flush()

    print("Creando usuario administrador...")
    admin_user = User(
        first_name="Admin",
        last_name_paternal="CaloFit",
        last_name_maternal="Admin",
        email="admin@calofit.com",
        hashed_password="$argon2id$v=19$m=65536,t=3,p=4$MTIzNDU2Nzg5MDEyMzQ1Ng$yfVOyoutStP/XpSnYfkcSZf4y4EMS2HtLOM800VXDYE",
        role_id=admin_role.id,
        role_name="admin",
        is_active=True
    )
    db.add(admin_user)
    db.commit()

def normalizar_texto(texto):
    import unicodedata
    if not texto:
        return ""
    # Quitar tildes y pasar a minusculas
    texto = unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode('utf-8')
    return texto.lower().strip()

def seed_csv(db: Session, file_path: str, fuente: str):
    if not os.path.exists(file_path):
        print(f"Archivo no encontrado: {file_path}")
        return

    print(f"Procesando {file_path}...")
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        count = 0
        for row in reader:
            nombre = row.get("Título", "").strip()
            if not nombre:
                continue

            calorias = clean_float(row.get("Energía <ENERC> - kcal", "0"))
            proteina = clean_float(row.get("Proteínas <PROCNT>", "0"))
            grasa = clean_float(row.get("Grasa total <FAT>", "0"))
            
            # Carbohidratos: TCPA usa "Carbohidratos disponibles <CHOAVL>" y "Carbohidratos totales <CHOCDF>"
            carbohidratos = clean_float(row.get("Carbohidratos disponibles <CHOAVL>", "0"))
            if carbohidratos == 0:
                carbohidratos = clean_float(row.get("Carbohidratos totales <CHOCDF>", "0"))
                
            fibra = clean_float(row.get("Fibra dietaria <FIBTG>", "0"))
            
            categoria = row.get("Grupo de alimentos", "").strip()
            id_externo = row.get("Código", "").strip()
            
            # Evitar duplicados si hay el mismo nombre
            existe = db.query(Alimento).filter(Alimento.nombre == nombre).first()
            if not existe:
                nuevo = Alimento(
                    nombre=nombre,
                    nombre_normalizado=normalizar_texto(nombre),
                    calorias_100g=calorias,
                    proteina_100g=proteina,
                    carbohidratos_100g=carbohidratos,
                    grasas_100g=grasa,
                    fibra_100g=fibra,
                    azucar_100g=0.0, # TCPA no suele dar azucar separada
                    categoria=categoria,
                    fuente=fuente,
                    id_externo=id_externo,
                    es_confiable=True,
                    pendiente_validacion=False
                )
                db.add(nuevo)
                count += 1
        db.commit()
        print(f"Se insertaron {count} alimentos desde {file_path}")

def main():
    print("Iniciando limpieza y sembrado de base de datos...")
    # 1. Limpiar BD
    reset_db_postgres()
    # 2. Correr migraciones para tener base limpia
    run_alembic_upgrade()
    
    with Session(engine) as db:
        # 2. Insertar Rol y Admin
        seed_admin_and_role(db)
        
        # 3. Insertar CSVs
        seed_csv(db, "tpca/alimentos_peru.csv", "TCPA")
        seed_csv(db, "tpca/alimentos_preparados_peru.csv", "TCPA Preparados")

if __name__ == "__main__":
    main()
