def calculate_score(stats):
    """
    Suma puntos según las palabras clave encontradas.
    Meta: 70 para aprobar. Máximo: 100.
    """
    score = 0
    
    # Pesos estratégicos
    pesos = {
        "latencia": 25,    # Crítico
        "simetria": 25,    # Crítico
        "fibra": 20,       # Importante
        "reuso": 15,       # Técnico
        "soporte": 15      # Comercial
    }
    
    for palabra, peso in pesos.items():
        # Si la palabra aparece al menos una vez, sumamos su peso
        if stats.get(palabra, 0) > 0:
            score += peso
            
    return min(score, 100)