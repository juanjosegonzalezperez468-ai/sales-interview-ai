"""
calculadora/routes.py
Rutas (Blueprint) para la calculadora de costos

Este archivo se integra con tu app.py existente como un Blueprint.
"""

from flask import Blueprint, render_template, request, jsonify, session
from datetime import datetime
import logging
import os

# Importar Supabase (usará la misma configuración que tu app principal)
from supabase import create_client, Client

# Importar la lógica de cálculos
from calculadora.logic import calcular_metricas, generar_mensaje_benchmark

# Crear Blueprint
calculadora_bp = Blueprint(
    'calculadora',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/calculadora'
)

# Logger
logger = logging.getLogger(__name__)

# Cliente Supabase (se inicializa con las mismas credenciales de tu app)
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)


# ============================================
# RUTAS PÚBLICAS (Landing + Formulario)
# ============================================

@calculadora_bp.route('/')
@calculadora_bp.route('/landing')
def landing():
    """
    Landing page de la calculadora
    URL: /calculadora/ o /calculadora/landing
    """
    return render_template('calculadora/calculadora_landing.html')


@calculadora_bp.route('/formulario')
def formulario():
    """
    Formulario de 8 preguntas
    URL: /calculadora/formulario
    """
    # TODO: Crear este template
    return render_template('calculadora/calculadora_formulario.html')


@calculadora_bp.route('/resultados/<diagnostico_id>')
def resultados(diagnostico_id):
    """
    Página de resultados
    URL: /calculadora/resultados/<id>
    """
    try:
        # Obtener diagnóstico de Supabase
        diagnostico = supabase.table('diagnosticos').select('*, leads(*)').eq('id', diagnostico_id).execute()
        
        if not diagnostico.data:
            return "Diagnóstico no encontrado", 404
        
        data = diagnostico.data[0]
        
        # Marcar como visto
        supabase.table('diagnosticos').update({'visto_resultados': True}).eq('id', diagnostico_id).execute()
        
        # Generar mensajes de benchmark
        mensajes_benchmark = generar_mensaje_benchmark(
            data['diferencia_vs_benchmark_tiempo'],
            data['diferencia_vs_benchmark_error']
        )
        
        # TODO: Crear este template
        return render_template(
            'calculadora/calculadora_resultados.html',
            diagnostico=data,
            mensajes=mensajes_benchmark
        )
        
    except Exception as e:
        logger.error(f"Error en resultados: {str(e)}")
        return f"Error: {str(e)}", 500


# ============================================
# API ENDPOINTS (para AJAX)
# ============================================

@calculadora_bp.route('/api/submit', methods=['POST'])
def api_submit():
    """
    API: Procesar formulario y guardar en Supabase
    POST /calculadora/api/submit
    
    Body JSON:
    {
        "nombre": "...",
        "email": "...",
        "empresa": "...",
        "cargo": "...",
        "vacantes_activas": "4-10",
        "candidatos_por_vacante": "21-50",
        "principal_dolor": "...",
        "frecuencia_error": "3 de cada 10",
        "tiempo_por_cv": "8-15 min",
        "personas_proceso": "2-3",
        "rango_salarial": "$6-10k"
    }
    """
    try:
        data = request.get_json()
        
        # Validar campos requeridos
        campos_requeridos = [
            'nombre', 'email', 'empresa', 'cargo',
            'vacantes_activas', 'candidatos_por_vacante',
            'principal_dolor', 'frecuencia_error',
            'tiempo_por_cv', 'personas_proceso', 'rango_salarial'
        ]
        
        for campo in campos_requeridos:
            if campo not in data or not data[campo]:
                return jsonify({
                    'success': False,
                    'error': f'Campo requerido faltante: {campo}'
                }), 400
        
        # 1. CREAR O ACTUALIZAR LEAD
        lead_data = {
            'nombre': data['nombre'],
            'email': data['email'],
            'empresa': data['empresa'],
            'cargo': data['cargo'],
            'telefono': data.get('telefono'),
            'origen_lead': 'calculadora',
            'utm_source': data.get('utm_source'),
            'utm_campaign': data.get('utm_campaign')
        }
        
        # Verificar si el lead ya existe
        existing_lead = supabase.table('leads').select('*').eq('email', data['email']).execute()
        
        if existing_lead.data:
            lead_id = existing_lead.data[0]['id']
            supabase.table('leads').update(lead_data).eq('id', lead_id).execute()
        else:
            lead_result = supabase.table('leads').insert(lead_data).execute()
            lead_id = lead_result.data[0]['id']
        
        logger.info(f"Lead procesado: {data['email']}")
        
        # 2. CALCULAR MÉTRICAS
        metricas = calcular_metricas({
            'vacantes_activas': data['vacantes_activas'],
            'candidatos_por_vacante': data['candidatos_por_vacante'],
            'tiempo_por_cv': data['tiempo_por_cv'],
            'personas_proceso': data['personas_proceso'],
            'rango_salarial': data['rango_salarial'],
            'frecuencia_error': data['frecuencia_error']
        })
        
        # 3. GUARDAR DIAGNÓSTICO
        diagnostico_data = {
            'lead_id': lead_id,
            'vacantes_activas': data['vacantes_activas'],
            'candidatos_por_vacante': data['candidatos_por_vacante'],
            'principal_dolor': data['principal_dolor'],
            'frecuencia_error': data['frecuencia_error'],
            'tiempo_por_cv': data['tiempo_por_cv'],
            'personas_proceso': data['personas_proceso'],
            'rango_salarial': data['rango_salarial'],
            **metricas,
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent')
        }
        
        diagnostico_result = supabase.table('diagnosticos').insert(diagnostico_data).execute()
        diagnostico_id = diagnostico_result.data[0]['id']
        
        logger.info(f"Diagnóstico creado: {diagnostico_id}")
        
        # 4. REGISTRAR INTERACCIÓN
        supabase.table('interacciones').insert({
            'lead_id': lead_id,
            'diagnostico_id': diagnostico_id,
            'tipo_interaccion': 'formulario_completado',
            'datos': {
                'costo_mensual': metricas['costo_operativo_mensual'],
                'ahorro_anual': metricas['ahorro_anual']
            }
        }).execute()
        
        # 5. GENERAR MENSAJES DE BENCHMARK
        mensajes_benchmark = generar_mensaje_benchmark(
            metricas['diferencia_vs_benchmark_tiempo'],
            metricas['diferencia_vs_benchmark_error']
        )
        
        return jsonify({
            'success': True,
            'diagnostico_id': diagnostico_id,
            'redirect_url': f'/calculadora/resultados/{diagnostico_id}'
        }), 201
        
    except Exception as e:
        logger.error(f"Error en api_submit: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Error procesando el formulario'
        }), 500


@calculadora_bp.route('/api/tracking', methods=['POST'])
def api_tracking():
    """
    API: Registrar interacciones del usuario
    POST /calculadora/api/tracking
    
    Body JSON:
    {
        "diagnostico_id": "uuid",
        "tipo_interaccion": "descargar_pdf",
        "datos": {...}
    }
    """
    try:
        data = request.get_json()
        
        # Obtener lead_id del diagnóstico
        diagnostico = supabase.table('diagnosticos').select('lead_id').eq('id', data['diagnostico_id']).execute()
        
        if not diagnostico.data:
            return jsonify({'success': False, 'error': 'Diagnóstico no encontrado'}), 404
        
        lead_id = diagnostico.data[0]['lead_id']
        
        # Registrar interacción
        supabase.table('interacciones').insert({
            'lead_id': lead_id,
            'diagnostico_id': data['diagnostico_id'],
            'tipo_interaccion': data['tipo_interaccion'],
            'datos': data.get('datos')
        }).execute()
        
        # Actualizar flags en diagnóstico
        if data['tipo_interaccion'] == 'descargar_pdf':
            supabase.table('diagnosticos').update({'descargado_pdf': True}).eq('id', data['diagnostico_id']).execute()
        elif data['tipo_interaccion'] == 'click_agendar':
            supabase.table('diagnosticos').update({'agendada_demo': True}).eq('id', data['diagnostico_id']).execute()
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        logger.error(f"Error en api_tracking: {str(e)}")
        return jsonify({'success': False}), 500


# ============================================
# HEALTH CHECK
# ============================================

@calculadora_bp.route('/health')
def health():
    """Health check para la calculadora"""
    return jsonify({
        'status': 'healthy',
        'service': 'calculadora',
        'timestamp': datetime.now().isoformat()
    }), 200