"""
calculadora/logic.py
Lógica de cálculos para la calculadora de costos
"""

# ============================================
# CONFIGURACIÓN DE BENCHMARKS Y CONSTANTES
# ============================================

# Benchmarks basados en estudios reales
BENCHMARK_MIN_POR_CV = 7  # SHRM 2022
BENCHMARK_TASA_ERROR = 0.12  # Empresas con scoring (LinkedIn 2023)
BENCHMARK_PERSONAS = 2  # Promedio industria
BENCHMARK_COSTO_MALA_CONTRATACION = 0.30  # 30% salario anual (HBR)

# Mejoras estimadas con automatización
REDUCCION_TIEMPO = 0.70  # 70% menos tiempo
MEJORA_CALIDAD = 0.60  # 60% menos errores
AUMENTO_CAPACIDAD = 2.33  # 233% más candidatos

# Mapeo de respuestas del formulario
MAPEO_VACANTES = {
    "1-3": 2,
    "4-10": 7,
    "11-25": 18,
    "26-50": 38,
    "+50": 60
}

MAPEO_CANDIDATOS = {
    "1-20": 10,
    "21-50": 35,
    "51-100": 75,
    "101-200": 150,
    "+200": 250
}

MAPEO_TIEMPO_CV = {
    "1-3 min": 2,
    "4-7 min": 5.5,
    "8-15 min": 11.5,
    "+15 min": 20
}

MAPEO_PERSONAS = {
    "Solo yo": 1,
    "2-3": 2.5,
    "4-6": 5,
    "+7": 8
}

MAPEO_SALARIO = {
    "$2-5k/mes": 3500,
    "$6-10k": 8000,
    "$11-20k": 15000,
    "+$20k": 25000
}

MAPEO_TASA_ERROR = {
    "Casi nunca": 0.05,
    "1 de cada 10": 0.10,
    "3 de cada 10": 0.30,
    "5 de cada 10": 0.50,
    "Más de la mitad": 0.70
}


def calcular_metricas(respuestas: dict) -> dict:
    """
    Calcula todas las métricas del diagnóstico basado en las respuestas.
    
    Args:
        respuestas: dict con las respuestas del formulario
    
    Returns:
        dict con todas las métricas calculadas
    """
    
    # Extraer y mapear valores
    vacantes_activas_num = MAPEO_VACANTES.get(respuestas['vacantes_activas'], 7)
    candidatos_por_vacante_num = MAPEO_CANDIDATOS.get(respuestas['candidatos_por_vacante'], 35)
    tiempo_por_cv_min = MAPEO_TIEMPO_CV.get(respuestas['tiempo_por_cv'], 5.5)
    personas_proceso_num = MAPEO_PERSONAS.get(respuestas['personas_proceso'], 2.5)
    salario_mensual = MAPEO_SALARIO.get(respuestas['rango_salarial'], 8000)
    tasa_error = MAPEO_TASA_ERROR.get(respuestas['frecuencia_error'], 0.10)
    
    # 1. CALCULAR VOLUMEN Y TIEMPO
    total_cvs_mes = vacantes_activas_num * candidatos_por_vacante_num
    tiempo_total_min = total_cvs_mes * tiempo_por_cv_min * personas_proceso_num
    horas_mensuales = round(tiempo_total_min / 60, 2)
    
    # 2. CALCULAR COSTO OPERATIVO
    costo_hora_empleado = salario_mensual / 160
    costo_operativo_mensual = round(costo_hora_empleado * horas_mensuales, 2)
    
    # 3. COSTO DE MALA CONTRATACIÓN
    salario_anual_contratado = salario_mensual * 0.8 * 12
    costo_mala_contratacion = round(salario_anual_contratado * BENCHMARK_COSTO_MALA_CONTRATACION, 2)
    costo_anual_errores = round(costo_mala_contratacion * tasa_error * vacantes_activas_num, 2)
    
    # 4. CALCULAR EFICIENCIA
    eficiencia_tiempo = min(100, round((BENCHMARK_MIN_POR_CV / tiempo_por_cv_min) * 100, 2))
    eficiencia_personas = min(100, round((BENCHMARK_PERSONAS / personas_proceso_num) * 100, 2))
    eficiencia_calidad = max(0, round((1 - tasa_error) * 100, 2))
    eficiencia_total = round((eficiencia_tiempo + eficiencia_personas + eficiencia_calidad) / 3, 2)
    
    # 5. BENCHMARK COMPARATIVO
    diferencia_tiempo = round(((tiempo_por_cv_min - BENCHMARK_MIN_POR_CV) / BENCHMARK_MIN_POR_CV) * 100, 2)
    diferencia_error = round(((tasa_error - BENCHMARK_TASA_ERROR) / BENCHMARK_TASA_ERROR) * 100, 2)
    
    # 6. IDENTIFICAR CUELLO DE BOTELLA
    if tiempo_por_cv_min > 10:
        cuello_botella = "Revisión manual de CVs consume demasiado tiempo por candidato"
    elif personas_proceso_num > 3:
        cuello_botella = "Demasiadas personas involucradas ralentizan la toma de decisiones"
    elif tasa_error > 0.20:
        cuello_botella = "Alta tasa de error en selección manual sin scoring objetivo"
    else:
        cuello_botella = "Volumen de candidatos supera la capacidad de revisión del equipo"
    
    # 7. PROYECCIÓN OPTIMIZADA
    horas_optimizadas = round(horas_mensuales * (1 - REDUCCION_TIEMPO), 2)
    costo_optimizado_mensual = round(costo_operativo_mensual * (1 - REDUCCION_TIEMPO), 2)
    tasa_error_optimizada = round(tasa_error * (1 - MEJORA_CALIDAD), 2)
    capacidad_aumentada = int(total_cvs_mes * AUMENTO_CAPACIDAD)
    
    # 8. AHORRO POTENCIAL
    ahorro_mensual = round(costo_operativo_mensual - costo_optimizado_mensual, 2)
    ahorro_anual = round(ahorro_mensual * 12, 2)
    reduccion_errores_anual = round(costo_anual_errores * MEJORA_CALIDAD, 2)
    roi_mensual = round(ahorro_mensual + (reduccion_errores_anual / 12), 2)
    
    return {
        'vacantes_activas_num': vacantes_activas_num,
        'candidatos_por_vacante_num': candidatos_por_vacante_num,
        'tiempo_por_cv_min': tiempo_por_cv_min,
        'personas_proceso_num': personas_proceso_num,
        'salario_mensual_promedio': salario_mensual,
        'tasa_error_decimal': tasa_error,
        'total_cvs_mes': total_cvs_mes,
        'horas_mensuales': horas_mensuales,
        'costo_operativo_mensual': costo_operativo_mensual,
        'costo_mala_contratacion': costo_mala_contratacion,
        'costo_anual_errores': costo_anual_errores,
        'eficiencia_tiempo': eficiencia_tiempo,
        'eficiencia_personas': eficiencia_personas,
        'eficiencia_calidad': eficiencia_calidad,
        'eficiencia_total': eficiencia_total,
        'diferencia_vs_benchmark_tiempo': diferencia_tiempo,
        'diferencia_vs_benchmark_error': diferencia_error,
        'cuello_botella': cuello_botella,
        'horas_optimizadas': horas_optimizadas,
        'costo_optimizado_mensual': costo_optimizado_mensual,
        'tasa_error_optimizada': tasa_error_optimizada,
        'capacidad_aumentada': capacidad_aumentada,
        'ahorro_mensual': ahorro_mensual,
        'ahorro_anual': ahorro_anual,
        'roi_mensual': roi_mensual
    }


def generar_mensaje_benchmark(diferencia_tiempo: float, diferencia_error: float) -> dict:
    """
    Genera mensajes personalizados comparando con benchmark.
    """
    mensajes = {
        'tiempo': '',
        'error': '',
        'nivel_urgencia': 'medio'
    }
    
    # Mensaje de tiempo
    if diferencia_tiempo > 50:
        mensajes['tiempo'] = f"⚠️ Crítico: Estás invirtiendo {int(diferencia_tiempo)}% más tiempo que empresas optimizadas"
        mensajes['nivel_urgencia'] = 'alto'
    elif diferencia_tiempo > 30:
        mensajes['tiempo'] = f"⚠️ Estás invirtiendo {int(diferencia_tiempo)}% más tiempo que el benchmark de industria"
        mensajes['nivel_urgencia'] = 'alto'
    elif diferencia_tiempo > 0:
        mensajes['tiempo'] = f"📊 Estás {int(diferencia_tiempo)}% por encima del promedio"
    else:
        mensajes['tiempo'] = f"✅ Tu tiempo de revisión está por debajo del benchmark"
    
    # Mensaje de error
    if diferencia_error > 100:
        mensajes['error'] = f"🔴 Riesgo crítico: Tu tasa de error es {int(diferencia_error)}% mayor que empresas con scoring"
        mensajes['nivel_urgencia'] = 'alto'
    elif diferencia_error > 50:
        mensajes['error'] = f"⚠️ Riesgo {round(diferencia_error/50, 1)}x mayor de mala contratación vs benchmark"
    elif diferencia_error > 0:
        mensajes['error'] = f"📊 Tasa de error {int(diferencia_error)}% por encima del benchmark"
    else:
        mensajes['error'] = f"✅ Tu tasa de error está controlada"
    
    return mensajes