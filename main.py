import sys
import os
from core.engine import evaluar_candidato_motor
import storage.interview_repository as repo

def run_interview_process():
    print("\n" + "═"*50)
    print("      📊 NUEVA EVALUACIÓN ANALÍTICA V4.1")
    print("═"*50)
    
    # 🆕 NUEVO: SELECCIÓN DE VACANTE
    print("\nSeleccione la VACANTE para este proceso:")
    print("1. Vendedor Junior")
    print("2. Gerente Comercial")
    print("3. Soporte Técnico")
    print("4. Otra (Ingresar manualmente)")
    
    v_op = input("> ")
    if v_op == "1": vacante_nombre = "Vendedor Junior"
    elif v_op == "2": vacante_nombre = "Gerente Comercial"
    elif v_op == "3": vacante_nombre = "Soporte Técnico"
    else: vacante_nombre = input("Nombre de la vacante: ")

    # 1. CAPTURA DE DATOS BÁSICOS
    cc = input("\nCC del candidato: ")
    nombre = input("Nombre completo: ")
    email = input("Correo electrónico: ")
    telefono = input("Teléfono (Ej: 573001234567): ")
    
    print(f"\nAVISO DE PRIVACIDAD: ¿El candidato {nombre} autoriza el")
    print("tratamiento de sus datos para contacto directo? (s/n)")
    autoriza_input = input("> ").lower()
    autoriza_texto = "SÍ" if autoriza_input == 's' else "NO"

    # 2. CAPTURA DE LA ENTREVISTA
    print(f"\nPegue la entrevista de {nombre} para la vacante de {vacante_nombre}:")
    texto_raw = input("> ")

    if len(texto_raw.split()) < 5:
        print("\n❌ Error: El texto es demasiado corto.")
        return

    # Procesa con el motor de IA
    res = evaluar_candidato_motor(texto_raw)

    # 3. IMPRESIÓN COMPLETA EN PANTALLA
    print("\n" + "*" * 45)
    print("       📊 RESULTADO DEL ANÁLISIS")
    print("*" * 45)
    print(f" CANDIDATO: {nombre.upper()}")
    print(f" VACANTE:   {vacante_nombre.upper()}") # 🆕 Mostramos la vacante
    print(f" PUNTAJE:   {res['score']}/100")
    print(f" VEREDICTO: {res['veredicto']}")
    print("-" * 45)
    # ... (resto de impresiones de fortalezas/debilidades)

    # 4. PREPARACIÓN DEL PAQUETE PARA SUPABASE
    datos_completos = {
        "cc": cc,
        "nombre": nombre,
        "email": email,
        "telefono": telefono,
        "autoriza": autoriza_texto,
        "vacante": vacante_nombre, # 🆕 Guardamos el nombre de la vacante
        "texto_original": texto_raw,
        **res 
    }

    # 5. GUARDADO
    repo.save_interview(datos_completos)
    repo.export_to_txt(datos_completos)
    
    print(f"\n✅ Registro guardado exitosamente en la vacante: {vacante_nombre}")
    input("\nPresione ENTER para volver...")

# ... (resto de funciones show_history, search_candidate, etc., se mantienen igual)

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