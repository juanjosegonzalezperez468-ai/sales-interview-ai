"""
calculadora/api_calculadora.py
Endpoints API adicionales para la calculadora
"""

from flask import Blueprint, jsonify, request
from datetime import datetime
import logging
import os
from supabase import create_client, Client

# Logger
logger = logging.getLogger(__name__)

# Cliente Supabase
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)


def registrar_demo(diagnostico_id: str, email: str, telefono: str = None, preferencia_horario: str = None):
    """
    Registra una solicitud de demo
    
    Args:
        diagnostico_id: ID del diagnóstico
        email: Email del lead
        telefono: Teléfono opcional
        preferencia_horario: Preferencia de horario
    
    Returns:
        dict con resultado
    """
    try:
        # Obtener lead_id del diagnóstico
        diagnostico = supabase.table('calculadora_diagnosticos') \
            .select('lead_id') \
            .eq('id', diagnostico_id) \
            .execute()
        
        if not diagnostico.data:
            return {'success': False, 'error': 'Diagnóstico no encontrado'}
        
        lead_id = diagnostico.data[0]['lead_id']
        
        # Insertar solicitud de demo
        demo_data = {
            'lead_id': lead_id,
            'diagnostico_id': diagnostico_id,
            'email': email,
            'telefono': telefono,
            'preferencia_horario': preferencia_horario,
            'estado': 'pendiente',
            'origen': 'calculadora_resultados'
        }
        
        result = supabase.table('calculadora_demos').insert(demo_data).execute()
        
        # Actualizar diagnóstico
        supabase.table('calculadora_diagnosticos') \
            .update({'agendada_demo': True}) \
            .eq('id', diagnostico_id) \
            .execute()
        
        # Registrar interacción
        supabase.table('calculadora_interacciones').insert({
            'lead_id': lead_id,
            'diagnostico_id': diagnostico_id,
            'accion': 'agenda_demo',
            'metadata': {
                'preferencia_horario': preferencia_horario,
                'telefono_proporcionado': telefono is not None
            }
        }).execute()
        
        logger.info(f"Demo agendada para lead {lead_id}, diagnóstico {diagnostico_id}")
        
        return {
            'success': True,
            'demo_id': result.data[0]['id'],
            'mensaje': 'Demo agendada exitosamente'
        }
        
    except Exception as e:
        logger.error(f"Error en registrar_demo: {str(e)}")
        return {'success': False, 'error': str(e)}


def registrar_interaccion(diagnostico_id: str, accion: str, metadata: dict = None):
    """
    Registra una interacción del usuario
    
    Args:
        diagnostico_id: ID del diagnóstico
        accion: Tipo de acción realizada
        metadata: Datos adicionales
    
    Returns:
        dict con resultado
    """
    try:
        # Obtener lead_id del diagnóstico
        diagnostico = supabase.table('calculadora_diagnosticos') \
            .select('lead_id') \
            .eq('id', diagnostico_id) \
            .execute()
        
        if not diagnostico.data:
            return {'success': False, 'error': 'Diagnóstico no encontrado'}
        
        lead_id = diagnostico.data[0]['lead_id']
        
        # Insertar interacción
        interaccion_data = {
            'lead_id': lead_id,
            'diagnostico_id': diagnostico_id,
            'accion': accion,
            'metadata': metadata or {},
            'user_agent': request.headers.get('User-Agent'),
            'ip_address': request.remote_addr
        }
        
        supabase.table('calculadora_interacciones').insert(interaccion_data).execute()
        
        # Actualizar flags en diagnóstico según la acción
        updates = {}
        
        if accion == 'descarga_pdf':
            updates['descargado_pdf'] = True
        elif accion == 'abrio_modal_demo':
            updates['vio_cta_demo'] = True
        elif accion == 'click_registro':
            updates['click_registro'] = True
        
        if updates:
            supabase.table('calculadora_diagnosticos') \
                .update(updates) \
                .eq('id', diagnostico_id) \
                .execute()
        
        return {'success': True}
        
    except Exception as e:
        logger.error(f"Error en registrar_interaccion: {str(e)}")
        return {'success': False, 'error': str(e)}