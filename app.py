import os
import time
import json
import logging
import uuid
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, render_template_string
from supabase import create_client, Client

# ═══════════════════════════════════════════════════════════════════════════
# ✅ IMPORTS DE BLUEPRINTS (sin registrar aún)
# ═══════════════════════════════════════════════════════════════════════════
from calculadora.routes import calculadora_bp
from calculadora.epayco_checkout import epayco_bp

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# ═══════════════════════════════════════════════════════════════════════════
# ✅ CREAR LA APP (AHORA SÍ)
# ═══════════════════════════════════════════════════════════════════════════
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'una-clave-muy-secreta')

app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400

# ═══════════════════════════════════════════════════════════════════════════
# ✅ REGISTRAR BLUEPRINTS (DESPUÉS de crear app)
# ═══════════════════════════════════════════════════════════════════════════
app.register_blueprint(calculadora_bp, url_prefix='/calculadora')
app.register_blueprint(epayco_bp, url_prefix='/epayco')
logger.info("✅ Módulo de calculadora registrado en /calculadora")
logger.info("✅ Módulo de ePayco registrado en /epayco")

# Cliente Supabase
supabase: Client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# ============================================
# MOTOR DE EVALUACIÓN - LÓGICA
# ============================================

def generar_resumen_profesional(cargo, score_final, detalle, hubo_ko, motivo_ko):
    """Genera un resumen profesional basado en REGLAS LÓGICAS (sin IA)."""
    
    if hubo_ko:
        resumen = f"Candidato descartado automáticamente. {motivo_ko}. No cumple con requisitos críticos para el cargo de {cargo}."
    elif score_final >= 75:
        resumen = f"Candidato altamente calificado para {cargo}. Cumple con la mayoría de requisitos clave. Se recomienda entrevista prioritaria."
    elif score_final >= 40:
        resumen = f"Candidato con perfil moderado para {cargo}. Cumple requisitos básicos pero requiere validación adicional del reclutador."
    else:
        resumen = f"Candidato por debajo del umbral mínimo para {cargo}. No se recomienda continuar el proceso."
    
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
        fortalezas = ["Proceso de evaluación completado"]
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
        if score_final < 75:
            riesgos = ["Requiere validación manual del reclutador"]
        else:
            riesgos = ["Sin riesgos identificados"]
    riesgos = riesgos[:5]
    
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

# ============================================
# RUTAS PÚBLICAS (LANDING PAGES)
# ============================================

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

# ============================================
# RUTAS PÚBLICAS (CANDIDATOS)
# ============================================

@app.route('/encuesta')
def index():
    id_seleccionada = request.args.get('vacante')
    if not id_seleccionada:
        return "<h1>Link incompleto</h1>", 400

    try:
        result = supabase.table('vacantes').select('*').eq('id_vacante_publico', id_seleccionada).execute()
        
        if not result.data:
            return "<h1>Vacante no encontrada</h1>", 404
        
        v = result.data[0]
        preguntas_finales = v.get('preguntas', [])
        
        if isinstance(preguntas_finales, dict) and 'preguntas' in preguntas_finales:
            preguntas_finales = preguntas_finales['preguntas']

        vacantes_dict = {
            str(v['id_vacante_publico']): {
                "cargo": v['cargo'],
                "preguntas": preguntas_finales
            }
        }

        return render_template('encuesta.html', 
                               vacantes=[v], 
                               vacantes_dict=vacantes_dict, 
                               id_seleccionada=id_seleccionada)
    except Exception as e:
        logger.error(f"Error en encuesta: {e}")
        return f"Error: {e}", 500


@app.route('/procesar', methods=['POST'])
def procesar():
    id_publico = request.form.get('id_vacante')
    nombre = request.form.get('nombre')
    cc = request.form.get('cc')

    try:
        result = supabase.table('vacantes').select('*').eq('id_vacante_publico', id_publico).execute()
        
        if not result.data:
            return "Vacante no encontrada", 404
        
        v = result.data[0]
        
        ids_q = request.form.getlist('preguntas_custom[]')
        vals_r = request.form.getlist('respuestas_custom[]')
        
        logger.info(f"🎯 Procesando candidato: {nombre} para cargo: {v['cargo']}")
        
        peso_total_posible = sum(
            float(p.get('peso', 0)) 
            for p in v['preguntas'] 
            if p.get('tipo') in ['si_no', 'multiple']
        )
        
        logger.info(f"📊 Peso total calificable: {peso_total_posible}")
        
        puntos_brutos_acumulados = 0
        hubo_ko = False
        motivo_descarte = ""
        detalle = []

        for i in range(len(ids_q)):
            p_orig = next((p for p in v['preguntas'] if p['id'] == ids_q[i]), None)
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
                    logger.info(f"✅ Pregunta {p_orig['id']}: {peso_pregunta} pts")
                else:
                    logger.info(f"❌ Pregunta {p_orig['id']}: 0 pts")
                    if es_ko:
                        hubo_ko = True
                        motivo_descarte = f"No cumple: {p_orig['texto']}"
                        logger.warning(f"🚫 KNOCKOUT: {motivo_descarte}")
            
            elif tipo == 'abierta':
                logger.info(f"📝 Pregunta abierta {p_orig['id']}: Guardada")
            
            puntos_brutos_acumulados += puntos_obtenidos
            
            detalle.append({
                "pregunta": p_orig['texto'],
                "respuesta": respuesta_user,
                "puntos": puntos_obtenidos,
                "peso": peso_pregunta,
                "tipo": tipo
            })
        
        if peso_total_posible == 0:
            score_final = 0
        else:
            score_final = (puntos_brutos_acumulados / peso_total_posible) * 100
        
        score_final = round(score_final, 1)
        
        logger.info(f"💯 Score final: {score_final}%")

        analisis_json = generar_resumen_profesional(
            cargo=v['cargo'],
            score_final=score_final,
            detalle=detalle,
            hubo_ko=hubo_ko,
            motivo_ko=motivo_descarte
        )

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

        nueva_entrevista = {
            "id": str(uuid.uuid4()),
            "vacante_id": v['id'],
            "empresa_id": v['empresa_id'],
            "nombre_candidato": nombre,
            "identificacion": cc,
            "score": score_final,
            "veredicto": veredicto,
            "tag": tag,
            "comentarios_tecnicos": motivo_descarte,
            "respuestas_detalle": detalle,
            "analisis_ia": analisis_json,
            "fecha": datetime.utcnow().isoformat()
        }
        
        supabase.table('entrevistas').insert(nueva_entrevista).execute()
        
        logger.info(f"✅ Candidato guardado: {nombre} - {veredicto}")
        return render_template('gracias.html')
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return f"Error: {e}", 500
    
@app.route('/candidatos')
def lista_candidatos():
    try:
        res = supabase.table('entrevistas').select('*').execute()
        candidatos = res.data if res.data else []
        
        if candidatos:
            print(f"Columnas detectadas: {candidatos[0].keys()}")

        for c in candidatos:
            c['nombre_puesto'] = "Candidato Registrado"

        return render_template('candidatos.html', candidatos=candidatos)
    
    except Exception as e:
        print(f"ERROR EN APP.PY: {str(e)}")
        return f"Error de conexión: {str(e)}", 500
    
@app.route('/actualizar_estado', methods=['POST'])
def actualizar_estado():
    try:
        data = request.json
        candidato_id = data.get('id')
        nuevo_estado = data.get('estado')

        if not candidato_id or not nuevo_estado:
            return jsonify({"status": "error", "message": "Datos incompletos"}), 400

        supabase.table('entrevistas').update({'estado': nuevo_estado}).eq('id', candidato_id).execute()

        print(f"✅ Candidato {candidato_id} actualizado a: {nuevo_estado}")
        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"❌ Error en actualización: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500   

# ============================================
# DASHBOARD
# ============================================

@app.route('/dashboard')
def dashboard():
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    emp_id_str = session.get('empresa_id')
    
    try:
        usuario_result = supabase.table('usuarios_empresa').select('*').eq('id', user_id).execute()
        if not usuario_result.data:
            session.clear()
            return redirect(url_for('login'))
        usuario = usuario_result.data[0]
        
        empresa_result = supabase.table('empresas').select('*').eq('id', emp_id_str).execute()
        if not empresa_result.data:
            session.clear()
            return redirect(url_for('login'))
        empresa = empresa_result.data[0]
        
        vacantes_result = supabase.table('vacantes').select('*').eq('empresa_id', emp_id_str).execute()
        vacantes = vacantes_result.data
        
        entrevistas_result = supabase.table('entrevistas').select('*').eq('empresa_id', emp_id_str).order('fecha', desc=True).execute()
        resultados = entrevistas_result.data
        
        candidatos_cards = []
        for e in resultados:
            v_rel = next((v for v in vacantes if v['id'] == e['vacante_id']), None)
            candidatos_cards.append({
                "id": e['id'],
                "nombre": e['nombre_candidato'],
                "cargo": v_rel['cargo'] if v_rel else "N/A",
                "score": e['score'],
                "veredicto": e['veredicto'],
                "tag": e['tag'],
                "fecha": e.get('fecha', 'N/A')[:10] if e.get('fecha') else "N/A",
                "analisis_ia": e.get('analisis_ia'),
                "respuestas_detalle": e.get('respuestas_detalle')
            })

        return render_template("dashboard.html", 
                               usuario=usuario,
                               empresa=empresa,
                               entrevistas=candidatos_cards, 
                               vacantes=vacantes, 
                               total_c=len(resultados), 
                               total_v=len(vacantes),
                               nombre_empresa=empresa['nombre_empresa'])
    except Exception as e:
        logger.error(f"Error en dashboard: {e}")
        session.clear()
        return redirect(url_for('login'))

# ============================================
# GESTIÓN DE VACANTES
# ============================================

@app.route('/gestionar_vacantes')
def gestionar_vacantes():
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    
    emp_id_str = session.get('empresa_id')
    
    try:
        vacantes_result = supabase.table('vacantes').select('*').eq('empresa_id', emp_id_str).execute()
        vacantes = vacantes_result.data
        return render_template('lista_vacantes.html', vacantes=vacantes)
    except Exception as e:
        logger.error(f"Error: {e}")
        return f"Error: {e}", 500

@app.route('/nueva_vacante', methods=['GET', 'POST'])
def nueva_vacante():
    if not session.get('logeado'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        cargo = request.form.get('cargo')
        emp_id_str = session.get('empresa_id')
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

        nueva = {
            "id": str(uuid.uuid4()),
            "cargo": cargo,
            "id_vacante_publico": id_publico,
            "empresa_id": emp_id_str,
            "preguntas": nuevas_preguntas,
            "activa": True,
            "created_at": datetime.utcnow().isoformat()
        }
        
        try:
            supabase.table('vacantes').insert(nueva).execute()
            return redirect(url_for('gestionar_vacantes'))
        except Exception as e:
            logger.error(f"Error: {e}")
            return f"Error: {e}", 500

    return render_template('nueva_vacante.html')

@app.route('/vacante_lista/<id_publico>')
def vacante_lista(id_publico):
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    
    try:
        result = supabase.table('vacantes').select('*').eq('id_vacante_publico', id_publico).execute()
        if not result.data:
            return "No encontrada", 404
        
        v = result.data[0]
        link = f"{request.url_root}encuesta?vacante={id_publico}"
        
        return render_template('vacante_lista.html', vacante=v, link=link)
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/editar_vacante/<id_publico>', methods=['GET', 'POST'])
def editar_vacante(id_publico):
    """Editar una vacante existente"""
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    
    try:
        result = supabase.table('vacantes').select('*').eq('id_vacante_publico', id_publico).execute()
        
        if not result.data:
            return "Vacante no encontrada", 404
        
        v = result.data[0]
        
        emp_id_str = session.get('empresa_id')
        if v['empresa_id'] != emp_id_str:
            return "No autorizado", 403

        if request.method == 'POST':
            cargo = request.form.get('cargo')
            
            ids = request.form.getlist('p_id[]')
            textos = request.form.getlist('p_texto[]')
            tipos = request.form.getlist('p_tipo[]')
            pesos = request.form.getlist('p_peso[]')
            reglas = request.form.getlist('p_regla[]')
            kos = request.form.getlist('p_ko[]')

            nuevas_preguntas = []
            for i in range(len(textos)):
                regla_obj = {}
                
                if tipos[i] == "si_no":
                    regla_obj = {"ideal": reglas[i]}
                elif tipos[i] == "multiple":
                    regla_obj = {"ideal": reglas[i]}
                else:
                    regla_obj = {"palabras_clave": reglas[i]}
                
                nuevas_preguntas.append({
                    "id": ids[i] if i < len(ids) else f"q{i+1}",
                    "texto": textos[i],
                    "tipo": tipos[i],
                    "peso": int(pesos[i]) if pesos[i] else 0,
                    "knockout": str(i) in kos,
                    "reglas": regla_obj
                })
            
            supabase.table('vacantes').update({
                "cargo": cargo,
                "preguntas": nuevas_preguntas
            }).eq('id_vacante_publico', id_publico).execute()
            
            logger.info(f"✅ Vacante actualizada: {id_publico}")
            return redirect(url_for('gestionar_vacantes'))

        return render_template('editar_vacante.html', vacante=v)
        
    except Exception as e:
        logger.error(f"Error editando vacante: {e}")
        return f"Error: {e}", 500

@app.route('/marketplace')
def marketplace():
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    return render_template('marketplace.html')

@app.route('/clonar_plantilla/<plantilla_id>')
def clonar_plantilla(plantilla_id):
    """Clonar una plantilla del marketplace"""
    if not session.get('logeado'): 
        return redirect(url_for('login'))
    
    biblioteca = {
        'operativo_express': {
            'cargo': 'Filtro Express (Operativo)',
            'preguntas': [
                {"id": "q1", "texto": "¿Vives en la ciudad de la vacante?", "tipo": "si_no", "peso": 10, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q2", "texto": "¿Tienes disponibilidad para viajar?", "tipo": "si_no", "peso": 5, "knockout": False, "reglas": {"ideal": "si"}},
                {"id": "q3", "texto": "¿Tienes experiencia en el cargo?", "tipo": "si_no", "peso": 15, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q4", "texto": "¿Dispones del horario requerido?", "tipo": "si_no", "peso": 10, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q5", "texto": "¿Aceptas el salario ofrecido?", "tipo": "si_no", "peso": 10, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q6", "texto": "Describe brevemente tu última función", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}},
                {"id": "q7", "texto": "¿Tienes documentos al día?", "tipo": "si_no", "peso": 5, "knockout": False, "reglas": {"ideal": "si"}},
                {"id": "q8", "texto": "¿Cuándo puedes iniciar?", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}}
            ]
        },
        'comercial_ventas': {
            'cargo': 'Ventas Retail / Campo',
            'preguntas': [
                {"id": "q1", "texto": "¿Tienes experiencia previa en ventas?", "tipo": "si_no", "peso": 20, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q2", "texto": "¿Cuentas con vehículo propio?", "tipo": "si_no", "peso": 15, "knockout": False, "reglas": {"ideal": "si"}},
                {"id": "q3", "texto": "Describe tu logro comercial más relevante", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}},
                {"id": "q4", "texto": "¿Disponibilidad para viajar?", "tipo": "si_no", "peso": 10, "knockout": False, "reglas": {"ideal": "si"}},
                {"id": "q5", "texto": "¿Has cumplido cuotas de ventas?", "tipo": "si_no", "peso": 20, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q6", "texto": "¿Cuándo puedes iniciar?", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}}
            ]
        },
        'tecnico_campo': {
            'cargo': 'Técnico de Campo',
            'preguntas': [
                {"id": "q1", "texto": "¿Tienes certificación técnica vigente?", "tipo": "si_no", "peso": 25, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q2", "texto": "¿Cuentas con herramientas propias?", "tipo": "si_no", "peso": 15, "knockout": False, "reglas": {"ideal": "si"}},
                {"id": "q3", "texto": "¿Tienes licencia de conducción?", "tipo": "si_no", "peso": 20, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q4", "texto": "Describe tu experiencia técnica", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}},
                {"id": "q5", "texto": "¿Disponibilidad para trabajo en alturas?", "tipo": "si_no", "peso": 10, "knockout": False, "reglas": {"ideal": "si"}}
            ]
        }
    }

    datos = biblioteca.get(plantilla_id)
    if not datos:
        return "Plantilla no encontrada", 404

    emp_id_str = session.get('empresa_id')
    id_publico = f"JOB-{plantilla_id.upper()[:3]}-{int(time.time())}"

    nueva_vacante = {
        "id": str(uuid.uuid4()),
        "cargo": datos['cargo'],
        "id_vacante_publico": id_publico,
        "empresa_id": emp_id_str,
        "preguntas": datos['preguntas'],
        "activa": True,
        "created_at": datetime.utcnow().isoformat()
    }
    
    try:
        supabase.table('vacantes').insert(nueva_vacante).execute()
        logger.info(f"✅ Plantilla clonada: {id_publico}")
        return redirect(url_for('vacante_lista', id_publico=id_publico))
    except Exception as e:
        logger.error(f"Error clonando plantilla: {e}")
        return f"Error: {e}", 500

# ============================================
# AUTH - LOGIN CON EMAIL/PASSWORD Y GOOGLE OAUTH
# ============================================

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
                usuario_result = supabase.table('usuarios_empresa').select('*').eq('id', res.user.id).execute()
                
                if usuario_result.data:
                    u_db = usuario_result.data[0]
                    
                    empresa_result = supabase.table('empresas').select('*').eq('id', u_db['empresa_id']).execute()
                    nombre_empresa = empresa_result.data[0]['nombre_empresa'] if empresa_result.data else "Mi Empresa"
                    
                    session.update({
                        'logeado': True,
                        'user_id': res.user.id,
                        'empresa_id': str(u_db['empresa_id']),
                        'nombre_empresa': nombre_empresa
                    })
                    
                    logger.info(f"✅ Login: {email}")
                    return redirect(url_for('dashboard'))
                else:
                    return render_template('login.html', 
                                         error="Usuario no vinculado.",
                                         supabase_url=os.getenv('SUPABASE_URL'),
                                         supabase_key=os.getenv('SUPABASE_KEY'))
                    
        except Exception as e: 
            logger.error(f"❌ Login error: {e}")
            return render_template('login.html', 
                                 error="Credenciales incorrectas.",
                                 supabase_url=os.getenv('SUPABASE_URL'),
                                 supabase_key=os.getenv('SUPABASE_KEY'))

    return render_template('login.html', 
                         error=None,
                         supabase_url=os.getenv('SUPABASE_URL'),
                         supabase_key=os.getenv('SUPABASE_KEY'))


@app.route('/auth/google/callback')
def google_callback():
    """Maneja el callback de Google OAuth usando JavaScript"""
    try:
        callback_html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Autenticando...</title>
            <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
            <style>
                body {
                    font-family: 'Inter', sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .loader {
                    text-align: center;
                    color: white;
                }
                .spinner {
                    border: 4px solid rgba(255,255,255,0.3);
                    border-radius: 50%;
                    border-top-color: white;
                    width: 50px;
                    height: 50px;
                    animation: spin 1s linear infinite;
                    margin: 0 auto 20px;
                }
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
            </style>
        </head>
        <body>
            <div class="loader">
                <div class="spinner"></div>
                <h2>Iniciando sesión...</h2>
                <p>Espera un momento</p>
            </div>
            
    

            <script>
                const SUPABASE_URL = '{{ supabase_url }}';
                const SUPABASE_KEY = '{{ supabase_key }}';
                
                // CAMBIO AQUÍ: Cambia 'const supabase' por 'const supabaseClient'
                const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
                
                async function handleCallback() {
                    try {
                        // CAMBIO AQUÍ: Usa 'supabaseClient'
                        const { data: { session }, error } = await supabaseClient.auth.getSession();
                        
                        if (error) throw error;
                        
                        if (session && session.user) {
                            console.log('Usuario autenticado:', session.user.email);
                            
                            const response = await fetch('/auth/google/sync', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({
                                    user_id: session.user.id,
                                    email: session.user.email,
                                    full_name: session.user.user_metadata.full_name || session.user.email,
                                    access_token: session.access_token
                                })
                            });
                            
                            const result = await response.json();
                            
                            if (result.success) {
                                window.location.href = '/dashboard';
                            } else {
                                alert('Error al sincronizar usuario: ' + result.error);
                                window.location.href = '/login';
                            }
                        } else {
                            throw new Error('No se pudo obtener la sesión');
                        }
                    } catch (error) {
                        console.error('Error en callback:', error);
                        alert('Error al iniciar sesión: ' + error.message);
                        window.location.href = '/login';
                    }
                }
                
                handleCallback();
            </script>
        </body>
        </html>
        '''
        
        return render_template_string(callback_html,
                                    supabase_url=os.getenv('SUPABASE_URL'),
                                    supabase_key=os.getenv('SUPABASE_KEY'))
        
    except Exception as e:
        logger.error(f"❌ Error en callback: {e}")
        return redirect(url_for('login'))


@app.route('/auth/google/sync', methods=['POST'])
def google_sync():
    """Crea o actualiza el usuario en la base de datos después de autenticarse con Google"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        email = data.get('email')
        full_name = data.get('full_name')
        
        if not user_id or not email:
            return jsonify({"success": False, "error": "Datos incompletos"}), 400
        
        usuario_result = supabase.table('usuarios_empresa').select('*').eq('id', user_id).execute()
        
        if not usuario_result.data:
            logger.info(f"🆕 Creando nuevo usuario Google: {email}")
            
            empresa_uuid = str(uuid.uuid4())
            nombre_base = email.split('@')[0].replace('.', ' ').title()
            
            nueva_empresa = {
                "id": empresa_uuid,
                "nombre_empresa": f"{nombre_base} Company",
                "pais": "Colombia",
                "industria": "Tecnología",
                "tamano": "1-10",
                "created_at": datetime.utcnow().isoformat()
            }
            supabase.table('empresas').insert(nueva_empresa).execute()
            
            nuevo_usuario = {
                "id": user_id,
                "email": email,
                "nombre_completo": full_name,
                "empresa_id": empresa_uuid,
                "rol_en_empresa": 'admin'
            }
            supabase.table('usuarios_empresa').insert(nuevo_usuario).execute()
            
            id_v_publico = f"JOB-{int(time.time())}"
            preguntas_base = [
                {"id": "q1", "texto": "¿Tienes experiencia previa en ventas?", "tipo": "si_no", "peso": 20, "knockout": True, "reglas": {"ideal": "si"}},
                {"id": "q2", "texto": "¿Cuentas con vehículo propio?", "tipo": "si_no", "peso": 15, "knockout": False, "reglas": {"ideal": "si"}},
                {"id": "q3", "texto": "Describe tu logro comercial", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}},
            ]
            primera_vacante = {
                "id": str(uuid.uuid4()),
                "cargo": "Asesor Comercial",
                "id_vacante_publico": id_v_publico,
                "empresa_id": empresa_uuid,
                "preguntas": preguntas_base,
                "activa": True,
                "created_at": datetime.utcnow().isoformat()
            }
            supabase.table('vacantes').insert(primera_vacante).execute()
            
            u_db = {"empresa_id": empresa_uuid, "nombre_completo": full_name}
        else:
            u_db = usuario_result.data[0]
        
        empresa_result = supabase.table('empresas').select('*').eq('id', u_db['empresa_id']).execute()
        nombre_empresa = empresa_result.data[0]['nombre_empresa'] if empresa_result.data else "Mi Empresa"
        
        session.update({
            'logeado': True,
            'user_id': user_id,
            'empresa_id': str(u_db['empresa_id']),
            'nombre_empresa': nombre_empresa
        })
        
        logger.info(f"✅ Usuario Google sincronizado: {email}")
        return jsonify({"success": True})
        
    except Exception as e:
        logger.error(f"❌ Error sincronizando Google: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


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
                empresa_uuid = str(uuid.uuid4())
                
                nueva_empresa = {
                    "id": empresa_uuid,
                    "nombre_empresa": nombre_empresa,
                    "pais": pais,
                    "industria": industria,
                    "tamano": tamano_empresa,
                    "created_at": datetime.utcnow().isoformat()
                }
                supabase.table('empresas').insert(nueva_empresa).execute()

                nuevo_usuario = {
                    "id": user_id,
                    "email": email,
                    "nombre_completo": nombre_usuario,
                    "empresa_id": empresa_uuid,
                    "rol_en_empresa": 'admin'
                }
                supabase.table('usuarios_empresa').insert(nuevo_usuario).execute()

                cargo_display = cargo_inicial if cargo_inicial else "Asesor Comercial"
                id_v_publico = f"JOB-{int(time.time())}"
                
                preguntas_base = [
                    {"id": "q1", "texto": "¿Tienes experiencia previa en ventas?", "tipo": "si_no", "peso": 20, "knockout": True, "reglas": {"ideal": "si"}},
                    {"id": "q2", "texto": "¿Cuentas con vehículo propio?", "tipo": "si_no", "peso": 15, "knockout": False, "reglas": {"ideal": "si"}},
                    {"id": "q3", "texto": "¿Disponibilidad para viajar?", "tipo": "si_no", "peso": 10, "knockout": False, "reglas": {"ideal": "si"}},
                    {"id": "q4", "texto": "Describe tu logro comercial más relevante", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}},
                    {"id": "q5", "texto": "¿Cuándo puedes iniciar?", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}}
                ]
                
                primera_vacante = {
                    "id": str(uuid.uuid4()),
                    "cargo": cargo_display,
                    "id_vacante_publico": id_v_publico,
                    "empresa_id": empresa_uuid,
                    "preguntas": preguntas_base,
                    "activa": True,
                    "created_at": datetime.utcnow().isoformat()
                }
                supabase.table('vacantes').insert(primera_vacante).execute()
                
                session.update({
                    'logeado': True,
                    'user_id': user_id,
                    'empresa_id': empresa_uuid,
                    'nombre_empresa': nombre_empresa
                })
                
                logger.info(f"🚀 Registro: {nombre_empresa}")
                return redirect(url_for('dashboard'))

        except Exception as e:
            logger.error(f"❌ Registro error: {e}")
            return f"Error: {e}", 400

    return render_template('registro.html')

@app.route('/eliminar_candidato/<id>', methods=['POST'])
def eliminar_candidato(id):
    """Eliminar un candidato"""
    if not session.get('logeado'): 
        return jsonify({"success": False, "error": "No autorizado"}), 401
    
    emp_id_str = session.get('empresa_id')
    
    try:
        candidato_result = supabase.table('entrevistas').select('*').eq('id', id).execute()
        
        if not candidato_result.data:
            return jsonify({"success": False, "error": "Candidato no encontrado"}), 404
        
        candidato = candidato_result.data[0]
        
        if candidato['empresa_id'] != emp_id_str:
            return jsonify({"success": False, "error": "No autorizado"}), 403
        
        supabase.table('entrevistas').delete().eq('id', id).execute()
        logger.info(f"✅ Candidato eliminado: {id}")
        return jsonify({"success": True})
        
    except Exception as e:
        logger.error(f"Error eliminando candidato: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/candidato/<id>')
def api_candidato(id):
    """API para obtener datos completos del candidato"""
    if not session.get('logeado'):
        return jsonify({"error": "No autorizado"}), 401
    
    try:
        candidato_result = supabase.table('entrevistas').select('*').eq('id', id).execute()
        
        if not candidato_result.data:
            return jsonify({"error": "Candidato no encontrado"}), 404
        
        candidato = candidato_result.data[0]
        
        emp_id_str = session.get('empresa_id')
        if candidato['empresa_id'] != emp_id_str:
            return jsonify({"error": "No autorizado"}), 403
        
        vacante_result = supabase.table('vacantes').select('*').eq('id', candidato['vacante_id']).execute()
        cargo = vacante_result.data[0]['cargo'] if vacante_result.data else "N/A"
        
        try:
            analisis = json.loads(candidato['analisis_ia'])
        except:
            analisis = {
                "resumen": "Análisis no disponible",
                "fortalezas": [],
                "riesgos": [],
                "recomendacion": ""
            }
        
        return jsonify({
            "nombre": candidato['nombre_candidato'],
            "identificacion": candidato['identificacion'],
            "cargo": cargo,
            "score": candidato['score'],
            "veredicto": candidato['veredicto'],
            "tag": candidato['tag'],
            "fecha": candidato.get('fecha', 'N/A')[:10] if candidato.get('fecha') else "N/A",
            "analisis": analisis,
            "respuestas": candidato.get('respuestas_detalle', [])
        })
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)