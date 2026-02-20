import os
import time
import json
import logging
import uuid
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, render_template_string, flash
from supabase import create_client, Client
from functools import wraps
from datetime import datetime, timedelta

from calculadora.routes import calculadora_bp
#from calculadora.epayco_checkout import epayco_bp

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'una-clave-muy-secreta')

app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400

app.register_blueprint(calculadora_bp, url_prefix='/calculadora')
#app.register_blueprint(epayco_bp, url_prefix='/epayco')
logger.info("✅ Módulo de calculadora registrado en /calculadora")
#logger.info("✅ Módulo de ePayco registrado en /epayco")

supabase: Client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# ============================================
# MOTOR DE EVALUACIÓN - LÓGICA
# ============================================

def generar_resumen_profesional(cargo, score_final, detalle, hubo_ko, motivo_ko, metricas_radar, skill_stack=None):
    entity_skill_score = {}
    for item in detalle:
        hab   = item.get('habilidad', '')
        peso  = float(item.get('peso', 0))
        puntos = float(item.get('puntos', 0))
        if not hab or peso == 0:
            continue
        if hab not in entity_skill_score:
            entity_skill_score[hab] = {'obtenido': 0, 'posible': 0}
        entity_skill_score[hab]['obtenido'] += puntos
        entity_skill_score[hab]['posible']  += peso
    for hab, vals in entity_skill_score.items():
        vals['pct'] = round((vals['obtenido'] / vals['posible']) * 100) if vals['posible'] > 0 else 0

    if hubo_ko:
        resumen = f"Candidato descartado automáticamente. {motivo_ko}. No cumple requisitos críticos (KO) para {cargo}."
    elif score_final >= 75:
        resumen = f"Candidato con perfil sobresaliente para {cargo}. Alto índice de compatibilidad con el stack de habilidades del rol. Se recomienda entrevista prioritaria."
    elif score_final >= 40:
        resumen = f"Candidato con potencial moderado para {cargo}. Cumple algunas habilidades críticas del rol pero presenta brechas que deben validarse."
    else:
        resumen = f"Candidato por debajo del perfil mínimo esperado para {cargo}. Baja alineación con las habilidades críticas del rol."

    fortalezas = []
    habilidades_criticas = skill_stack or []

    for hab in habilidades_criticas:
        if hab in entity_skill_score and entity_skill_score[hab]['pct'] >= 80:
            fortalezas.append(f"{hab} ({entity_skill_score[hab]['pct']}% — habilidad crítica del rol)")

    for item in detalle:
        hab = item.get('habilidad', '')
        if hab and hab not in habilidades_criticas:
            if item.get('puntos', 0) >= item.get('peso', 1) and item.get('peso', 0) > 0:
                if hab not in [f.split(' (')[0] for f in fortalezas]:
                    fortalezas.append(hab)

    if not fortalezas:
        fortalezas = ["Evaluación completada — sin habilidades críticas con puntaje destacado"]
    fortalezas = fortalezas[:5]

    riesgos = []
    if hubo_ko:
        riesgos.append(f"KO automático: {motivo_ko}")

    for hab in habilidades_criticas:
        if hab in entity_skill_score and entity_skill_score[hab]['pct'] <= 60:
            riesgos.append(f"Bajo desempeño en {hab} ({entity_skill_score[hab]['pct']}% — habilidad crítica del rol)")

    for hab in habilidades_criticas:
        if hab not in entity_skill_score:
            riesgos.append(f"{hab} no fue evaluada (habilidad crítica sin preguntas asociadas)")

    if not riesgos:
        riesgos = ["Sin alertas críticas detectadas"] if score_final >= 75 else ["Validar competencias blandas en entrevista"]
    riesgos = riesgos[:5]

    if hubo_ko:
        recomendacion = "❌ No continuar proceso"
    elif score_final >= 85:
        recomendacion = "⭐ Agendar Entrevista Inmediata"
    elif score_final >= 70:
        recomendacion = "✅ Avanzar a siguiente fase"
    elif score_final >= 40:
        recomendacion = "⚠ Entrevista técnica de validación"
    else:
        recomendacion = "❌ Descartar candidato"

    resultado = {
        "resumen": resumen,
        "fortalezas": fortalezas,
        "riesgos": riesgos,
        "recomendacion": recomendacion,
        "radar": metricas_radar,
        "metodo": "Motor de Competencias Sales AI v2 — Skill Stack",
        "entity_skill_score": {hab: vals['pct'] for hab, vals in entity_skill_score.items()}
    }
    return json.dumps(resultado, ensure_ascii=False)


# ============================================
# MIDDLEWARE ADMIN
# ============================================

# ============================================
# MIDDLEWARE ADMIN (CON LOGS DE DEBUG)
# ============================================

def admin_required(f):
    """Decorador para proteger rutas que requieren acceso de super admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Verificar sesión
        if not session.get('logeado'):
            logger.warning("❌ ADMIN: Usuario no logueado")
            flash('Debes iniciar sesión primero', 'error')
            return redirect(url_for('login'))
        
        user_id = session.get('user_id')
        logger.info(f"🔍 ADMIN: Verificando acceso para user_id: {user_id}")
        
        try:
            # 2. Obtener email del usuario
            response = supabase.table('usuarios_empresa').select('email').eq('id', user_id).execute()
            
            if not response.data:
                logger.error(f"❌ ADMIN: No se encontró usuario con id: {user_id}")
                flash('Usuario no encontrado', 'error')
                return redirect(url_for('dashboard'))
            
            user_email = response.data[0]['email']
            logger.info(f"📧 ADMIN: Email del usuario: {user_email}")
            
            # 3. Verificar si es super admin
            admin_check = supabase.table('super_admins').select('*').eq('email', user_email).eq('activo', True).execute()
            
            logger.info(f"🔎 ADMIN: Resultado de búsqueda en super_admins: {admin_check.data}")
            
            if not admin_check.data:
                logger.warning(f"⛔ ADMIN: Email {user_email} NO está en super_admins o no está activo")
                flash('No tienes permisos de administrador', 'warning')
                return redirect(url_for('dashboard'))
            
            logger.info(f"✅ ADMIN: Acceso concedido a {user_email}")
            return f(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"💥 ADMIN: Error verificando permisos: {e}")
            flash('Error verificando permisos', 'error')
            return redirect(url_for('dashboard'))
    
    return decorated_function


# ============================================
# RUTAS PÚBLICAS (LANDING PAGES)
# ============================================

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

        scores_categorias = {"Técnica": 0, "Experiencia": 0, "Blandas": 0, "Ajuste": 0}
        max_categorias = {"Técnica": 0, "Experiencia": 0, "Blandas": 0, "Ajuste": 0}
        scores_habilidades = {}
        max_habilidades = {}
        peso_total_posible = 0
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
            cat_nombre = p_orig.get('categoria', 'Ajuste')
            hab_nombre = p_orig.get('habilidad', 'General')

            if hab_nombre not in scores_habilidades:
                scores_habilidades[hab_nombre] = 0
                max_habilidades[hab_nombre] = 0

            puntos_obtenidos = 0
            if tipo in ['si_no', 'multiple', 'escala_1_5', 'escala_1_10']:
                peso_total_posible += peso_pregunta
                if cat_nombre in max_categorias:
                    max_categorias[cat_nombre] += peso_pregunta
                max_habilidades[hab_nombre] += peso_pregunta
                if respuesta_user.lower() == ideal.lower():
                    puntos_obtenidos = peso_pregunta
                    if cat_nombre in scores_categorias:
                        scores_categorias[cat_nombre] += peso_pregunta
                    scores_habilidades[hab_nombre] += peso_pregunta
                else:
                    if es_ko:
                        hubo_ko = True
                        motivo_descarte = f"No cumple: {p_orig['texto']}"
            elif tipo == 'abierta':
                logger.info(f"📝 Pregunta abierta {p_orig['id']}: Guardada para análisis IA")

            puntos_brutos_acumulados += puntos_obtenidos
            detalle.append({
                "pregunta": p_orig['texto'],
                "respuesta": respuesta_user,
                "puntos": puntos_obtenidos,
                "peso": peso_pregunta,
                "tipo": tipo,
                "categoria": cat_nombre,
                "habilidad": hab_nombre
            })

        score_final = (puntos_brutos_acumulados / peso_total_posible * 100) if peso_total_posible > 0 else 0
        score_final = round(score_final, 1)

        def calc_pct(obtenido, maximo):
            return round((obtenido / maximo * 100)) if maximo > 0 else 0

        metricas_radar = (
            f"T:{calc_pct(scores_categorias['Técnica'], max_categorias['Técnica'])}% "
            f"E:{calc_pct(scores_categorias['Experiencia'], max_categorias['Experiencia'])}% "
            f"B:{calc_pct(scores_categorias['Blandas'], max_categorias['Blandas'])}% "
            f"A:{calc_pct(scores_categorias['Ajuste'], max_categorias['Ajuste'])}%"
        )

        skill_stack_rol = v.get('skill_stack') or []

        analisis_ia_texto = generar_resumen_profesional(
            cargo=v['cargo'],
            score_final=score_final,
            detalle=detalle,
            hubo_ko=hubo_ko,
            motivo_ko=motivo_descarte,
            metricas_radar=metricas_radar,
            skill_stack=skill_stack_rol
        )

        if hubo_ko:
            veredicto, tag = "DESCARTADO (KO)", "🔴"
        elif score_final >= 75:
            veredicto, tag = "RECOMENDADO", "🟢"
        elif score_final >= 40:
            veredicto, tag = "REVISAR", "🟡"
        else:
            veredicto, tag = "NO APTO", "🔴"

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
            "analisis_ia": analisis_ia_texto,
            "fecha": datetime.utcnow().isoformat(),
            "entity_skill_score": {h: calc_pct(scores_habilidades[h], max_habilidades[h]) for h in scores_habilidades}
        }
        supabase.table('entrevistas').insert(nueva_entrevista).execute()
        return render_template('gracias.html')

    except Exception as e:
        logger.error(f"❌ Error en procesar: {e}")
        return f"Error: {e}", 500


@app.route('/candidatos')
def candidatos():
    if not session.get('logeado'):
        return redirect(url_for('login'))
    try:
        result = supabase.table('entrevistas').select('*').order('score', desc=True).execute()
        entrevistas = result.data
        for e in entrevistas:
            if e.get('analisis_ia'):
                try:
                    e['analisis_ia_obj'] = json.loads(e['analisis_ia'])
                except Exception as ex:
                    logger.error(f"Error parseando analisis_ia: {ex}")
                    e['analisis_ia_obj'] = None
        return render_template('candidatos.html', candidatos=entrevistas)
    except Exception as e:
        logger.error(f"❌ Error en ruta candidatos: {e}")
        return f"Error: {e}", 500


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
                "respuestas_detalle": e.get('respuestas_detalle'),
                "estado": e.get('estado', None)
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

        textos = request.form.getlist('pregunta[]')
        tipos = request.form.getlist('tipo[]')
        pesos = request.form.getlist('peso[]')
        reglas = request.form.getlist('regla_valor[]')
        habilidades_asociadas = request.form.getlist('habilidad_asociada[]')
        categorias = request.form.getlist('categoria[]')
        kos = request.form.getlist('ko[]')
        opciones_todas = request.form.getlist('p_opciones_lista[]')

        hab_criticas_raw = request.form.get('habilidades_seleccionadas', '')
        hab_criticas = [h.strip() for h in hab_criticas_raw.split(',') if h.strip()]

        nuevas_preguntas = []
        opcion_idx = 0
        for i in range(len(textos)):
            t = tipos[i]
            regla_dict = {}
            if t == 'multiple':
                opciones_pregunta = opciones_todas[opcion_idx: opcion_idx + 4]
                regla_dict = {
                    "opciones": [o for o in opciones_pregunta if o],
                    "ideal": reglas[i]
                }
                opcion_idx += 4
            elif t == 'abierta':
                palabras = [p.strip() for p in reglas[i].split(',')] if reglas[i] else []
                regla_dict = {"palabras_clave": palabras}
            else:
                regla_dict = {"ideal": reglas[i]}

            nuevas_preguntas.append({
                "id": f"q{i+1}",
                "texto": textos[i],
                "tipo": t,
                "reglas": regla_dict,
                "peso": float(pesos[i]) if pesos[i] else 0.0,
                "categoria": categorias[i] if i < len(categorias) else "General",
                "habilidad": habilidades_asociadas[i] if i < len(habilidades_asociadas) else "General",
                "knockout": str(i) in kos,
                "texto_corto": textos[i][:30] + "..."
            })

        nueva_vacante_data = {
            "id": str(uuid.uuid4()),
            "cargo": cargo,
            "id_vacante_publico": id_publico,
            "empresa_id": emp_id_str,
            "preguntas": nuevas_preguntas,
            "skill_stack": hab_criticas,
            "activa": True,
            "created_at": datetime.utcnow().isoformat()
        }
        try:
            supabase.table('vacantes').insert(nueva_vacante_data).execute()
            return redirect(url_for('gestionar_vacantes'))
        except Exception as e:
            logger.error(f"Error al insertar vacante: {e}")
            return f"Error en el servidor: {e}", 500

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
# AUTH
# ============================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
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
    try:
        callback_html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Autenticando...</title>
            <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
            <style>
                body { font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
                .loader { text-align: center; color: white; }
                .spinner { border: 4px solid rgba(255,255,255,0.3); border-radius: 50%; border-top-color: white; width: 50px; height: 50px; animation: spin 1s linear infinite; margin: 0 auto 20px; }
                @keyframes spin { to { transform: rotate(360deg); } }
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
                const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
                async function handleCallback() {
                    try {
                        const { data: { session }, error } = await supabaseClient.auth.getSession();
                        if (error) throw error;
                        if (session && session.user) {
                            const response = await fetch('/auth/google/sync', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    user_id: session.user.id,
                                    email: session.user.email,
                                    full_name: session.user.user_metadata.full_name || session.user.email,
                                    access_token: session.access_token
                                })
                            });
                            const result = await response.json();
                            if (result.success) { window.location.href = '/dashboard'; }
                            else { alert('Error: ' + result.error); window.location.href = '/login'; }
                        } else { throw new Error('No se pudo obtener la sesión'); }
                    } catch (error) { alert('Error: ' + error.message); window.location.href = '/login'; }
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
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        email = data.get('email')
        full_name = data.get('full_name')
        if not user_id or not email:
            return jsonify({"success": False, "error": "Datos incompletos"}), 400

        usuario_result = supabase.table('usuarios_empresa').select('*').eq('id', user_id).execute()
        if not usuario_result.data:
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
            primera_vacante = {
                "id": str(uuid.uuid4()),
                "cargo": "Asesor Comercial",
                "id_vacante_publico": id_v_publico,
                "empresa_id": empresa_uuid,
                "preguntas": [
                    {"id": "q1", "texto": "¿Tienes experiencia previa en ventas?", "tipo": "si_no", "peso": 20, "knockout": True, "reglas": {"ideal": "si"}},
                    {"id": "q2", "texto": "¿Cuentas con vehículo propio?", "tipo": "si_no", "peso": 15, "knockout": False, "reglas": {"ideal": "si"}},
                    {"id": "q3", "texto": "Describe tu logro comercial", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}},
                ],
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
                primera_vacante = {
                    "id": str(uuid.uuid4()),
                    "cargo": cargo_display,
                    "id_vacante_publico": id_v_publico,
                    "empresa_id": empresa_uuid,
                    "preguntas": [
                        {"id": "q1", "texto": "¿Tienes experiencia previa en ventas?", "tipo": "si_no", "peso": 20, "knockout": True, "reglas": {"ideal": "si"}},
                        {"id": "q2", "texto": "¿Cuentas con vehículo propio?", "tipo": "si_no", "peso": 15, "knockout": False, "reglas": {"ideal": "si"}},
                        {"id": "q3", "texto": "¿Disponibilidad para viajar?", "tipo": "si_no", "peso": 10, "knockout": False, "reglas": {"ideal": "si"}},
                        {"id": "q4", "texto": "Describe tu logro comercial más relevante", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}},
                        {"id": "q5", "texto": "¿Cuándo puedes iniciar?", "tipo": "abierta", "peso": 0, "knockout": False, "reglas": {}}
                    ],
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


# ============================================
# REPORTES
# ============================================

@app.route('/reportes')
def reportes():
    if not session.get('logeado'):
        return redirect(url_for('login'))

    emp_id_str = session.get('empresa_id')
    user_id    = session.get('user_id')

    try:
        usuario_result = supabase.table('usuarios_empresa').select('*').eq('id', user_id).execute()
        usuario = usuario_result.data[0] if usuario_result.data else {}

        empresa_result = supabase.table('empresas').select('*').eq('id', emp_id_str).execute()
        empresa = empresa_result.data[0] if empresa_result.data else {}

        vacantes_result = supabase.table('vacantes').select('*').eq('empresa_id', emp_id_str).execute()
        vacantes = vacantes_result.data or []

        entrevistas_result = supabase.table('entrevistas').select('*').eq('empresa_id', emp_id_str).order('fecha', desc=True).execute()
        entrevistas = entrevistas_result.data or []

        total_c = len(entrevistas)
        total_v = len(vacantes)
        recomendados    = [e for e in entrevistas if e.get('veredicto') == 'RECOMENDADO']
        no_recomendados = [e for e in entrevistas if e.get('veredicto') == 'NO RECOMENDADO']
        a_revisar       = [e for e in entrevistas if e.get('veredicto') == 'REVISAR']

        tasa_aprobacion = round(len(recomendados) / total_c * 100) if total_c > 0 else 0
        score_promedio  = round(sum(e.get('score', 0) for e in entrevistas) / total_c, 1) if total_c > 0 else 0

        finalistas  = [e for e in entrevistas if e.get('estado') == 'Finalista']
        contratados = [e for e in entrevistas if e.get('estado') == 'Contratado']
        descartados = [e for e in entrevistas if e.get('estado') == 'Descartado']
        sin_estado  = [e for e in entrevistas if not e.get('estado')]

        rendimiento_por_vacante = []
        for v in vacantes:
            cands = [e for e in entrevistas if e.get('vacante_id') == v['id']]
            if not cands:
                continue
            scores = [e.get('score', 0) for e in cands]
            aptos  = [e for e in cands if e.get('veredicto') == 'RECOMENDADO']
            rendimiento_por_vacante.append({
                'cargo':           v['cargo'],
                'total':           len(cands),
                'score_promedio':  round(sum(scores) / len(scores), 1),
                'tasa_aprobacion': round(len(aptos) / len(cands) * 100),
                'finalistas':      len([e for e in cands if e.get('estado') == 'Finalista']),
                'contratados':     len([e for e in cands if e.get('estado') == 'Contratado']),
            })
        rendimiento_por_vacante.sort(key=lambda x: x['score_promedio'], reverse=True)

        from collections import defaultdict
        por_mes = defaultdict(list)
        for e in entrevistas:
            fecha = e.get('fecha', '')
            if fecha and len(fecha) >= 7:
                por_mes[fecha[:7]].append(e.get('score', 0))

        evolucion = []
        for mes in sorted(por_mes.keys()):
            scores_mes = por_mes[mes]
            evolucion.append({
                'mes':            mes,
                'total':          len(scores_mes),
                'score_promedio': round(sum(scores_mes) / len(scores_mes), 1)
            })

        import json as json_mod
        evolucion_labels  = json_mod.dumps([e['mes'] for e in evolucion])
        evolucion_totales = json_mod.dumps([e['total'] for e in evolucion])
        evolucion_scores  = json_mod.dumps([e['score_promedio'] for e in evolucion])
        vacante_labels    = json_mod.dumps([r['cargo'][:20] for r in rendimiento_por_vacante])
        vacante_scores    = json_mod.dumps([r['score_promedio'] for r in rendimiento_por_vacante])
        vacante_tasas     = json_mod.dumps([r['tasa_aprobacion'] for r in rendimiento_por_vacante])
        embudo            = json_mod.dumps([total_c, len(recomendados), len(finalistas), len(contratados)])

        return render_template('reportes.html',
            usuario=usuario,
            empresa=empresa,
            nombre_empresa=empresa.get('nombre_empresa', ''),
            total_c=total_c,
            total_v=total_v,
            tasa_aprobacion=tasa_aprobacion,
            score_promedio=score_promedio,
            recomendados=len(recomendados),
            no_recomendados=len(no_recomendados),
            a_revisar=len(a_revisar),
            finalistas=len(finalistas),
            contratados=len(contratados),
            descartados=len(descartados),
            sin_estado=len(sin_estado),
            rendimiento_por_vacante=rendimiento_por_vacante,
            evolucion=evolucion,
            evolucion_labels=evolucion_labels,
            evolucion_totales=evolucion_totales,
            evolucion_scores=evolucion_scores,
            vacante_labels=vacante_labels,
            vacante_scores=vacante_scores,
            vacante_tasas=vacante_tasas,
            embudo=embudo,
        )
    except Exception as e:
        logger.error(f"❌ Error en reportes: {e}")
        return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/api/habilidades', methods=['GET'])
def get_habilidades():
    if not session.get('logeado'):
        return jsonify({"error": "No autorizado"}), 401
    try:
        result = supabase.table('habilidades').select('*').execute()
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# API CANDIDATO
# ============================================

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

        evaluacion = None
        criterios_guardados = candidato.get('criterios_entrevista')
        if criterios_guardados:
            evaluacion = {
                "criterios":             criterios_guardados,
                "comentario":            candidato.get('comentario_entrevista', ''),
                "score_interview":       candidato.get('score_interview'),
                "score_final_combinado": candidato.get('score_final_combinado'),
            }

        score_pre = float(candidato['score'] or 0)
        score_interview = None
        score_final_combinado = None

        if evaluacion and evaluacion.get('criterios'):
            criterios = evaluacion['criterios']
            bloque_a = [criterios.get(k, 3) for k in ['dominio', 'resolucion']]
            bloque_b = [criterios.get(k, 3) for k in ['comunicacion', 'pensamiento', 'cultura', 'seguridad']]
            score_a  = sum(bloque_a) / len(bloque_a) if bloque_a else 3
            score_b  = sum(bloque_b) / len(bloque_b) if bloque_b else 3
            interview_score_raw = score_a * 0.4 + score_b * 0.6
            score_interview = round((interview_score_raw - 1) / 4 * 100)
            score_final_combinado = round(score_pre * 0.7 + score_interview * 0.3, 1)

        return jsonify({
            "nombre":                candidato['nombre_candidato'],
            "identificacion":        candidato['identificacion'],
            "cargo":                 cargo,
            "score":                 candidato['score'],
            "veredicto":             candidato['veredicto'],
            "tag":                   candidato['tag'],
            "fecha":                 candidato.get('fecha', 'N/A')[:10] if candidato.get('fecha') else "N/A",
            "analisis":              analisis,
            "respuestas":            candidato.get('respuestas_detalle', []),
            "estado":                candidato.get('estado', None),
            "evaluacion":            evaluacion,
            "score_interview":       score_interview,
            "score_final_combinado": score_final_combinado
        })
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# API GUARDAR EVALUACIÓN
# ============================================

@app.route('/api/guardar_evaluacion', methods=['POST'])
def guardar_evaluacion():
    if not session.get('logeado'):
        return jsonify({"error": "No autorizado"}), 401
    try:
        data = request.json
        entrevista_id = data.get('entrevista_id')
        criterios     = data.get('criterios', {})
        comentario    = data.get('comentario', '')

        if not entrevista_id or not criterios:
            return jsonify({"error": "Datos incompletos"}), 400

        bloque_a = [criterios.get(k, 3) for k in ['dominio', 'resolucion']]
        score_a  = sum(bloque_a) / len(bloque_a) if bloque_a else 3
        bloque_b = [criterios.get(k, 3) for k in ['comunicacion', 'pensamiento', 'cultura', 'seguridad']]
        score_b  = sum(bloque_b) / len(bloque_b) if bloque_b else 3
        interview_score_raw = round(score_a * 0.4 + score_b * 0.6, 2)
        score_interview = round((interview_score_raw - 1) / 4 * 100)

        cand = supabase.table('entrevistas').select('score').eq('id', entrevista_id).single().execute()
        score_pre = float(cand.data['score'] or 0) if cand.data else 0
        score_final_combinado = round(score_pre * 0.7 + score_interview * 0.3, 1)

        supabase.table('entrevistas').update({
            "criterios_entrevista":  criterios,
            "comentario_entrevista": comentario,
            "score_interview":       score_interview,
            "score_final_combinado": score_final_combinado,
        }).eq('id', entrevista_id).execute()

        logger.info(f"✅ Evaluación guardada: {entrevista_id} — score combinado: {score_final_combinado}%")
        return jsonify({
            "status":                "success",
            "score_interview":       score_interview,
            "score_final_combinado": score_final_combinado
        })
    except Exception as e:
        logger.error(f"❌ Error guardando evaluación: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# COMPARAR CANDIDATOS
# ============================================

@app.route('/comparar')
def comparar():
    if not session.get('logeado'):
        return redirect(url_for('candidatos'))
    id1 = request.args.get('c1')
    id2 = request.args.get('c2')
    if not id1 or not id2:
        return redirect(url_for('candidatos'))
    try:
        c1 = supabase.table('entrevistas').select('*, vacantes(cargo, skill_stack)').eq('id', id1).single().execute()
        c2 = supabase.table('entrevistas').select('*, vacantes(cargo, skill_stack)').eq('id', id2).single().execute()

        for c in [c1.data, c2.data]:
            if c.get('analisis_ia'):
                c['analisis_ia_obj'] = json.loads(c['analisis_ia'])

        def get_eval(candidato_data):
            criterios = candidato_data.get('criterios_entrevista')
            if not criterios:
                return None
            return {
                "criterios":             criterios,
                "comentario":            candidato_data.get('comentario_entrevista', ''),
                "score_interview":       candidato_data.get('score_interview'),
                "score_final_combinado": candidato_data.get('score_final_combinado'),
            }

        eval1 = get_eval(c1.data)
        eval2 = get_eval(c2.data)

        def calc_score_final(score_pre, eval_data):
            if not eval_data or not eval_data.get('criterios'):
                return None
            criterios = eval_data['criterios']
            bloque_a = [criterios.get(k, 3) for k in ['dominio', 'resolucion']]
            bloque_b = [criterios.get(k, 3) for k in ['comunicacion', 'pensamiento', 'cultura', 'seguridad']]
            score_a = sum(bloque_a) / len(bloque_a) if bloque_a else 3
            score_b = sum(bloque_b) / len(bloque_b) if bloque_b else 3
            interview_raw = score_a * 0.4 + score_b * 0.6
            score_interview = round((interview_raw - 1) / 4 * 100)
            return round(float(score_pre) * 0.7 + score_interview * 0.3, 1)

        c1.data['score_final'] = calc_score_final(c1.data.get('score', 0), eval1)
        c2.data['score_final'] = calc_score_final(c2.data.get('score', 0), eval2)
        c1.data['eval'] = eval1
        c2.data['eval'] = eval2

        skill_stack = []
        if c1.data.get('vacantes') and c1.data['vacantes'].get('skill_stack'):
            skill_stack = c1.data['vacantes']['skill_stack']

        return render_template('comparar.html', c1=c1.data, c2=c2.data, skill_stack=skill_stack)
    except Exception as e:
        logger.error(f"❌ Error en comparador: {e}")
        return redirect(url_for('candidatos'))


# ============================================
# RUTAS ADMIN
# ============================================

@app.route('/admin')
@admin_required
def admin_panel():
    """Panel de administrador global"""
    try:
        metricas_response = supabase.table('vista_metricas_empresas').select('*').execute()
        empresas = metricas_response.data if metricas_response.data else []
        
        total_empresas = len(empresas)
        empresas_activas = sum(1 for e in empresas if e.get('activo'))
        total_vacantes = sum(e.get('total_vacantes', 0) for e in empresas)
        total_candidatos = sum(e.get('total_candidatos', 0) for e in empresas)
        
        empresas_con_vacante_24h = sum(1 for e in empresas if e.get('primera_vacante_24h'))
        porcentaje_conversion = round((empresas_con_vacante_24h / total_empresas * 100), 2) if total_empresas > 0 else 0
        
        for empresa in empresas:
            if empresa.get('fecha_registro'):
                empresa['fecha_registro_formatted'] = datetime.fromisoformat(
                    empresa['fecha_registro'].replace('Z', '+00:00')
                ).strftime('%d/%m/%Y %H:%M')
            
            if empresa.get('ultima_actividad'):
                empresa['ultima_actividad_formatted'] = datetime.fromisoformat(
                    empresa['ultima_actividad'].replace('Z', '+00:00')
                ).strftime('%d/%m/%Y %H:%M')
            else:
                empresa['ultima_actividad_formatted'] = 'Sin actividad'
        
        return render_template('admin/dashboard.html',
                             empresas=empresas,
                             total_empresas=total_empresas,
                             empresas_activas=empresas_activas,
                             total_vacantes=total_vacantes,
                             total_candidatos=total_candidatos,
                             porcentaje_conversion=porcentaje_conversion)
        
    except Exception as e:
        logger.error(f"Error en admin_panel: {e}")
        return redirect(url_for('dashboard'))


@app.route('/admin/empresa/<empresa_id>')
@admin_required
def admin_empresa_detalle(empresa_id):
    """Ver detalles completos de una empresa"""
    try:
        empresa_response = supabase.table('empresas').select('*').eq('id', empresa_id).execute()
        if not empresa_response.data:
            return redirect(url_for('admin_panel'))
        
        empresa = empresa_response.data[0]
        usuarios_response = supabase.table('usuarios_empresa').select('*').eq('empresa_id', empresa_id).execute()
        usuarios = usuarios_response.data if usuarios_response.data else []
        vacantes_response = supabase.table('vacantes').select('*').eq('empresa_id', empresa_id).execute()
        vacantes = vacantes_response.data if vacantes_response.data else []
        candidatos_response = supabase.table('entrevistas').select('*').eq('empresa_id', empresa_id).order('fecha', desc=True).execute()
        candidatos = candidatos_response.data if candidatos_response.data else []
        
        return render_template('admin/empresa_detalle.html',
                             empresa=empresa,
                             usuarios=usuarios,
                             vacantes=vacantes,
                             candidatos=candidatos)
        
    except Exception as e:
        logger.error(f"Error en admin_empresa_detalle: {e}")
        return redirect(url_for('admin_panel'))


@app.route('/admin/api/estadisticas')
@admin_required
def admin_estadisticas():
    """API para obtener estadísticas agregadas"""
    try:
        metricas_response = supabase.table('vista_metricas_empresas').select('*').execute()
        empresas = metricas_response.data if metricas_response.data else []
        
        hoy = datetime.now()
        stats_mensuales = {}
        
        for i in range(6):
            mes = (hoy - timedelta(days=30*i)).strftime('%Y-%m')
            stats_mensuales[mes] = {
                'nuevas_empresas': 0,
                'nuevos_candidatos': 0
            }
        
        for empresa in empresas:
            if empresa.get('fecha_registro'):
                mes = empresa['fecha_registro'][:7]
                if mes in stats_mensuales:
                    stats_mensuales[mes]['nuevas_empresas'] += 1
        
        return jsonify({
            'success': True,
            'stats_mensuales': stats_mensuales,
            'total_empresas': len(empresas),
            'empresas_activas': sum(1 for e in empresas if e.get('activo')),
            'tasa_activacion': round(sum(1 for e in empresas if e.get('activo')) / len(empresas) * 100, 2) if empresas else 0
        })
        
    except Exception as e:
        logger.error(f"Error en admin_estadisticas: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Agregar esto después de las rutas principales, antes del if __name__
@app.route('/health')
def health():
    """Health check para Render"""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()}), 200


# ============================================
# INICIO DE LA APLICACIÓN
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)