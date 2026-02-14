import sys
import os
from core.engine import evaluar_candidato_motor
import storage.interview_repository as repo

def run_interview_process():
    print("\n" + "═"*50)
    print("      📊 NUEVA EVALUACIÓN ANALÍTICA V3.0")
    print("═"*50)
    
    cc = input("CC del candidato: ")
    nombre = input("Nombre completo: ")
    print(f"\nPegue la entrevista de {nombre}:")
    texto_raw = input("> ")

    if len(texto_raw.split()) < 5:
        print("\n❌ Error: El texto es demasiado corto.")
        return

    # Procesa con el motor nuevo (Punto 3)
    res = evaluar_candidato_motor(texto_raw)

    # IMPRESIÓN COMPLETA EN PANTALLA
    print("\n" + "*" * 45)
    print("       📊 RESULTADO DEL ANÁLISIS")
    print("*" * 45)
    print(f" CANDIDATO: {nombre.upper()}")
    print(f" CC:        {cc}")
    print(f" FECHA:     {res.get('fecha_evaluacion')}")
    print(f" PUNTAJE:   {res['score']}/100")
    print(f" VEREDICTO: {res['veredicto']}")
    print("-" * 45)
    print(f" ✅ FORTALEZAS: {', '.join(res.get('fortalezas', []))}")
    print(f" ❌ DEBILIDADES: {', '.join(res.get('debilidades', []))}")
    print(f" 💡 RESUMEN:    {res.get('resumen_ia')}")
    print("*" * 45)

    # GUARDA TODO EL PAQUETE
    datos_completos = {
        "cc": cc,
        "nombre": nombre,
        "texto_original": texto_raw,
        **res 
    }
    repo.save_interview(datos_completos)
    repo.export_to_txt(datos_completos)
    print("\n✅ Registro guardado exitosamente.")
    input("\nPresione ENTER para volver...")

def show_history():
    print(f"\n{'FECHA':<20} | {'CC':<10} | {'NOMBRE':<20} | {'SCORE':<5}")
    print("=" * 65)
    for ent in repo.load_interviews():
        f = ent.get('fecha_evaluacion', 'S/F')
        c = ent.get('cc', 'S/N')
        n = ent.get('nombre', 'S/N')[:20]
        s = ent.get('score', 0)
        print(f"{f:<20} | {c:<10} | {n:<20} | {s:<5}")
    input("\nPresione ENTER para continuar...")

def search_candidate():
    cc_buscar = input("\nIngrese la CC a consultar: ")
    for ent in repo.load_interviews():
        if str(ent.get('cc')) == cc_buscar:
            print(f"\n🔍 DETALLE DE {ent['nombre'].upper()}")
            print(f"Fecha:      {ent.get('fecha_evaluacion')}")
            print(f"Veredicto:  {ent['veredicto']}")
            print(f"Fortalezas: {', '.join(ent.get('fortalezas', []))}")
            print(f"Debilidades: {', '.join(ent.get('debilidades', []))}")
            print(f"Resumen IA: {ent.get('resumen_ia')}")
            return
    print("❌ No encontrado.")

def main_menu():
    while True:
        print(f"\n🏢 SALES AI ANALYTICS - PANEL DE CONTROL")
        print("1. Evaluar Nuevo Candidato")
        print("2. Ver Historial (Resumen)")
        print("3. Buscar Detalle por CC")
        print("4. Modificar Candidato")
        print("5. Eliminar Registro")
        print("6. Borrar TODA la Base de Datos")
        print("7. VER DASHBOARD DE ESTADÍSTICAS (REPORTES)") # <--- ESTA
        print("8. Salir")
        
        op = input("\nSeleccione una opción: ")
        
        if op == "1": run_interview_process()
        elif op == "2": show_history()
        elif op == "3": search_candidate()
        elif op == "4": # lógica de modificar
            pass 
        elif op == "5": # lógica de eliminar
            pass
        elif op == "6": # lógica de borrar todo
            pass
        elif op == "7": 
            pass
        elif op == "8":
            print("Saliendo..."); break

if __name__ == "__main__":
    main_menu()