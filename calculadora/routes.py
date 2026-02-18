from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from datetime import datetime
import logging
import os

from supabase import create_client, Client
from calculadora.logic import calcular_metricas, generar_mensaje_benchmark
from calculadora.api_calculadora import registrar_demo, registrar_interaccion
from calculadora.epayco_checkout import crear_checkout_epayco, PLANES, epayco_bp

# ── Blueprint ──────────────────────────────────────────────────────────────────
calculadora_bp = Blueprint(
    'calculadora',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/calculadora'
)

logger = logging.getLogger(__name__)

supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)


# ==============================================================================
# PÁGINAS PÚBLICAS
# ==============================================================================

@calculadora_bp.route('/')
@calculadora_bp.route('/landing')
def landing():
    return render_template('calculadora/calculadora_landing.html')


@calculadora_bp.route('/formulario')
def formulario():
    return render_template('calculadora/calculadora_formulario.html')


@calculadora_bp.route('/gate/<diagnostico_id>')
def lead_gate(diagnostico_id):
    """
    Lead Gate: pantalla previa a los resultados.
    El usuario completó la encuesta → ve resultados borrosos → da sus datos → accede.

    URL: /calculadora/gate/<diagnostico_id>
    """
    try:
        # Verificar que el diagnóstico existe
        result = supabase.table('calculadora_diagnosticos') \
            .select('id, desbloqueado') \
            .eq('id', diagnostico_id) \
            .execute()

        if not result.data:
            return redirect(url_for('calculadora.formulario'))

        # Si ya desbloqueó antes, ir directo a resultados
        if result.data[0].get('desbloqueado'):
            return redirect(url_for('calculadora.resultados', diagnostico_id=diagnostico_id))

        return render_template('calculadora/calculadora_lead_gate.html', diagnostico_id=diagnostico_id)
        
    except Exception as e:
        logger.error(f"Error en lead_gate: {str(e)}") # Este es el error que vemos en el log
        return redirect(url_for('calculadora.formulario'))


@calculadora_bp.route('/resultados/<diagnostico_id>')
def resultados(diagnostico_id):
    """
    Resultados completos. Solo accesible si el lead ya dejó sus datos (desbloqueado=True).
    Si intenta entrar directo sin datos → redirige al gate.

    URL: /calculadora/resultados/<diagnostico_id>
    """
    try:
        result = supabase.table('calculadora_diagnosticos') \
            .select('*, calculadora_leads(*)') \
            .eq('id', diagnostico_id) \
            .execute()

        if not result.data:
            return "Diagnóstico no encontrado", 404

        data = result.data[0]

        # Seguridad: si no desbloqueó, mandarlo al gate
        if not data.get('desbloqueado'):
            return redirect(url_for('calculadora.lead_gate', diagnostico_id=diagnostico_id))

        # Marcar como visto
        supabase.table('calculadora_diagnosticos') \
            .update({'visto_resultados': True}) \
            .eq('id', diagnostico_id) \
            .execute()

        mensajes = generar_mensaje_benchmark(
            data.get('diferencia_vs_benchmark_tiempo', 0),
            data.get('diferencia_vs_benchmark_error', 0)
        )

        return render_template(
            'calculadora/calculadora_resultados.html',
            diagnostico=data,
            mensajes=mensajes
        )

    except Exception as e:
        logger.error(f"Error en resultados: {e}")
        return f"Error: {e}", 500


@calculadora_bp.route('/pago-exitoso')
def pago_exitoso():
    """
    ✨ NUEVO: Página de éxito después del pago con ePayco.
    ePayco redirige aquí (url_response).

    URL: /calculadora/pago-exitoso?diagnostico_id=xxx&ref=xxx
    """
    diagnostico_id = request.args.get('diagnostico_id')
    ref_payco      = request.args.get('ref')
    cancelado      = request.args.get('cancel')

    # Si el usuario canceló, redirigir a resultados
    if cancelado:
        return redirect(f"/calculadora/resultados/{diagnostico_id}?cancel=1")

    # Renderizar página de éxito
    return render_template(
        'pago_exitoso.html',
        diagnostico_id=diagnostico_id,
        ref_payco=ref_payco,
    )


# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@calculadora_bp.route('/api/submit', methods=['POST'])
def api_submit():
    """
    Procesa el formulario de 8 preguntas.
    Crea lead + diagnóstico en Supabase.
    Responde con redirect_url al Lead Gate (NO a resultados directamente).

    POST /calculadora/api/submit
    Body: { nombre, email, empresa, cargo, vacantes_activas,
            candidatos_por_vacante, principal_dolor, frecuencia_error,
            tiempo_por_cv, personas_proceso, rango_salarial }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Body vacío'}), 400

        # ── Validar campos ──────────────────────────────────────────────────
        campos_requeridos = [
            'nombre', 'email', 'empresa', 'cargo',
            'vacantes_activas', 'candidatos_por_vacante',
            'principal_dolor', 'frecuencia_error',
            'tiempo_por_cv', 'personas_proceso', 'rango_salarial'
        ]
        for campo in campos_requeridos:
            if not data.get(campo):
                return jsonify({'success': False, 'error': f'Campo requerido: {campo}'}), 400

        # ── 1. Crear o actualizar lead (SIN datos de contacto todavía) ──────
        # Nota: el lead se crea con datos mínimos. Los datos completos
        # (teléfono, empleados) llegan en el /api/lead-gate más adelante.
        lead_payload = {
            'nombre': data['nombre'],
            'email': data['email'],
            'empresa': data['empresa'],
            'cargo': data['cargo'],
            'origen_lead': 'calculadora',
            'utm_source': data.get('utm_source'),
            'utm_campaign': data.get('utm_campaign'),
        }

        existing = supabase.table('calculadora_leads') \
            .select('id') \
            .eq('email', data['email']) \
            .execute()

        if existing.data:
            lead_id = existing.data[0]['id']
            supabase.table('calculadora_leads') \
                .update(lead_payload) \
                .eq('id', lead_id) \
                .execute()
        else:
            ins = supabase.table('calculadora_leads').insert(lead_payload).execute()
            lead_id = ins.data[0]['id']

        logger.info(f"Lead procesado: {data['email']} → {lead_id}")

        # ── 2. Calcular métricas ────────────────────────────────────────────
        metricas = calcular_metricas({
            'vacantes_activas':       data['vacantes_activas'],
            'candidatos_por_vacante': data['candidatos_por_vacante'],
            'tiempo_por_cv':          data['tiempo_por_cv'],
            'personas_proceso':       data['personas_proceso'],
            'rango_salarial':         data['rango_salarial'],
            'frecuencia_error':       data['frecuencia_error'],
        })

        # ── 3. Crear diagnóstico ────────────────────────────────────────────
        diagnostico_payload = {
            'lead_id':                  lead_id,
            'vacantes_activas':         data['vacantes_activas'],
            'candidatos_por_vacante':   data['candidatos_por_vacante'],
            'principal_dolor':          data['principal_dolor'],
            'frecuencia_error':         data['frecuencia_error'],
            'tiempo_por_cv':            data['tiempo_por_cv'],
            'personas_proceso':         data['personas_proceso'],
            'rango_salarial':           data['rango_salarial'],
            'desbloqueado':             False,   # ← bloqueado hasta el gate
            'ip_address':               request.remote_addr,
            'user_agent':               request.headers.get('User-Agent'),
            **metricas,
        }

        diag = supabase.table('calculadora_diagnosticos') \
            .insert(diagnostico_payload) \
            .execute()
        diagnostico_id = diag.data[0]['id']

        logger.info(f"Diagnóstico creado: {diagnostico_id}")

        # ── 4. Registrar interacción ────────────────────────────────────────
        supabase.table('calculadora_interacciones').insert({
            'lead_id':          lead_id,
            'diagnostico_id':   diagnostico_id,
            'accion':           'formulario_completado',
            'metadata': {
                'costo_mensual': metricas['costo_operativo_mensual'],
                'ahorro_anual':  metricas['ahorro_anual'],
            }
        }).execute()

        # ── Respuesta → redirigir al GATE, no a resultados ─────────────────
        return jsonify({
            'success':      True,
            'diagnostico_id': diagnostico_id,
            'redirect_url': f'/calculadora/gate/{diagnostico_id}'   # ← GATE primero
        }), 201

    except Exception as e:
        logger.error(f"Error en api_submit: {e}")
        return jsonify({'success': False, 'error': 'Error interno'}), 500


@calculadora_bp.route('/api/lead-gate', methods=['POST'])
def api_lead_gate():
    """
    Recibe los datos del Lead Gate y desbloquea los resultados.

    POST /calculadora/api/lead-gate
    Body: {
        diagnostico_id, nombre, cargo, empresa, email,
        telefono, empleados
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Body vacío'}), 400

        diagnostico_id = data.get('diagnostico_id')
        if not diagnostico_id:
            return jsonify({'success': False, 'error': 'diagnostico_id requerido'}), 400

        # ── 1. Obtener diagnóstico ──────────────────────────────────────────
        diag = supabase.table('calculadora_diagnosticos') \
            .select('lead_id') \
            .eq('id', diagnostico_id) \
            .execute()

        if not diag.data:
            return jsonify({'success': False, 'error': 'Diagnóstico no encontrado'}), 404

        lead_id = diag.data[0]['lead_id']

        # ── 2. Actualizar lead con datos completos ──────────────────────────
        supabase.table('calculadora_leads').update({
            'nombre':    data.get('nombre'),
            'cargo':     data.get('cargo'),
            'empresa':   data.get('empresa'),
            'email':     data.get('email'),
            'telefono':  data.get('telefono'),
            'empleados': data.get('empleados'),
        }).eq('id', lead_id).execute()

        # ── 3. Desbloquear diagnóstico ──────────────────────────────────────
        supabase.table('calculadora_diagnosticos').update({
            'desbloqueado':      True,
            'desbloqueado_at':   datetime.now().isoformat(),
        }).eq('id', diagnostico_id).execute()

        # ── 4. Registrar interacción ────────────────────────────────────────
        supabase.table('calculadora_interacciones').insert({
            'lead_id':        lead_id,
            'diagnostico_id': diagnostico_id,
            'accion':         'lead_gate_completado',
            'metadata': {
                'empleados': data.get('empleados'),
                'tiene_telefono': bool(data.get('telefono')),
            }
        }).execute()

        logger.info(f"Lead Gate completado: {data.get('email')} → {diagnostico_id}")

        return jsonify({
            'success':      True,
            'redirect_url': f'/calculadora/resultados/{diagnostico_id}'
        }), 200

    except Exception as e:
        logger.error(f"Error en api_lead_gate: {e}")
        return jsonify({'success': False, 'error': 'Error interno'}), 500


@calculadora_bp.route('/api/tracking', methods=['POST'])
def api_tracking():
    """
    Registra interacciones del usuario en el dashboard de resultados.

    POST /calculadora/api/tracking
    Body: { diagnostico_id, tipo_interaccion, datos }
    """
    try:
        data = request.get_json()
        if not data or not data.get('diagnostico_id'):
            return jsonify({'success': False}), 400

        diag = supabase.table('calculadora_diagnosticos') \
            .select('lead_id') \
            .eq('id', data['diagnostico_id']) \
            .execute()

        if not diag.data:
            return jsonify({'success': False, 'error': 'No encontrado'}), 404

        lead_id = diag.data[0]['lead_id']

        supabase.table('calculadora_interacciones').insert({
            'lead_id':        lead_id,
            'diagnostico_id': data['diagnostico_id'],
            'accion':         data.get('tipo_interaccion') or data.get('accion'),
            'metadata':       data.get('datos') or data.get('metadata'),
        }).execute()

        # Actualizar flags relevantes
        flags = {}
        accion = data.get('tipo_interaccion') or data.get('accion', '')
        if accion == 'descargar_pdf':
            flags['descargado_pdf'] = True
        elif accion in ('click_agendar', 'abrio_modal_demo'):
            flags['vio_cta_demo'] = True
        elif accion == 'agenda_demo':
            flags['agendada_demo'] = True
        elif accion == 'click_registro':
            flags['click_registro'] = True
        elif accion == 'click_activar_trial':
            flags['click_trial'] = True

        if flags:
            supabase.table('calculadora_diagnosticos') \
                .update(flags) \
                .eq('id', data['diagnostico_id']) \
                .execute()

        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error en api_tracking: {e}")
        return jsonify({'success': False}), 500


@calculadora_bp.route('/api/demo', methods=['POST'])
def api_demo():
    """
    Registra una solicitud de demo desde la página de resultados.

    POST /calculadora/api/demo
    Body: { diagnostico_id, email, telefono, preferencia_horario }
    """
    try:
        data = request.get_json()
        if not data or not data.get('diagnostico_id'):
            return jsonify({'success': False, 'error': 'diagnostico_id requerido'}), 400

        resultado = registrar_demo(
            diagnostico_id=data['diagnostico_id'],
            email=data.get('email'),
            telefono=data.get('telefono'),
            preferencia_horario=data.get('preferencia_horario'),
        )

        status = 200 if resultado['success'] else 500
        return jsonify(resultado), status

    except Exception as e:
        logger.error(f"Error en api_demo: {e}")
        return jsonify({'success': False, 'error': 'Error interno'}), 500


# ==============================================================================
# ✨ NUEVAS RUTAS EPAYCO — CHECKOUT Y PAGOS
# ==============================================================================

@calculadora_bp.route('/api/checkout', methods=['POST'])
def api_checkout():
    """
    ✨ NUEVO: Genera la configuración del checkout de ePayco.

    POST /calculadora/api/checkout
    Body: {
        "plan": "pro",
        "diagnostico_id": "uuid-del-diagnostico",
        "email": "cliente@empresa.com",
        "nombre": "Ana Martínez López"
    }

    Response: {
        "success": true,
        "checkout_data": { ... },  ← pasar esto al ePayco checkout.js
        "ref_payco": "SALESAI-PRO-abc123-1234567890"
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'error': 'Body vacío'}), 400

        # Validar campos requeridos
        plan           = data.get('plan', 'pro')
        diagnostico_id = data.get('diagnostico_id')
        email          = data.get('email')
        nombre         = data.get('nombre')

        if not all([plan, diagnostico_id, email, nombre]):
            return jsonify({
                'success': False,
                'error': 'Campos requeridos: plan, diagnostico_id, email, nombre'
            }), 400

        # Llamar a la función de ePayco
        resultado = crear_checkout_epayco(
            plan=plan,
            email=email,
            diagnostico_id=diagnostico_id,
            nombre=nombre
        )

        if resultado['success']:
            # Registrar intención de pago (analytics)
            try:
                supabase.table('calculadora_interacciones').insert({
                    'diagnostico_id': diagnostico_id,
                    'accion':         'inicio_checkout',
                    'metadata':       {
                        'plan':     plan,
                        'pasarela': 'epayco'
                    }
                }).execute()
            except Exception as e:
                logger.warning(f"No se pudo registrar interacción: {e}")

            return jsonify({
                'success':       True,
                'checkout_data': resultado['checkout_data'],
                'ref_payco':     resultado['ref_payco'],
            }), 200
        else:
            return jsonify(resultado), 500

    except Exception as e:
        logger.error(f"Error en api_checkout: {e}")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor'
        }), 500


@calculadora_bp.route('/api/planes', methods=['GET'])
def api_planes():
    """
    ✨ NUEVO: Devuelve los planes disponibles para mostrar en el frontend.

    GET /calculadora/api/planes

    Response: {
        "success": true,
        "planes": {
            "starter": { "nombre": "...", "precio_usd": 79, ... },
            "pro": { ... },
            "enterprise": { ... }
        }
    }
    """
    return jsonify({
        'success': True,
        'planes': PLANES
    }), 200


# ==============================================================================
# HEALTH CHECK
# ==============================================================================

@calculadora_bp.route('/health')
def health():
    return jsonify({
        'status':    'healthy',
        'service':   'calculadora',
        'timestamp': datetime.now().isoformat()
    }), 200