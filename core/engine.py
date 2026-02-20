from datetime import datetime



def evaluar_candidato_motor_supabase(respuestas_candidato, config_preguntas):

    # 1. Estructura de Dimensiones

    categorias = {

        "Tecnica": {"puntos": 0},

        "Experiencia": {"puntos": 0},

        "Blandas": {"puntos": 0},

        "Ajuste": {"puntos": 0}

    }

    

    score_total = 0

    fortalezas = []

    debilidades = []

    detalles_ia = [] 



    def limpiar_local(texto):

        t = str(texto).lower().strip()

        for a, b in {'á':'a','é':'e','í':'i','ó':'o','ú':'u'}.items(): t = t.replace(a, b)

        return t



    for config in config_preguntas:

        q_id = config.get('id')

        peso = config.get('peso', 0)

        tipo = config.get('tipo')

        cat = config.get('categoria', 'Ajuste')

        

        # Buscar respuesta del candidato

        rta_candidato = next((r['valor'] for r in respuestas_candidato if str(r['id']) == str(q_id)), "")

        puntos_pregunta = 0



        # --- EVALUACIÓN LÓGICA (Ajustada a tu tipo "si_no") ---

        if tipo in ["si_no", "booleana", "multiple", "seleccion_multiple"]:

            ideal = config.get('reglas', {}).get('ideal', '')

            puntos_pregunta = 100 if limpiar_local(rta_candidato) == limpiar_local(ideal) else 0

            detalles_ia.append(f"{config.get('texto')}: {'✅' if puntos_pregunta == 100 else '❌'}")



        elif "escala" in tipo:

            try:

                max_e = 5 if "5" in tipo else 10

                puntos_pregunta = (float(rta_candidato) / max_e) * 100

                detalles_ia.append(f"{config.get('texto')}: {rta_candidato}/{max_e}")

            except: puntos_pregunta = 0



        # --- LÓGICA DE KNOCK-OUT (KO) ---

        if config.get('knockout') is True and puntos_pregunta < 100:

            return {

                "score": 0,

                "score_ia": 0,

                "veredicto": "DESCALIFICADO (KO)",

                "fortalezas": "",

                "debilidades": config.get('texto_corto') or config.get('texto'),

                "analisis_ia": f"🚫 KO: No cumple con: {config.get('texto')}",

                "estado": "Rechazado",

                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            }



        # --- SUMA POR CATEGORÍA Y TOTAL ---

        if cat in categorias:

            categorias[cat]["puntos"] += (puntos_pregunta * (peso / 100))

        

        score_total += (puntos_pregunta * (peso / 100))

        

        # --- FORTALEZAS Y DEBILIDADES ---

        texto_item = config.get('texto_corto') or config.get('texto')

        if puntos_pregunta >= 80:

            if len(fortalezas) < 2: fortalezas.append(texto_item)

        elif puntos_pregunta <= 40:

            if len(debilidades) < 2: debilidades.append(texto_item)



    # --- RECOMENDACIÓN FINAL ---

    if score_total >= 85: rec = "⭐ Perfil sobresaliente."

    elif score_total >= 60: rec = "🔍 Perfil promedio."

    else: rec = "🚫 No cumple mínimos."



    # Formatear el análisis para la columna 'analisis_ia'

    desglose = f"T:{round(categorias['Tecnica']['puntos'],1)}% E:{round(categorias['Experiencia']['puntos'],1)}% B:{round(categorias['Blandas']['puntos'],1)}% A:{round(categorias['Ajuste']['puntos'],1)}%"

    analisis_final = f"{rec} | {desglose} | " + " | ".join(detalles_ia)



    return {

        "score": round(score_total, 2),

        "score_ia": round(score_total, 2),

        "veredicto": "APROBADO" if score_total >= 70 else "RECHAZADO",

        "fortalezas": ", ".join(fortalezas),

        "debilidades": ", ".join(debilidades),

        "analisis_ia": analisis_final,

        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

        "estado": "Evaluado"

    }