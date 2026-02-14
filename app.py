import os
import time
import json
import logging
import uuid
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from supabase import create_client, Client
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()
app = Flask(__name__)

database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'una-clave-muy-secreta')

db = SQLAlchemy(app)
supabase: Client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# --- MODELOS ---
class Empresa(db.Model):
    __tablename__ = 'empresas'
    id = db.Column(UUID(as_uuid=True), primary_key=True)
    nombre_empresa = db.Column(db.Text, nullable=False)
    pais = db.Column(db.Text)
    industria = db.Column(db.Text)
    tamano = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.FetchedValue())
    vacantes = db.relationship('Vacante', backref='empresa_rel', cascade="all, delete-orphan")

class UsuarioEmpresa(db.Model):
    __tablename__ = 'usuarios_empresa'
    id = db.Column(db.String, primary_key=True)
    empresa_id = db.Column(UUID(as_uuid=True), db.ForeignKey('empresas.id', ondelete='CASCADE'))
    nombre_completo = db.Column(db.Text)
    email = db.Column(db.Text, unique=True, nullable=False)
    rol_en_empresa = db.Column(db.Text, default='admin')
    empresa = db.relationship('Empresa', backref='usuarios')

class Vacante(db.Model):
    __tablename__ = 'vacantes'
    id = db.Column(db.Integer, primary_key=True)
    id_vacante_publico = db.Column(db.String, nullable=False, unique=True)
    empresa_id = db.Column(UUID(as_uuid=True), db.ForeignKey('empresas.id', ondelete='CASCADE'))
    cargo = db.Column(db.String, nullable=False)
    preguntas = db.Column(db.JSON)
    activa = db.Column(db.Boolean, default=True)
    entrevistas_rel = db.relationship('Entrevista', backref='vacante_info', lazy=True, cascade="all, delete-orphan")

class Entrevista(db.Model):
    __tablename__ = 'entrevistas'
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vacante_id = db.Column(db.Integer, db.ForeignKey('vacantes.id', ondelete='CASCADE'), nullable=False)
    empresa_id = db.Column(UUID(as_uuid=True), db.ForeignKey('empresas.id', ondelete='CASCADE'), nullable=False)
    nombre_candidato = db.Column(db.Text, nullable=False)
    identificacion = db.Column(db.Text, nullable=False)
    score = db.Column(db.Float, default=0)
    veredicto = db.Column(db.Text)
    tag = db.Column(db.Text)
    analisis_ia = db.Column(db.Text) 
    comentarios_tecnicos = db.Column(db.Text)
    respuestas_detalle = db.Column(db.JSON)
    fecha = db.Column(db.DateTime, server_default=db.FetchedValue())

with app.app_context():
    db.create_all()

# ============================================
# MOTOR DE EVALUACIÓN SIN IA - SOLO LÓGICA
# ============================================

def generar_resumen_profesional(cargo, score_final, detalle, hubo_ko, motivo_ko):
    """
    Genera un resumen profesional basado en REGLAS LÓGICAS (sin IA).
    
    Args:
        cargo: Nombre del cargo
        score_final: Puntaje final (0-100)
        detalle: Lista de respuestas con puntos
        hubo_ko: Boolean si hubo knockout
        motivo_ko: Razón del knockout
    
    Returns:
        JSON string con resumen, fortalezas y riesgos
    """
    
    # 1. RESUMEN EJECUTIVO
    if hubo_ko:
        resumen = f"Candidato descartado automáticamente. {motivo_ko}. No cumple con requisitos críticos para el cargo de {cargo}."
    elif score_final >= 75:
        resumen = f"Candidato altamente calificado para {cargo}. Cumple con la mayoría de requisitos clave. Se recomienda entrevista prioritaria."
    elif score_final >= 40:
        resumen = f"Candidato con perfil moderado para {cargo}. Cumple requisitos básicos pero requiere validación adicional del reclutador."
    else:
        resumen = f"Candidato por debajo del umbral mínimo para {cargo}. No se recomienda continuar el proceso."
    
    # 2. FORTALEZAS (basadas en respuestas con puntaje alto)
    fortalezas = []
    for item in detalle:
        if item.get('tipo') == 'abierta':
            continue  # Ignoramos abiertas en análisis automático
        
        puntos_obtenidos = item.get('puntos', 0)
        puntos_posibles = item.get('peso', 1)
        
        if puntos_obtenidos == puntos_posibles and puntos_posibles > 0:
            # Extraer primera parte de la pregunta (más concisa)
            pregunta_corta = item['pregunta'][:50]
            fortalezas.append(f"✓ {pregunta_corta}")
    
    if not fortalezas:
        fortalezas = ["Proceso de evaluación completado"]
    
    # Limitar a 5 fortalezas
    fortalezas = fortalezas[:5]
    
    # 3. RIESGOS / DEBILIDADES (basadas en respuestas con puntaje 0)
    riesgos = []
    
    if hubo_ko:
        riesgos.append(f"⚠ {motivo_ko}")
    
    for item in detalle:
        if item.get('tipo') == 'abierta':
            continue
        
        puntos_obtenidos = item.get('puntos', 0)
        puntos_posibles = item.get('peso', 1)
        
        if puntos_obtenidos == 0 and puntos_posibles > 0:
            pregunta_corta = item['pregunta'][:50]
            riesgos.append(f"✗ {pregunta_corta}")
    
    if not riesgos:
        if score_final < 75:
            riesgos = ["Requiere validación manual del reclutador"]
        else:
            riesgos = ["Sin riesgos identificados"]
    
    # Limitar a 5 riesgos
    riesgos = riesgos[:5]
    
    # 4. RECOMENDACIÓN
    if hubo_ko:
        recomendacion = "❌ No continuar proceso"
    elif score_final >= 75:
        recomendacion = "✅ Agendar entrevista prioritaria"
    elif score_final >= 40:
        recomendacion = "⚠ Validar manualmente antes de decidir"
    else:
        recomendacion = "❌ Descartar"
    
    resultado = {
        "resumen": resumen,
        "fortalezas": fortalezas,
        "riesgos": riesgos,
        "recomendacion": recomendacion,
        "metodo": "Evaluación lógica automatizada"
    }
    
    return json.dumps(resultado, ensure_ascii=False)


@app.route('/')
def home():
    """Página principal (landing)"""
    return render_template('index.html')

@app.route('/como-funciona')
def como_funciona():
    """Página cómo funciona"""
    return render_template('como-funciona.html')

@app.route('/pricing')
def pricing():
    """Página de precios"""
    return render_template('pricing.html')

@app.route('/contacto')
def contacto():
    """Página de contacto"""
    return render_template('contacto.html')

# --- RUTAS PÚBLICAS (CANDIDATOS) ---

@app.route('/encuesta')
def index():
    id_seleccionada = request.args.get('vacante')
    if not id_seleccionada:
        return "<h1>Link incompleto</h1>", 400

    v = Vacante.query.filter_by(id_vacante_publico=id_seleccionada).first()
    if not v:
        return "<h1>Vacante no encontrada</h1>", 404

    preguntas_finales = v.preguntas if isinstance(v.preguntas, list) else []
    
    if isinstance(v.preguntas, dict) and 'preguntas' in v.preguntas:
        preguntas_finales = v.preguntas['preguntas']

    vacantes_dict = {
        str(v.id_vacante_publico): {
            "cargo": v.cargo,
            "preguntas": preguntas_finales
        }
    }

    return render_template('encuesta.html', 
                           vacantes=[v], 
                           vacantes_dict=vacantes_dict, 
                           id_seleccionada=id_seleccionada)


@app.route('/procesar', methods=['POST'])
def procesar():
    id_publico = request.form.get('id_vacante')
    nombre = request.form.get('nombre')
    cc = request.form.get('cc')

    v = Vacante.query.filter_by(id_vacante_publico=id_publico).first()
    if not v: 
        return "Vacante no encontrada", 404

    ids_q = request.form.getlist('preguntas_custom[]')
    vals_r = request.form.getlist('respuestas_custom[]')
    
    logger.info(f"🎯 Procesando candidato: {nombre} para cargo: {v.cargo}")
    
    # CÁLCULO DE PESO TOTAL (solo preguntas cerradas)
    peso_total_posible = sum(
        float(p.get('peso', 0)) 
        for p in v.preguntas 
        if p.get('tipo') in ['si_no', 'multiple']
    )
    
    logger.info(f"📊 Peso total calificable: {peso_total_posible}")
    
    puntos_brutos_acumulados = 0
    hubo_ko = False
    motivo_descarte = ""
    detalle = []

    # BUCLE DE CALIFICACIÓN
    for i in range(len(ids_q)):
        p_orig = next((p for p in v.preguntas if p['id'] == ids_q[i]), None)
        if not p_orig: 
            continue

        respuesta_user = vals_r[i].strip()
        peso_pregunta = float(p_orig.get('peso', 0))
        tipo = p_orig.get('tipo')
        es_ko = p_orig.get('knockout', False)
        reglas = p_orig.get('reglas', {})
        ideal = str(reglas.get('ideal', '')).strip()

        puntos_obtenidos = 0
        
        # CALIFICACIÓN SOLO PARA CERRADAS (Sí/No y Múltiple)
        if tipo in ['si_no', 'multiple']:
            if respuesta_user.lower() == ideal.lower():
                puntos_obtenidos = peso_pregunta
                logger.info(f"✅ Pregunta {p_orig['id']}: {peso_pregunta} pts")
            else:
                logger.info(f"❌ Pregunta {p_orig['id']}: 0 pts (esperaba '{ideal}', recibió '{respuesta_user}')")
                if es_ko:
                    hubo_ko = True
                    motivo_descarte = f"No cumple: {p_orig['texto']}"
                    logger.warning(f"🚫 KNOCKOUT activado: {motivo_descarte}")
        
        # PREGUNTAS ABIERTAS: Solo se guardan para lectura del reclutador
        elif tipo == 'abierta':
            logger.info(f"📝 Pregunta abierta {p_orig['id']}: Guardada para revisión manual")
            # No suma puntos, solo se guarda la respuesta
        
        puntos_brutos_acumulados += puntos_obtenidos
        
        detalle.append({
            "pregunta": p_orig['texto'],
            "respuesta": respuesta_user,
            "puntos": puntos_obtenidos,
            "peso": peso_pregunta,
            "tipo": tipo
        })
    
    # CALCULAR SCORE FINAL
    if peso_total_posible == 0:
        score_final = 0
    else:
        score_final = (puntos_brutos_acumulados / peso_total_posible) * 100
    
    score_final = round(score_final, 1)
    
    logger.info(f"💯 Score final: {score_final}% ({puntos_brutos_acumulados}/{peso_total_posible})")

    # GENERAR RESUMEN PROFESIONAL (sin IA)
    analisis_json = generar_resumen_profesional(
        cargo=v.cargo,
        score_final=score_final,
        detalle=detalle,
        hubo_ko=hubo_ko,
        motivo_ko=motivo_descarte
    )

    # DETERMINAR VEREDICTO
    if hubo_ko:
        veredicto = "DESCARTADO (KO)"
        tag = "🔴"
    elif score_final >= 75:
        veredicto = "RECOMENDADO"
        tag = "🟢"
    elif score_final >= 40:
        veredicto = "REVISAR"
        tag = "🟡"
    else:
        veredicto = "NO APTO"
        tag = "🔴"

    # GUARDAR EN BASE DE DATOS
    nueva_entrevista = Entrevista(
        vacante_id=v.id,
        empresa_id=v.empresa_id,
        nombre_candidato=nombre,
        identificacion=cc,
        score=score_final,
        veredicto=veredicto,
        tag=tag,
        comentarios_tecnicos=motivo_descarte,
        respuestas_detalle=detalle,
        analisis_ia=analisis_json
    )

    try:
        db.session.add(nueva_entrevista)
        db.session.commit()
        logger.info(f"✅ Candidato guardado: {nombre} - Score: {score_final}% - {veredicto}")
        return render_template('gracias.html')
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Error guardando: {e}")
        return f"Error guardando: {e}", 500

# --- DASHBOARD ---

@app.route('/dashboard')
def dashboard():
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    emp_id_str = session.get('empresa_id')
    
    try:
        emp_id = uuid.UUID(emp_id_str)
    except (ValueError, AttributeError, TypeError):
        logger.error(f"❌ empresa_id inválido: {emp_id_str}")
        session.clear()
        return redirect(url_for('login'))
    
    usuario = UsuarioEmpresa.query.get(user_id)
    empresa = Empresa.query.get(emp_id)

    if not usuario or not empresa:
        session.clear()
        return redirect(url_for('login'))

    vacantes = Vacante.query.filter_by(empresa_id=emp_id).all()
    resultados = Entrevista.query.filter_by(empresa_id=emp_id).order_by(Entrevista.fecha.desc()).all()

    candidatos_cards = []
    for e in resultados:
        v_rel = next((v for v in vacantes if v.id == e.vacante_id), None)
        candidatos_cards.append({
            "id": e.id,
            "nombre": e.nombre_candidato,
            "cargo": v_rel.cargo if v_rel else "N/A",
            "score": e.score,
            "veredicto": e.veredicto,
            "tag": e.tag,
            "fecha": e.fecha.strftime('%d.%m.%Y') if e.fecha else "N/A",
            "analisis_ia": e.analisis_ia,
            "respuestas_detalle": e.respuestas_detalle
        })

    return render_template("dashboard.html", 
                           usuario=usuario,
                           empresa=empresa,
                           entrevistas=candidatos_cards, 
                           vacantes=vacantes, 
                           total_c=len(resultados), 
                           total_v=len(vacantes),
                           nombre_empresa=empresa.nombre_empresa)

@app.route('/gestionar_vacantes')
def gestionar_vacantes():
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    
    emp_id_str = session.get('empresa_id')
    
    try:
        emp_id = uuid.UUID(emp_id_str)
    except (ValueError, AttributeError, TypeError):
        session.clear()
        return redirect(url_for('login'))
    
    vacantes = Vacante.query.filter_by(empresa_id=emp_id).all()
    
    return render_template('lista_vacantes.html', vacantes=vacantes)

@app.route('/nueva_vacante', methods=['GET', 'POST'])
def nueva_vacante():
    if not session.get('logeado'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        cargo = request.form.get('cargo')
        emp_id_str = session.get('empresa_id')
        
        try:
            empresa_id = uuid.UUID(emp_id_str)
        except (ValueError, AttributeError, TypeError):
            return "Error: Sesión inválida", 400
        
        id_publico = f"JOB-{int(time.time())}"

        textos = request.form.getlist('p_texto[]')
        tipos = request.form.getlist('p_tipo[]')
        pesos = request.form.getlist('p_peso[]')
        reglas = request.form.getlist('p_regla[]')
        opciones_todas = request.form.getlist('p_opciones_lista[]')

        nuevas_preguntas = []
        opcion_idx = 0
        
        for i in range(len(textos)):
            t = tipos[i]
            regla_dict = {}
            
            if t == 'multiple':
                opciones_pregunta = opciones_todas[opcion_idx : opcion_idx + 4]
                regla_dict = {
                    "opciones": [o for o in opciones_pregunta if o],
                    "ideal": reglas[i]
                }
                opcion_idx += 4
            elif t == 'abierta':
                regla_dict = {"palabras_clave": reglas[i]}
            else:
                regla_dict = {"ideal": reglas[i]}

            nuevas_preguntas.append({
                "id": f"q{i+1}",
                "texto": textos[i],
                "tipo": t,
                "reglas": regla_dict,
                "peso": int(pesos[i]) if pesos[i] else 0,
                "knockout": str(i) in request.form.getlist('p_ko[]')
            })

        nueva = Vacante(
            cargo=cargo,
            id_vacante_publico=id_publico,
            empresa_id=empresa_id,
            preguntas=nuevas_preguntas
        )
        
        db.session.add(nueva)
        db.session.commit()
        
        return redirect(url_for('gestionar_vacantes'))

    return render_template('nueva_vacante.html')

@app.route('/vacante_lista/<id_publico>')
def vacante_lista(id_publico):
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    
    v = Vacante.query.filter_by(id_vacante_publico=id_publico).first()
    if not v: 
        return "No encontrada", 404
    
    link = f"{request.url_root}encuesta?vacante={id_publico}"
    
    return render_template('vacante_lista.html', vacante=v, link=link)

@app.route('/editar_vacante/<id_publico>', methods=['GET', 'POST'])
def editar_vacante(id_publico):
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    
    v = Vacante.query.filter_by(id_vacante_publico=id_publico).first()
    if not v: 
        return "No encontrada", 404

    if request.method == 'POST':
        v.cargo = request.form.get('cargo')
        
        ids = request.form.getlist('p_id[]')
        textos = request.form.getlist('p_texto[]')
        tipos = request.form.getlist('p_tipo[]')
        pesos = request.form.getlist('p_peso[]')
        reglas = request.form.getlist('p_regla[]')
        kos = request.form.getlist('p_ko[]')

        nuevas_preguntas = []
        for i in range(len(textos)):
            regla_obj = {"ideal": reglas[i]} if tipos[i] == "si_no" else {"palabras_clave": reglas[i]}
            
            nuevas_preguntas.append({
                "id": ids[i],
                "texto": textos[i],
                "tipo": tipos[i],
                "peso": int(pesos[i]),
                "knockout": str(i) in kos,
                "reglas": regla_obj
            })
        
        v.preguntas = nuevas_preguntas
        db.session.commit()
        return redirect(url_for('gestionar_vacantes'))

    return render_template('editar_vacante.html', vacante=v)

@app.route('/marketplace')
def marketplace():
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    return render_template('marketplace.html')

@app.route('/clonar_plantilla/<plantilla_id>')
def clonar_plantilla(plantilla_id):
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    
    # Biblioteca de plantillas profesionales
    biblioteca = {
        'call_center_ventas': {
            'cargo': 'Agente de Ventas Call Center (Sin Experiencia)',
            'preguntas': [
                {"id": "q1", "texto": "¿Tienes disponibilidad para trabajar de lunes a sábado en turnos rotativos?", "tipo": "si_no", "peso": 15, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q2", "texto": "¿Cuentas con computador e internet estable en casa?", "tipo": "si_no", "peso": 15, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q3", "texto": "¿Qué nivel de estudios has completado?", "tipo": "multiple", "peso": 10, "knockout": False, "reglas": {"opciones": ["Primaria", "Bachillerato completo", "Técnico/Tecnólogo", "Universidad"], "ideal": "Bachillerato completo"}},
                {"id": "q4", "texto": "¿Has trabajado antes atendiendo público o clientes?", "tipo": "si_no", "peso": 20, "knockout": False, "reglas": {"ideal": "si"}},
                {"id": "q5", "texto": "Si un cliente te dice 'no me interesa' y cuelga, ¿qué harías?", "tipo": "multiple", "peso": 25, "knockout": False, "reglas": {"opciones": ["Me sentiría mal y no volvería a llamar", "Registraría la llamada y continuaría con el siguiente", "Llamaría de nuevo hasta que acepte", "Depende de mi ánimo"], "ideal": "Registraría la llamada y continuaría con el siguiente"}},
                {"id": "q6", "texto": "¿Cuándo puedes iniciar?", "tipo": "multiple", "peso": 10, "knockout": False, "reglas": {"opciones": ["Inmediatamente (1-3 días)", "La próxima semana", "En 2-4 semanas", "Más de un mes"], "ideal": "Inmediatamente (1-3 días)"}},
                {"id": "q7", "texto": "Cuéntanos por qué te interesa trabajar en ventas telefónicas", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}}
            ]
        },
        'operativo_express': {
            'cargo': 'Filtro Express (Operativo)',
            'preguntas': [
                {"id": "q1", "texto": "¿Vives en la ciudad de la vacante?", "tipo": "si_no", "peso": 10, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q2", "texto": "¿Tienes experiencia en el cargo?", "tipo": "si_no", "peso": 15, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q3", "texto": "¿Dispones del horario requerido?", "tipo": "si_no", "peso": 15, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q4", "texto": "¿Aceptas el salario ofrecido?", "tipo": "si_no", "peso": 15, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q5", "texto": "¿Tienes documentos al día?", "tipo": "si_no", "peso": 10, "knockout": False, "reglas": {"ideal": "si"}},
                {"id": "q6", "texto": "¿Tienes disponibilidad para viajar?", "tipo": "si_no", "peso": 10, "knockout": False, "reglas": {"ideal": "si"}},
                {"id": "q7", "texto": "Describe brevemente tu última función", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}},
                {"id": "q8", "texto": "¿Cuándo puedes iniciar?", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}}
            ]
        }
    }

    datos = biblioteca.get(plantilla_id)
    if not datos:
        return "Plantilla no encontrada", 404

    emp_id_str = session.get('empresa_id')
    
    try:
        empresa_id = uuid.UUID(emp_id_str)
    except (ValueError, AttributeError, TypeError):
        return "Error: Sesión inválida", 400

    id_u = f"JOB-{plantilla_id.upper()[:3]}-{int(time.time())}"

    nueva_v = Vacante(
        id_vacante_publico=id_u,
        empresa_id=empresa_id,
        cargo=datos['cargo'], 
        preguntas=datos['preguntas'],
        activa=True 
    )
    
    try:
        db.session.add(nueva_v)
        db.session.commit()
        logger.info(f"✅ Vacante clonada: {id_u}")
        return redirect(url_for('vacante_lista', id_publico=id_u))
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Error: {e}")
        return f"Error: {e}", 500

# --- AUTH ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            res = supabase.auth.sign_in_with_password({
                "email": email, 
                "password": password
            })
            
            if res.user:
                u_db = UsuarioEmpresa.query.filter_by(id=res.user.id).first()
                
                if u_db:
                    session.update({
                        'logeado': True,
                        'user_id': res.user.id,
                        'empresa_id': str(u_db.empresa_id),
                        'nombre_empresa': u_db.empresa.nombre_empresa if u_db.empresa else "Mi Empresa"
                    })
                    
                    logger.info(f"✅ Login: {email}")
                    return redirect(url_for('dashboard'))
                else:
                    return render_template('login.html', 
                        error="Usuario no vinculado.")
                    
        except Exception as e: 
            logger.error(f"❌ Login error: {e}")
            return render_template('login.html', 
                error="Credenciales incorrectas.")

    return render_template('login.html', error=None)

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre_usuario = request.form.get('nombre_usuario')
        email = request.form.get('email')
        password = request.form.get('password')
        nombre_empresa = request.form.get('nombre_empresa')
        pais = request.form.get('pais')
        industria = request.form.get('industria')
        tamano_empresa = request.form.get('tamano') or "1-10"
        cargo_inicial = request.form.get('cargo_inicial')

        try:
            auth_res = supabase.auth.sign_up({"email": email, "password": password})
            
            if auth_res.user:
                user_id = auth_res.user.id
                empresa_uuid = uuid.uuid4()
                
                nueva_empresa = Empresa(
                    id=empresa_uuid, 
                    nombre_empresa=nombre_empresa,
                    pais=pais,
                    industria=industria,
                    tamano=tamano_empresa
                )
                db.session.add(nueva_empresa)
                db.session.flush()

                nuevo_usuario = UsuarioEmpresa(
                    id=user_id,
                    email=email,
                    nombre_completo=nombre_usuario,
                    empresa_id=empresa_uuid,
                    rol_en_empresa='admin'
                )
                db.session.add(nuevo_usuario)

                cargo_display = cargo_inicial if cargo_inicial else "Asesor Comercial"
                id_v_publico = f"JOB-{int(time.time())}"
                
                preguntas_base = [
                    {"id": "q1", "texto": "¿Tienes experiencia previa en ventas?", "tipo": "si_no", "peso": 20, "knockout": True, "reglas": {"ideal": "si"}},
                    {"id": "q2", "texto": "¿Cuentas con vehículo propio?", "tipo": "si_no", "peso": 15, "knockout": False, "reglas": {"ideal": "si"}},
                    {"id": "q3", "texto": "¿Disponibilidad para viajar?", "tipo": "si_no", "peso": 10, "knockout": False, "reglas": {"ideal": "si"}},
                    {"id": "q4", "texto": "Describe tu logro comercial más relevante", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}},
                    {"id": "q5", "texto": "¿Cuándo puedes iniciar?", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}}
                ]
                
                primera_vacante = Vacante(
                    cargo=cargo_display,
                    id_vacante_publico=id_v_publico,
                    empresa_id=empresa_uuid,
                    preguntas=preguntas_base,
                    activa=True
                )
                db.session.add(primera_vacante)
                db.session.commit()
                
                session.update({
                    'logeado': True,
                    'user_id': user_id,
                    'empresa_id': str(empresa_uuid),
                    'nombre_empresa': nombre_empresa
                })
                
                logger.info(f"🚀 Registro: {nombre_empresa}")
                return redirect(url_for('dashboard'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ Registro error: {e}")
            return f"Error: {e}", 400

    return render_template('registro.html')

@app.route('/eliminar_candidato/<id>', methods=['POST'])
def eliminar_candidato(id):
    if not session.get('logeado'): 
        return jsonify({"success": False}), 401
    
    emp_id_str = session.get('empresa_id')
    
    try:
        emp_id = uuid.UUID(emp_id_str)
    except:
        return jsonify({"success": False}), 400
    
    candidato = Entrevista.query.get(id)
    
    if candidato and candidato.empresa_id == emp_id:
        try:
            db.session.delete(candidato)
            db.session.commit()
            return jsonify({"success": True})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False})
    
    return jsonify({"success": False})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/candidato/<id>')
def api_candidato(id):
    """API para obtener datos completos del candidato para el modal"""
    if not session.get('logeado'):
        return jsonify({"error": "No autorizado"}), 401
    
    candidato = Entrevista.query.get(id)
    
    if not candidato:
        return jsonify({"error": "Candidato no encontrado"}), 404
    
    # Verificar que pertenece a la empresa del usuario
    emp_id_str = session.get('empresa_id')
    try:
        emp_id = uuid.UUID(emp_id_str)
        if candidato.empresa_id != emp_id:
            return jsonify({"error": "No autorizado"}), 403
    except:
        return jsonify({"error": "Sesión inválida"}), 400
    
    # Obtener nombre del cargo
    vacante = Vacante.query.get(candidato.vacante_id)
    cargo = vacante.cargo if vacante else "N/A"
    
    # Parsear análisis
    try:
        analisis = json.loads(candidato.analisis_ia)
    except:
        analisis = {
            "resumen": "Análisis no disponible",
            "fortalezas": [],
            "riesgos": [],
            "recomendacion": ""
        }
    
    return jsonify({
        "nombre": candidato.nombre_candidato,
        "identificacion": candidato.identificacion,
        "cargo": cargo,
        "score": candidato.score,
        "veredicto": candidato.veredicto,
        "tag": candidato.tag,
        "fecha": candidato.fecha.strftime('%d/%m/%Y %H:%M') if candidato.fecha else "N/A",
        "analisis": analisis,
        "respuestas": candidato.respuestas_detalle or []
    })

if __name__ == '__main__':
    app.run(debug=True)