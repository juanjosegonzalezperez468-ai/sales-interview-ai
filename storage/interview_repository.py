import json
import os

FILE_PATH = "storage/interviews.json"
VACANTES_PATH = "storage/vacantes.json"

# --- GESTIÓN DE VACANTES (ACTUALIZADO) ---

def load_vacantes():
    """Carga todas las configuraciones de vacantes"""
    if not os.path.exists(VACANTES_PATH):
        return {}
    
    try:
        with open(VACANTES_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_vacante(id_v, data):
    vacantes = load_vacantes()
    vacante_id = id_v
    
    # CAMBIO CRÍTICO: Usamos una LISTA en lugar de un diccionario
    preguntas_lista = []
    
    for i, p in enumerate(data.get('preguntas', [])): 
        q_id = f"q_{i+1}"
        # Añadimos el diccionario directamente a la lista
        preguntas_lista.append({
            "id": q_id,
            "texto": p.get('texto'),
            "tipo": p.get('tipo', 'abierta'),
            "peso": int(p.get('peso', 0)),
            "knockout": p.get('knockout', False),
            "reglas": p.get('reglas', {})
        })

    vacante_final = {
        "id": vacante_id,
        "nombre_cargo": data.get('cargo'),
        "activa": True,
        "preguntas": preguntas_lista # <--- Ahora esto es una lista []
    }

    vacantes[vacante_id] = vacante_final
    
    os.makedirs(os.path.dirname(VACANTES_PATH), exist_ok=True)
    with open(VACANTES_PATH, "w", encoding="utf-8") as file:
        json.dump(vacantes, file, indent=4, ensure_ascii=False)

def get_vacante_by_id(vacante_id):
    """Retorna la configuración de una vacante específica"""
    vacantes = load_vacantes()
    return vacantes.get(str(vacante_id))

# --- ENTREVISTAS (GESTIÓN DE RESULTADOS) ---

def load_interviews():
    if not os.path.exists(FILE_PATH):
        return []
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_interview(interview_data):
    interviews = load_interviews()
    interviews.append(interview_data)
    os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
    with open(FILE_PATH, "w", encoding="utf-8") as file:
        json.dump(interviews, file, indent=4, ensure_ascii=False)

def export_to_txt(data):
    """Genera reporte físico detallando el cumplimiento de la vacante"""
    os.makedirs("reportes", exist_ok=True)
    filename = f"reportes/reporte_{data['cc']}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("==============================================\n")
        f.write("       REPORTE TÉCNICO DE EVALUACIÓN IA       \n")
        f.write("==============================================\n\n")
        f.write(f"CANDIDATO:       {data['nombre'].upper()}\n")
        f.write(f"CARGO:           {data.get('cargo', 'N/A').upper()}\n")
        f.write(f"IDENTIFICACIÓN:  {data['cc']}\n")
        f.write(f"PUNTAJE FINAL:   {data['score']}/100\n")
        f.write(f"VEREDICTO:       {data['veredicto']}\n\n")
        
        f.write("--- DETALLES DE COMPETENCIAS ---\n")
        fortalezas = data.get('fortalezas', [])
        f.write(f"✅ LOGROS: {', '.join(fortalezas) if fortalezas else 'Ninguno'}\n")
        
        debilidades = data.get('debilidades', [])
        f.write(f"❌ BRECHAS: {', '.join(debilidades) if debilidades else 'Ninguna'}\n\n")
        
        f.write("--- ANÁLISIS DEL SISTEMA ---\n")
        f.write(f"{data.get('resumen_ia', 'Sin resumen disponible')}\n")
        f.write("\n----------------------------------------------\n")
        f.write(f"REGISTRO ORIGINAL: {data.get('texto_original', 'N/A')}\n")

def get_aggregated_metrics():
    interviews = load_interviews()
    total = len(interviews)
    if total == 0:
        return {"total": 0, "promedio": 0, "skill_mas_comun": "N/A", "raw_data": []}
    
    promedio = round(sum(i.get('score', 0) for i in interviews) / total, 1)
    
    todas_fortalezas = []
    for i in interviews:
        todas_fortalezas.extend(i.get('fortalezas', []))
    
    skill_mas_comun = max(set(todas_fortalezas), key=todas_fortalezas.count) if todas_fortalezas else "N/A"

    return {
        "total": total,
        "promedio": promedio,
        "skill_mas_comun": skill_mas_comun,
        "raw_data": interviews
    }

def delete_interview_by_cc(cc):
    interviews = load_interviews()
    nuevas = [i for i in interviews if str(i.get("cc")) != str(cc)]
    with open(FILE_PATH, "w", encoding="utf-8") as file:
        json.dump(nuevas, file, indent=4, ensure_ascii=False)
    return len(interviews) != len(nuevas)