import json
import os
from supabase import create_client

# Configuración de conexión (Asegúrate de tener estas variables en tu .env o en Render)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- GESTIÓN DE VACANTES (Sincronizado con Supabase) ---

def load_vacantes():
    """Carga vacantes directamente desde Supabase"""
    try:
        res = supabase.table('vacantes').select('*').execute()
        # Convertimos a diccionario para mantener compatibilidad con tu código actual
        return {str(v['id']): v for v in res.data}
    except Exception as e:
        print(f"❌ Error cargando vacantes: {e}")
        return {}

def get_vacante_by_id(vacante_id):
    """Retorna una vacante específica desde Supabase"""
    try:
        res = supabase.table('vacantes').select('*').eq('id', vacante_id).execute()
        return res.data[0] if res.data else None
    except:
        return None

# --- ENTREVISTAS (EL CAMBIO CLAVE) ---

def load_interviews():
    """Carga entrevistas desde Supabase para que la consola las vea"""
    try:
        res = supabase.table('entrevistas').select('*').execute()
        return res.data
    except Exception as e:
        print(f"❌ Error cargando historial: {e}")
        return []

def save_interview(data):
    """Guarda la entrevista en Supabase con los nombres de columna correctos"""
    try:
        # Mantenemos toda tu estructura, solo ajustamos los nombres de las llaves
        payload = {
            "nombre_candidato": data.get('nombre'),
            "identificacion": str(data.get('cc')),
            "vacante_id": data.get('vacante_id'),
            "score": data.get('score'),      # <--- CAMBIADO: Antes tenías score_ai
            "veredicto": data.get('veredicto'),
            "fortalezas": data.get('fortalezas'),
            "debilidades": data.get('debilidades'),
            "analisis_ia": data.get('resumen_ia'),
            "fecha": data.get('fecha_evaluacion')
        }
        
        # Insertamos en la tabla
        res = supabase.table('entrevistas').insert(payload).execute()
        
        # Mantenemos tu log de éxito
        print("✅ Guardado exitoso en Supabase")
        return res
    except Exception as e:
        # Mantenemos tu manejo de errores
        print(f"❌ Error guardando en Supabase: {e}")
        return None

def export_to_txt(data):
    """Mantenemos esta función por si quieres el archivo físico en tu PC"""
    os.makedirs("reportes", exist_ok=True)
    filename = f"reportes/reporte_{data['cc']}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"CANDIDATO: {data['nombre'].upper()}\n")
        f.write(f"PUNTAJE: {data['score']}/100\n")
        f.write(f"VEREDICTO: {data['veredicto']}\n")