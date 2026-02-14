import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

print("=" * 50)
print("DIAGNÓSTICO DE CONEXIÓN A SUPABASE")
print("=" * 50)

# 1. Verificar que exista el archivo .env
if os.path.exists('.env'):
    print("✅ Archivo .env encontrado")
else:
    print("❌ Archivo .env NO encontrado")
    print("   → Crea un archivo .env en la raíz del proyecto")

# 2. Verificar DATABASE_URL
database_url = os.getenv('DATABASE_URL')
if database_url:
    print(f"✅ DATABASE_URL encontrada")
    # Mostrar solo parte de la URL por seguridad
    if database_url.startswith('postgres'):
        print(f"   → Inicia con: {database_url[:20]}...")
    else:
        print(f"   ⚠️  No inicia con 'postgres://'")
else:
    print("❌ DATABASE_URL NO encontrada")
    print("   → Agrega DATABASE_URL en tu archivo .env")

# 3. Verificar SUPABASE_URL
supabase_url = os.getenv('SUPABASE_URL')
if supabase_url:
    print(f"✅ SUPABASE_URL encontrada: {supabase_url}")
else:
    print("❌ SUPABASE_URL NO encontrada")

# 4. Verificar SUPABASE_KEY
supabase_key = os.getenv('SUPABASE_KEY')
if supabase_key:
    print(f"✅ SUPABASE_KEY encontrada (primeros 20 chars): {supabase_key[:20]}...")
else:
    print("❌ SUPABASE_KEY NO encontrada")

# 5. Verificar GEMINI_API_KEY
gemini_key = os.getenv('GEMINI_API_KEY')
if gemini_key:
    print(f"✅ GEMINI_API_KEY encontrada")
else:
    print("❌ GEMINI_API_KEY NO encontrada")

# 6. Test de conexión a internet
print("\n" + "=" * 50)
print("TEST DE CONEXIÓN A INTERNET")
print("=" * 50)

try:
    import socket
    socket.create_connection(("8.8.8.8", 53), timeout=3)
    print("✅ Conexión a internet OK")
except OSError:
    print("❌ Sin conexión a internet")

# 7. Test de resolución DNS de Supabase
print("\n" + "=" * 50)
print("TEST DE RESOLUCIÓN DNS")
print("=" * 50)

try:
    import socket
    #host = "db.haifwpumfswqbsvcrxkx.supabase.co"
    ip = socket.gethostbyname(host)
    print(f"✅ Host {host} resuelto a IP: {ip}")
except socket.gaierror:
    print(f"❌ No se pudo resolver el host: {host}")
    print("   → Puede ser un problema de DNS o conexión")

print("\n" + "=" * 50)
print("FIN DEL DIAGNÓSTICO")
print("=" * 50)