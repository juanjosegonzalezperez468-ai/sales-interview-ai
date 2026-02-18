from datetime import datetime

def evaluar_candidato_motor_supabase(respuestas_candidato, config_preguntas):
    """
    Versión 4.3: Mantiene detalles anteriores + Agrega Categorías y Recomendaciones.
    """
    # 1. NUEVO: Estructura de Dimensiones
    categorias = {
        "Tecnica": {"puntos": 0},
        "Experiencia": {"puntos": 0},
        "Blandas": {"puntos": 0},
        "Ajuste": {"puntos": 0}
    }
    
    score_total = 0
    fortalezas = []
    debilidades = []
    detalles_ia = [] # Mantenemos tus detalles de "Correcto/Incorrecto"

    def limpiar_local(texto):
        cambios = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u'}
        t = str(texto).lower().strip()
        for original, reemplazo in cambios.items():
            t = t.replace(original, reemplazo)
        return t

    for config in config_preguntas:
        q_id = config.get('id')
        peso = config.get('peso', 0)
        tipo = config.get('tipo')
        cat = config.get('categoria', 'Ajuste') # Nueva columna en Supabase
        
        # Buscamos la respuesta
        rta_candidato = next((r['valor'] for r in respuestas_candidato if str(r['id']) == str(q_id)), "")
        puntos_pregunta = 0

        # --- EVALUACIÓN (Tu lógica original intacta) ---
        if tipo in ["booleana", "multiple", "seleccion_multiple"]:
            valor_recibido = limpiar_local(rta_candidato)
            valor_esperado = limpiar_local(config.get('reglas', {}).get('ideal', ''))
            puntos_pregunta = 100 if valor_recibido == valor_esperado else 0
            detalles_ia.append(f"{config['texto']}: {'✅' if puntos_pregunta == 100 else '❌'}")

        elif "escala" in tipo:
            try:
                max_escala = 5 if "5" in tipo else 10
                puntos_pregunta = (float(rta_candidato) / max_escala) * 100
                detalles_ia.append(f"{config['texto']}: {rta_candidato}/{max_escala}")
            except:
                detalles_ia.append(f"{config['texto']}: Error dato")

        # --- LÓGICA DE KNOCK-OUT ---
        if config.get('knockout') is True and puntos_pregunta < 100:
            return {
                "score": 0,
                "veredicto": "DESCALIFICADO (KO)",
                "analisis_ia": f"No cumple requisito crítico: {config['texto']}",
                "estado": "Rechazado"
            }

        # --- 2. NUEVO: SUMA POR CATEGORÍA ---
        if cat in categorias:
            categorias[cat]["puntos"] += (puntos_pregunta * (peso / 100))
        
        score_total += (puntos_pregunta * (peso / 100))
        
        # --- 3. NUEVO: FORTALEZAS Y DEBILIDADES ---
        texto_item = config.get('texto_corto') or config.get('texto')
        if puntos_pregunta >= 80:
            if len(fortalezas) < 2: fortalezas.append(texto_item)
        elif puntos_pregunta <= 40:
            if len(debilidades) < 2: debilidades.append(texto_item)

    # --- 4. NUEVO: RECOMENDACIÓN AUTOMÁTICA ---
    if score_total >= 85: rec = "⭐ Perfil sobresaliente. Agendar ya."
    elif score_total >= 60: rec = "🔍 Perfil promedio. Validar dudas."
    else: rec = "🚫 No cumple mínimos."

    # Mantenemos tus detalles_ia pero agregamos el resumen al inicio
    analisis_completo = f"{rec} | Desglose: T:{round(categorias['Tecnica']['puntos'],1)}% E:{round(categorias['Experiencia']['puntos'],1)}% | " + " | ".join(detalles_ia)

    return {
        "score": round(score_total, 2),
        "score_ia": round(score_total, 2),
        "veredicto": "APROBADO" if score_total >= 70 else "RECHAZADO",
        "fortalezas": ", ".join(fortalezas),
        "debilidades": ", ".join(debilidades),
        "analisis_ia": analisis_completo, # Aquí va todo: recomendación + desglose + detalles
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "estado": "Evaluado"
    }