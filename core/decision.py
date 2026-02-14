def make_decision(score: int):
    # Definimos los umbrales (niveles)
    if score >= 80:
        return "CONTRATACIÓN INMEDIATA (Excelente manejo técnico)"
    elif score >= 60:
        return "SEGUNDA ENTREVISTA (Buen potencial, requiere pulir)"
    elif score >= 40:
        return "EN ESPERA (Conocimiento básico)"
    else:
        return "DESCARTADO (No conoce el producto)"