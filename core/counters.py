# Asegúrate de que el nombre sea 'count_keywords' (en plural)
def count_keywords(text: str):
    keywords = [
        "simetri", "estabilidad", "megas", "latencia", 
        "cobertura", "navegar", "instalacion", "beneficio",
        "fibra", "velocidad", "promocion"
    ]
    
    results = {}
    
    for word in keywords:
        count = text.count(word)
        results[word] = count
        
    return results