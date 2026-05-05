"""Test de _agregar_equivalencia_gramos con los 3 casos del usuario."""
import ast, re, unicodedata

src = open("app/services/asistente_nutricion.py", encoding="utf-8").read()
ast.parse(src)
print("SINTAXIS OK")

ns = {"__builtins__": __builtins__, "re": re, "unicodedata": unicodedata}
exec(compile(src, "asistente_nutricion.py", "exec"), ns)
fn = ns["_agregar_equivalencia_gramos"]

casos = [
    ("2 rebanadas  pan integral (183.4 kcal)",  True),
    ("1 aguacate (140 kcal)",                    True),
    ("1/4 taza queso fresco (100 kcal)",         True),
    ("1 platano (106 kcal)",                     True),
    ("1 limon (25 kcal)",                        True),
    ("2 tomates (54 kcal)",                      True),
    ("150g pechuga de pollo (247 kcal)",         False),   # ya gramos
    ("1 cucharada aceite de oliva (88 kcal)",    True),
    ("1 cdta miel (23 kcal)",                    True),
]

print()
for texto, espera_cambio in casos:
    resultado = fn(texto)
    cambio = resultado != texto
    estado = "OK" if cambio == espera_cambio else "FALLO"
    print(f"  [{estado}] {resultado}")
