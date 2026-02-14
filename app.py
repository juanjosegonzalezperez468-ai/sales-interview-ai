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

def generar_resumen_profesional(cargo, score_final, detalle, hubo_ko, motivo_ko):
    if hubo_ko:
        resumen = f"Candidato descartado automáticamente. {motivo_ko}."
    elif score_final >= 75:
        resumen = f"Candidato altamente calificado para {cargo}."
    elif score_final >= 40:
        resumen = f"Candidato con perfil moderado para {cargo}."
    else:
        resumen = f"Candidato por debajo del umbral mínimo para {cargo}."
    
    fortalezas = []
    for item in detalle:
        if item.get('tipo') == 'abierta':
            continue
        puntos_obtenidos = item.get('puntos', 0)
        puntos_posibles = item.get('peso', 1)
        if puntos_obtenidos == puntos_posibles and puntos_posibles > 0:
            pregunta_corta = item['pregunta'][:50]
            fortalezas.append(f"✓ {pregunta_corta}")
    
    if not fortalezas:
        fortalezas = ["Proceso completado"]
    fortalezas = fortalezas[:5]
    
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
        riesgos = ["Sin riesgos"] if score_final >= 75 else ["Requiere validación manual"]
    riesgos = riesgos[:5]
    
    recomendacion = "❌ No continuar" if hubo_ko else ("✅ Entrevista prioritaria" if score_final >= 75 else ("⚠ Validar manualmente" if score_final >= 40 else "❌ Descartar"))
    
    return json.dumps({
        "resumen": resumen,
        "fortalezas": fortalezas,
        "riesgos": riesgos,
        "recomendacion": recomendacion,
        "metodo": "Evaluación lógica"
    }, ensure_ascii=False)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/como-funciona')
def como_funciona():
    return render_template('como-funciona.html')

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')

@app.route('/contacto')
def contacto():
    return render_template('contacto.html')

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
    vacantes_dict = {str(v.id_vacante_publico): {"cargo": v.cargo, "preguntas": preguntas_finales}}
    return render_template('encuesta.html', vacantes=[v], vacantes_dict=vacantes_dict, id_seleccionada=id_seleccionada)

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
    peso_total_posible = sum(float(p.get('peso', 0)) for p in v.preguntas if p.get('tipo') in ['si_no', 'multiple'])
    puntos_brutos_acumulados = 0
    hubo_ko = False
    motivo_descarte = ""
    detalle = []
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
        if tipo in ['si_no', 'multiple']:
            if respuesta_user.lower() == ideal.lower():
                puntos_obtenidos = peso_pregunta
            else:
                if es_ko:
                    hubo_ko = True
                    motivo_descarte = f"No cumple: {p_orig['texto']}"
        puntos_brutos_acumulados += puntos_obtenidos
        detalle.append({"pregunta": p_orig['texto'], "respuesta": respuesta_user, "puntos": puntos_obtenidos, "peso": peso_pregunta, "tipo": tipo})
    score_final = round((puntos_brutos_acumulados / max(1, peso_total_posible)) * 100, 1)
    analisis_json = generar_resumen_profesional(v.cargo, score_final, detalle, hubo_ko, motivo_descarte)
    veredicto = "DESCARTADO (KO)" if hubo_ko else ("RECOMENDADO" if score_final >= 75 else ("REVISAR" if score_final >= 40 else "NO APTO"))
    tag = "🔴" if hubo_ko or score_final < 40 else ("🟢" if score_final >= 75 else "🟡")
    nueva_entrevista = Entrevista(vacante_id=v.id, empresa_id=v.empresa_id, nombre_candidato=nombre, identificacion=cc, score=score_final, veredicto=veredicto, tag=tag, comentarios_tecnicos=motivo_descarte, respuestas_detalle=detalle, analisis_ia=analisis_json)
    try:
        db.session.add(nueva_entrevista)
        db.session.commit()
        return render_template('gracias.html')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error: {e}")
        return f"Error: {e}", 500

@app.route('/dashboard')
def dashboard():
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    user_id = session.get('user_id')
    emp_id_str = session.get('empresa_id')
    try:
        emp_id = uuid.UUID(emp_id_str)
    except:
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
        candidatos_cards.append({"id": e.id, "nombre": e.nombre_candidato, "cargo": v_rel.cargo if v_rel else "N/A", "score": e.score, "veredicto": e.veredicto, "tag": e.tag, "fecha": e.fecha.strftime('%d.%m.%Y') if e.fecha else "N/A", "analisis_ia": e.analisis_ia, "respuestas_detalle": e.respuestas_detalle})
    return render_template("dashboard.html", usuario=usuario, empresa=empresa, entrevistas=candidatos_cards, vacantes=vacantes, total_c=len(resultados), total_v=len(vacantes), nombre_empresa=empresa.nombre_empresa)

@app.route('/gestionar_vacantes')
def gestionar_vacantes():
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    emp_id_str = session.get('empresa_id')
    try:
        emp_id = uuid.UUID(emp_id_str)
    except:
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
        except:
            return "Error", 400
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
                regla_dict = {"opciones": [o for o in opciones_pregunta if o], "ideal": reglas[i]}
                opcion_idx += 4
            elif t == 'abierta':
                regla_dict = {"palabras_clave": reglas[i]}
            else:
                regla_dict = {"ideal": reglas[i]}
            nuevas_preguntas.append({"id": f"q{i+1}", "texto": textos[i], "tipo": t, "reglas": regla_dict, "peso": int(pesos[i]) if pesos[i] else 0, "knockout": str(i) in request.form.getlist('p_ko[]')})
        nueva = Vacante(cargo=cargo, id_vacante_publico=id_publico, empresa_id=empresa_id, preguntas=nuevas_preguntas)
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

@app.route('/marketplace')
def marketplace():
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    return render_template('marketplace.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            if res.user:
                u_db = UsuarioEmpresa.query.filter_by(id=res.user.id).first()
                if u_db:
                    session.update({'logeado': True, 'user_id': res.user.id, 'empresa_id': str(u_db.empresa_id), 'nombre_empresa': u_db.empresa.nombre_empresa if u_db.empresa else "Mi Empresa"})
                    return redirect(url_for('dashboard'))
                else:
                    return render_template('login.html', error="Usuario no vinculado.")
        except Exception as e: 
            return render_template('login.html', error="Credenciales incorrectas.")
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
                nueva_empresa = Empresa(id=empresa_uuid, nombre_empresa=nombre_empresa, pais=pais, industria=industria, tamano=tamano_empresa)
                db.session.add(nueva_empresa)
                db.session.flush()
                nuevo_usuario = UsuarioEmpresa(id=user_id, email=email, nombre_completo=nombre_usuario, empresa_id=empresa_uuid, rol_en_empresa='admin')
                db.session.add(nuevo_usuario)
                cargo_display = cargo_inicial if cargo_inicial else "Asesor Comercial"
                id_v_publico = f"JOB-{int(time.time())}"
                preguntas_base = [{"id": "q1", "texto": "¿Tienes experiencia previa en ventas?", "tipo": "si_no", "peso": 20, "knockout": True, "reglas": {"ideal": "si"}}, {"id": "q2", "texto": "¿Cuentas con vehículo propio?", "tipo": "si_no", "peso": 15, "knockout": False, "reglas": {"ideal": "si"}}, {"id": "q3", "texto": "¿Disponibilidad para viajar?", "tipo": "si_no", "peso": 10, "knockout": False, "reglas": {"ideal": "si"}}, {"id": "q4", "texto": "Describe tu logro comercial más relevante", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}}, {"id": "q5", "texto": "¿Cuándo puedes iniciar?", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}}]
                primera_vacante = Vacante(cargo=cargo_display, id_vacante_publico=id_v_publico, empresa_id=empresa_uuid, preguntas=preguntas_base, activa=True)
                db.session.add(primera_vacante)
                db.session.commit()
                session.update({'logeado': True, 'user_id': user_id, 'empresa_id': str(empresa_uuid), 'nombre_empresa': nombre_empresa})
                return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            return f"Error: {e}", 400
    return render_template('registro.html')

@app.route('/eliminar_candidato/<id>', methods=['POST'])
def eliminar_candidato(id):
    if not session.get('logeado'): 
        return jsonify({"success": False}), 401
    candidato = Entrevista.query.get(id)
    if candidato:
        try:
            db.session.delete(candidato)
            db.session.commit()
            return jsonify({"success": True})
        except:
            db.session.rollback()
    return jsonify({"success": False})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/candidato/<id>')
def api_candidato(id):
    if not session.get('logeado'):
        return jsonify({"error": "No autorizado"}), 401
    candidato = Entrevista.query.get(id)
    if not candidato:
        return jsonify({"error": "No encontrado"}), 404
    vacante = Vacante.query.get(candidato.vacante_id)
    try:
        analisis = json.loads(candidato.analisis_ia)
    except:
        analisis = {"resumen": "N/A", "fortalezas": [], "riesgos": [], "recomendacion": ""}
    return jsonify({"nombre": candidato.nombre_candidato, "identificacion": candidato.identificacion, "cargo": vacante.cargo if vacante else "N/A", "score": candidato.score, "veredicto": candidato.veredicto, "tag": candidato.tag, "fecha": candidato.fecha.strftime('%d/%m/%Y %H:%M') if candidato.fecha else "N/A", "analisis": analisis, "respuestas": candidato.respuestas_detalle or []})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)