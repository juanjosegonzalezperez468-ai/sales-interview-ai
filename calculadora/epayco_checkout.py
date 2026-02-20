"""
Blueprint de pagos con ePayco
Rutas:
  GET  /epayco/checkout/<diagnostico_id>  → página de pago
  POST /epayco/webhook                    → confirmación ePayco
  GET  /epayco/verificar/<ref_payco>      → verificación manual
  GET  /epayco/reporte/<diagnostico_id>   → reporte desbloqueado
"""

import os
import hashlib
import hmac
import json
import uuid
import logging
import requests
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, abort
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

epayco_bp = Blueprint('epayco', __name__)

# ── Supabase ──────────────────────────────────────────────
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# ── Credenciales ePayco ───────────────────────────────────
EPAYCO_P_CUST_ID  = os.getenv('EPAYCO_P_CUST_ID_CLIENTE')
EPAYCO_P_KEY      = os.getenv('EPAYCO_P_KEY')
EPAYCO_PUBLIC_KEY = os.getenv('EPAYCO_PUBLIC_KEY', '')
EPAYCO_TEST       = os.getenv('EPAYCO_TEST', 'true').lower() == 'true'

PRECIO_USD = 29.00
PRECIO_COP = int(os.getenv('PRECIO_COP', '120000'))  # Precio en COP para ePayco


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def get_diagnostico(diagnostico_id: str):
    """Obtiene diagnóstico con su lead asociado."""
    try:
        res = supabase.table('calculadora_diagnosticos')\
            .select('*, calculadora_leads(*)')\
            .eq('id', diagnostico_id)\
            .single()\
            .execute()
        return res.data
    except Exception as e:
        logger.error(f"❌ get_diagnostico: {e}")
        return None


def get_pago_por_diagnostico(diagnostico_id: str):
    """Retorna el pago aprobado de un diagnóstico, si existe."""
    try:
        res = supabase.table('calculadora_pagos')\
            .select('*')\
            .eq('diagnostico_id', diagnostico_id)\
            .eq('estado', 'aprobado')\
            .execute()
        return res.data[0] if res.data else None
    except:
        return None


def generar_ref_interna(diagnostico_id: str) -> str:
    """Genera referencia única interna para el pago."""
    corto = diagnostico_id[:8].upper()
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"SALESAI-{corto}-{timestamp}"


def verificar_firma_epayco(data: dict) -> bool:
    """
    Verifica la firma del webhook de ePayco.
    Firma = SHA256(P_CUST_ID_CLIENTE + P_KEY + x_ref_payco + x_transaction_id + x_amount + x_currency_code)
    """
    try:
        cadena = (
            str(EPAYCO_P_CUST_ID) +
            str(EPAYCO_P_KEY) +
            str(data.get('x_ref_payco', '')) +
            str(data.get('x_transaction_id', '')) +
            str(data.get('x_amount', '')) +
            str(data.get('x_currency_code', ''))
        )
        firma_calculada = hashlib.sha256(cadena.encode('utf-8')).hexdigest()
        firma_recibida  = data.get('x_signature', '')
        return hmac.compare_digest(firma_calculada, firma_recibida)
    except Exception as e:
        logger.error(f"❌ verificar_firma_epayco: {e}")
        return False


def crear_pago_pendiente(diagnostico_id: str, lead_id: str, ref_interna: str):
    """Crea registro de pago en estado pendiente."""
    try:
        res = supabase.table('calculadora_pagos').insert({
            'diagnostico_id': diagnostico_id,
            'lead_id': lead_id,
            'ref_interna': ref_interna,
            'estado': 'pendiente',
            'monto': PRECIO_USD,
            'moneda': 'USD',
        }).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"❌ crear_pago_pendiente: {e}")
        return None


def marcar_pago_aprobado(ref_interna: str, ref_payco: str, payload: dict):
    """Actualiza el pago a aprobado con datos de ePayco."""
    try:
        supabase.table('calculadora_pagos').update({
            'estado': 'aprobado',
            'ref_payco': ref_payco,
            'codigo_respuesta': str(payload.get('x_response_code', '')),
            'respuesta_epayco': payload,
            'fecha_pago': datetime.now().isoformat(),
        }).eq('ref_interna', ref_interna).execute()
    except Exception as e:
        logger.error(f"❌ marcar_pago_aprobado: {e}")


def marcar_pago_rechazado(ref_interna: str, ref_payco: str, payload: dict, estado='rechazado'):
    try:
        supabase.table('calculadora_pagos').update({
            'estado': estado,
            'ref_payco': ref_payco,
            'codigo_respuesta': str(payload.get('x_response_code', '')),
            'respuesta_epayco': payload,
        }).eq('ref_interna', ref_interna).execute()
    except Exception as e:
        logger.error(f"❌ marcar_pago_rechazado: {e}")


# ════════════════════════════════════════════════════════════
# RUTAS
# ════════════════════════════════════════════════════════════

@epayco_bp.route('/checkout/<diagnostico_id>')
def checkout(diagnostico_id):
    """Página de checkout — muestra el formulario de pago de ePayco."""

    diagnostico = get_diagnostico(diagnostico_id)
    if not diagnostico:
        abort(404)

    # Si ya pagó, redirigir al reporte
    pago_existente = get_pago_por_diagnostico(diagnostico_id)
    if pago_existente:
        return redirect(url_for('epayco.reporte', diagnostico_id=diagnostico_id))

    lead = diagnostico.get('calculadora_leads', {}) or {}

    # Crear referencia interna y registro pendiente
    ref_interna = generar_ref_interna(diagnostico_id)
    crear_pago_pendiente(
        diagnostico_id=diagnostico_id,
        lead_id=lead.get('id', ''),
        ref_interna=ref_interna,
    )

    # URL base del servidor
    base_url = os.getenv('BASE_URL', 'https://tuapp.com')

    return render_template('checkout.html',
        diagnostico=diagnostico,
        lead=lead,
        ref_interna=ref_interna,
        precio_cop=PRECIO_COP,
        precio_usd=PRECIO_USD,
        epayco_public_key=EPAYCO_PUBLIC_KEY,
        epayco_test=str(EPAYCO_TEST).lower(),
        url_respuesta=f"{base_url}/epayco/respuesta",
        url_confirmacion=f"{base_url}/epayco/webhook",
    )


@epayco_bp.route('/webhook', methods=['POST'])
def webhook():
    """
    Webhook de confirmación de ePayco.
    ePayco hace POST con los datos del pago.
    """
    try:
        data = request.form.to_dict() or request.get_json(silent=True) or {}
        logger.info(f"📩 Webhook ePayco recibido: {data.get('x_ref_payco', 'sin_ref')}")

        # Verificar firma
        if not verificar_firma_epayco(data):
            logger.warning("⚠️ Firma inválida en webhook ePayco")
            return jsonify({'error': 'firma_invalida'}), 400

        ref_interna  = data.get('x_extra1', '')   # Enviamos ref_interna en extra1
        ref_payco    = data.get('x_ref_payco', '')
        codigo_resp  = str(data.get('x_response_code', '0'))

        # Códigos ePayco: 1=Aceptada, 2=Rechazada, 3=Pendiente, 4=Fallida, 6=Reversada
        if codigo_resp == '1':
            marcar_pago_aprobado(ref_interna, ref_payco, data)
            logger.info(f"✅ Pago aprobado: {ref_interna}")
        elif codigo_resp in ['2', '4', '6']:
            marcar_pago_rechazado(ref_interna, ref_payco, data, estado='rechazado')
            logger.info(f"❌ Pago rechazado ({codigo_resp}): {ref_interna}")
        elif codigo_resp == '3':
            marcar_pago_rechazado(ref_interna, ref_payco, data, estado='pendiente')
            logger.info(f"⏳ Pago pendiente: {ref_interna}")

        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        logger.error(f"❌ Error en webhook ePayco: {e}")
        return jsonify({'error': str(e)}), 500


@epayco_bp.route('/respuesta')
def respuesta():
    """
    Página de retorno post-pago (ePayco redirige aquí).
    Verifica el estado y redirige al reporte o muestra error.
    """
    ref_payco   = request.args.get('ref_payco', '')
    ref_interna = request.args.get('extra1', '')
    codigo      = str(request.args.get('response_code', '0'))

    if codigo == '1':
        # Buscar el diagnóstico por ref_interna
        try:
            res = supabase.table('calculadora_pagos')\
                .select('diagnostico_id')\
                .eq('ref_interna', ref_interna)\
                .execute()
            if res.data:
                diag_id = res.data[0]['diagnostico_id']
                return redirect(url_for('epayco.reporte', diagnostico_id=diag_id))
        except:
            pass

    # Pago no aprobado — redirigir con mensaje
    return render_template('pago_fallido.html', codigo=codigo, ref_payco=ref_payco)


@epayco_bp.route('/verificar/<ref_payco>')
def verificar(ref_payco):
    """Verificación manual de un pago por referencia ePayco."""
    try:
        url = f"https://secure.epayco.co/validation/v1/reference/{ref_payco}"
        headers = {'Authorization': f'Bearer {EPAYCO_PUBLIC_KEY}'}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()

        if data.get('data', {}).get('x_response_code') == '1':
            return jsonify({'estado': 'aprobado', 'data': data})
        return jsonify({'estado': 'no_aprobado', 'data': data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@epayco_bp.route('/reporte/<diagnostico_id>')
def reporte(diagnostico_id):
    """
    Reporte completo desbloqueado post-pago.
    Requiere pago aprobado.
    """
    pago = get_pago_por_diagnostico(diagnostico_id)
    if not pago:
        return redirect(url_for('epayco.checkout', diagnostico_id=diagnostico_id))

    diagnostico = get_diagnostico(diagnostico_id)
    if not diagnostico:
        abort(404)

    return render_template('reporte_completo.html',
        diagnostico=diagnostico,
        pago=pago,
        lead=diagnostico.get('calculadora_leads', {}),
    )