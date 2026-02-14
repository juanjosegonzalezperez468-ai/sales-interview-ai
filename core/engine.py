from datetime import datetime
from core.text_cleaner import clean_text
from core.counters import count_keywords

def evaluar_abierta(texto, reglas):
    palabras = texto.split()
    if len(palabras) < 15:
        return 0, "Respuesta demasiado corta (mínimo 15 palabras)."
    
    limpio = clean_text(texto)
    keywords_esperadas = reglas.get('palabras_clave', [])
    if not keywords_esperadas:
        return 100, "Sin keywords configuradas."
    
    encontradas = sum(1 for k in keywords_esperadas if k.lower() in limpio)
    score_abierta = (encontradas / len(keywords_esperadas)) * 100
    return score_abierta, f"Domina {encontradas} conceptos clave."

def evaluar_candidato_motor(respuestas_candidato, config_vacante):
    score_total = 0
    fortalezas = []
    debilidades = []
    detalles_ia = []
    
    preguntas_config = config_vacante.get('preguntas', [])

    def limpiar_local(texto):
        cambios = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u'}
        t = str(texto).lower().strip()
        for original, reemplazo in cambios.items():
            t = t.replace(original, reemplazo)
        return t

    for config in preguntas_config:
        if isinstance(config, str): continue
        
        q_id = config.get('id')
        rta_candidato = next((r['valor'] for r in respuestas_candidato if r['id'] == q_id), "")
        
        tipo = config.get('tipo')
        reglas = config.get('reglas', {})
        puntos_pregunta = 0

        # --- 1. EVALUACIÓN POR TIPO ---
        
        # TIPO: ABIERTA
        if tipo == "abierta":
            _, mensaje = evaluar_abierta(rta_candidato, reglas)
            detalles_ia.append(f"{config['texto']}: {mensaje}")
            puntos_pregunta = 0 

        # TIPO: BOOLEANA O SELECCIÓN MÚLTIPLE
        elif tipo in ["booleana", "multiple", "seleccion_multiple"]:
            valor_recibido = limpiar_local(rta_candidato)
            valor_esperado = limpiar_local(reglas.get('ideal', ''))
            
            puntos_pregunta = 100 if valor_recibido == valor_esperado else 0
            detalles_ia.append(f"{config['texto']}: {'Correcto' if puntos_pregunta == 100 else 'Incorrecto'}")

        # TIPO: ESCALAS (1-5 o 1-10) - ¡NUEVA LÓGICA PROPORCIONAL!
        elif tipo in ["escala_1_5", "escala_1_10"]:
            try:
                valor_n = float(rta_candidato)
                max_escala = 5 if tipo == "escala_1_5" else 10
                # Calculamos el porcentaje: (valor / max) * 100
                # Ejemplo: 8 en escala de 10 = 80 puntos.
                puntos_pregunta = (valor_n / max_escala) * 100
                detalles_ia.append(f"{config['texto']}: Calificó {valor_n}/{max_escala}")
            except:
                puntos_pregunta = 0
                detalles_ia.append(f"{config['texto']}: Dato de escala inválido")

        # --- 2. LÓGICA DE KNOCK-OUT ---
        # Si es crítico (knockout) y no obtuvo el puntaje ideal (100)
        # Nota: En escalas, podrías definir que KO es si saca menos de cierto número, 
        # pero por ahora mantenemos el estándar de "debe ser ideal".
        if config.get('knockout') is True and puntos_pregunta < 100:
            return {
                "score": 0,
                "veredicto": "DESCALIFICADO (KO)",
                "causal_ko": {
                    "pregunta": config['texto'],
                    "respuesta": rta_candidato,
                    "regla": f"Se esperaba cumplimiento total (Ideal: {reglas.get('ideal') or 'Máximo'})"
                },
                "resumen_ia": f"No cumple requisito crítico: {config['texto']}",
                "fecha_evaluacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        # --- 3. SUMA PONDERADA ---
        peso = config.get('peso', 0)
        score_total += (puntos_pregunta * (peso / 100))
        
        if puntos_pregunta >= 70:
            fortalezas.append(config['texto'])
        else:
            debilidades.append(config['texto'])

    # --- 4. RESULTADO FINAL ---
    if score_total >= 80:
        veredicto = "APROBADO"
    elif score_total >= 60:
        veredicto = "A CONSIDERAR"
    else:
        veredicto = "RECHAZADO"

    return {
        "fecha_evaluacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "score": round(score_total, 2),
        "veredicto": veredicto,
        "fortalezas": fortalezas,
        "debilidades": debilidades,
        "analisis_ia": " | ".join(detalles_ia), # Cambié resumen_ia por analisis_ia para que coincida con tu Dashboard
        "causal_ko": None 
    }