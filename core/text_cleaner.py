import re
import unicodedata

def clean_text(text: str) -> str:
    # 1. Convertir a minúsculas
    text = text.lower()
    
    # 2. Eliminar acentos y tildes (normalización)
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    
    # 3. Eliminar caracteres especiales y números (opcional, dejamos solo letras y espacios)
    text = re.sub(r'[^a-z\s]', '', text)
    
    # 4. Eliminar espacios extra
    text = " ".join(text.split())
    
    return text