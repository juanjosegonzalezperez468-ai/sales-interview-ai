import os
import logging
import requests
import hashlib
from flask import Blueprint, request, jsonify, render_template
from supabase import create_client, Client
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Configuración ePayco (TUS CREDENCIALES REALES) ────────────────────────────
EPAYCO_PUBLIC_KEY    = os.getenv('EPAYCO_PUBLIC_KEY', '919c2b11b69b390481d2bcadddaab51c')
EPAYCO_PRIVATE_KEY   = os.getenv('EPAYCO_PRIVATE_KEY', '2ce1e122119c275559caefc67ccb280dI')  # ← PÉGALA AQUÍ
EPAYCO_CUSTOMER_ID   = os.getenv('EPAYCO_CUSTOMER_ID', '1573995')
EPAYCO_TEST_MODE     = os.getenv('EPAYCO_TEST_MODE', 'false').lower() == 'true'
BASE_URL             = os.getenv('BASE_URL', 'https://salesai.com.co')

# ── Supabase ──────────────────────────────────────────────────────────────────
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# ── Planes (Precios en USD para ePayco) ───────────────────────────────────────
PLANES = {
    'starter': {
        'nombre':       'Sales AI Starter',
        'precio_usd':   79,
        'precio_cop':   289000,  # Referencia visual
        'descripcion':  '3 vacantes · 150 candidatos/mes · Scoring automático',
    },
    'pro': {
        'nombre':       'Sales AI Pro',
        'precio_usd':   99,
        'precio_cop':   363000,
        'descripcion':  '10 vacantes · Candidatos ilimitados · IA avanzada',
    },
    'enterprise': {
        'nombre':       'Sales AI Enterprise',
        'precio_usd':   149,
        'precio_cop':   547000,
        'descripcion':  'Vacantes ilimitadas · Multi-empresa · API',
    },
}

# ── Blueprint ─────────────────────────────────────────────────────────────────
epayco_bp = Blueprint('epayco_bp', __name__)


# ==============================================================================
# GENERAR DATOS PARA EPAYCO CHECKOUT (Web Checkout Modal)
# ==============================================================================

def crear_checkout_epayco(plan: str, email: str, diagnostico_id: str, nombre: str = None):
    """
    Genera la configuración para el ePayco Web Checkout.
    
    ePayco usa un checkout modal en tu página (no redirige como Stripe).
    El frontend llama checkout.js con estos parámetros.
    
    Args:
        plan:           'starter' | 'pro' | 'enterprise'
        email:          Email del cliente
        diagnostico_id: UUID del diagnóstico
        nombre:         Nombre completo del cliente
    
    Returns:
        dict con 'success' y 'checkout_data' para pasar al JS
    """
    if plan not in PLANES:
        return {'success': False, 'error': f'Plan inválido: {plan}'}
    
    plan_data = PLANES[plan]
    
    # Generar referencia única
    timestamp = int(datetime.now().timestamp())
    ref_payco = f"SALESAI-{plan.upper()}-{diagnostico_id[:8]}-{timestamp}"
    
    # Extraer nombre y apellido
    partes_nombre = (nombre or email.split('@')[0]).split(' ', 1)
    nombres = partes_nombre[0]
    apellidos = partes_nombre[1] if len(partes_nombre) > 1 else ''
    
    checkout_config = {
        # Identificación del comercio
        'key':      EPAYCO_PUBLIC_KEY,
        'test':     'true' if EPAYCO_TEST_MODE else 'false',
        
        # Datos del producto
        'name':         plan_data['nombre'],
        'description':  plan_data['descripcion'],
        'invoice':      ref_payco,
        'currency':     'usd',  # ePayco acepta USD para suscripciones
        'amount':       str(plan_data['precio_usd']),
        'tax_base':     '0',
        'tax':          '0',
        'country':      'co',
        'lang':         'es',
        
        # Datos del cliente (pre-llenados)
        'name_billing':  nombres,
        'surname_billing': apellidos,
        'email_billing': email,
        
        # URLs de confirmación
        'url_confirmation': f"{BASE_URL}/epayco/webhook",
        'url_response':     f"{BASE_URL}/calculadora/pago-exitoso?diagnostico_id={diagnostico_id}&ref={ref_payco}",
        'method_confirmation': 'POST',
        
        # Metadata (para identificar en webhook)
        'extra1': diagnostico_id,
        'extra2': plan,
        'extra3': email,
    }
    
    logger.info(f"✅ Checkout ePayco generado: plan={plan} email={email} ref={ref_payco}")
    
    return {
        'success': True,
        'checkout_data': checkout_config,
        'ref_payco': ref_payco,
    }


# ==============================================================================
# WEBHOOK — ePayco llama aquí después de cada transacción
# ==============================================================================

@epayco_bp.route('/epayco/webhook', methods=['POST'])
def webhook():
    """
    Webhook de ePayco — Confirmación de pagos
    
    Configura esta URL en: app.epayco.co → Configuración → URL de confirmación
    URL: https://salesai.com.co/epayco/webhook
    
    ePayco envía datos via POST (form-data, no JSON):
    - x_cust_id_cliente:     tu customer ID (1573995)
    - x_ref_payco:          referencia única del pago
    - x_transaction_id:     ID de transacción
    - x_amount:             monto pagado
    - x_currency_code:      moneda (USD)
    - x_transaction_state:  'Aceptada' | 'Rechazada' | 'Pendiente'
    - x_signature:          firma de seguridad
    - x_extra1, x_extra2, x_extra3: tus metadatos
    """
    try:
        # ePayco envía form-data, no JSON
        data = request.form.to_dict()
        logger.info(f"📩 Webhook ePayco recibido: ref={data.get('x_ref_payco')} estado={data.get('x_transaction_state')}")
        
        # ── VALIDAR FIRMA (SEGURIDAD) ────────────────────────────────────────
        firma_recibida = data.get('x_signature', '')
        if not _validar_firma_epayco(data, firma_recibida):
            logger.error("❌ Firma de webhook inválida — posible intento de fraude")
            return jsonify({'error': 'Invalid signature'}), 400
        
        # ── PROCESAR SEGÚN ESTADO ─────────────────────────────────────────────
        estado = data.get('x_transaction_state', '').lower()
        cod_estado = data.get('x_cod_transaction_state', '')  # 1=Aceptada, 2=Rechazada, 3=Pendiente
        
        if estado == 'aceptada' or cod_estado == '1':
            _activar_cuenta_usuario(data)
        
        elif estado == 'rechazada' or cod_estado == '2':
            _on_pago_rechazado(data)
        
        elif estado == 'pendiente' or cod_estado == '3':
            _on_pago_pendiente(data)
        
        return jsonify({'received': True}), 200
        
    except Exception as e:
        logger.error(f"❌ Error en webhook ePayco: {e}")
        return jsonify({'error': 'Internal server error'}), 500


def _validar_firma_epayco(data: dict, firma_recibida: str) -> bool:
    """
    Valida la firma SHA256 de ePayco para seguridad.
    
    Fórmula de ePayco:
    SHA256(p_cust_id_cliente + "^" + p_key + "^" + x_ref_payco + "^" + 
           x_transaction_id + "^" + x_amount + "^" + x_currency_code)
    """
    try:
        cadena_firma = (
            f"{EPAYCO_CUSTOMER_ID}^"
            f"{EPAYCO_PUBLIC_KEY}^"
            f"{data.get('x_ref_payco', '')}^"
            f"{data.get('x_transaction_id', '')}^"
            f"{data.get('x_amount', '')}^"
            f"{data.get('x_currency_code', '')}"
        )
        
        firma_calculada = hashlib.sha256(cadena_firma.encode()).hexdigest()
        
        es_valida = firma_calculada == firma_recibida
        
        if not es_valida:
            logger.warning(f"Firma esperada: {firma_calculada}")
            logger.warning(f"Firma recibida: {firma_recibida}")
        
        return es_valida
        
    except Exception as e:
        logger.error(f"Error validando firma: {e}")
        return False


def _activar_cuenta_usuario(data: dict):
    """
    Pago aceptado → Activar cuenta del usuario en Supabase.
    """
    try:
        # Extraer datos del webhook
        diagnostico_id = data.get('x_extra1')
        plan           = data.get('x_extra2', 'pro')
        email          = data.get('x_extra3') or data.get('x_customer_email')
        ref_payco      = data.get('x_ref_payco')
        transaction_id = data.get('x_transaction_id')
        monto          = data.get('x_amount')
        
        if not diagnostico_id or not email:
            logger.warning("⚠️  Webhook sin diagnostico_id o email")
            return
        
        # 1. Buscar lead por email
        lead_response = supabase.table('calculadora_leads') \
            .select('id') \
            .eq('email', email) \
            .execute()
        
        if not lead_response.data:
            logger.warning(f"⚠️  Lead no encontrado para email: {email}")
            return
        
        lead_id = lead_response.data[0]['id']
        
        # 2. Actualizar lead con datos de suscripción
        supabase.table('calculadora_leads').update({
            'epayco_customer_id':     data.get('x_customer_id'),
            'epayco_subscription_id': transaction_id,
            'plan_activo':            plan,
            'suscripcion_activa':     True,
            'trial_activo':           True,
            'trial_inicio':           datetime.now().isoformat(),
            'convertido':             True,
            'convertido_at':          datetime.now().isoformat(),
        }).eq('id', lead_id).execute()
        
        # 3. Actualizar diagnóstico
        supabase.table('calculadora_diagnosticos').update({
            'pago_completado':  True,
            'plan_contratado':  plan,
            'epayco_ref_payco': ref_payco,
        }).eq('id', diagnostico_id).execute()
        
        # 4. Registrar interacción (analytics)
        supabase.table('calculadora_interacciones').insert({
            'lead_id':        lead_id,
            'diagnostico_id': diagnostico_id,
            'accion':         'pago_completado',
            'metadata': {
                'plan':           plan,
                'ref_payco':      ref_payco,
                'transaction_id': transaction_id,
                'monto':          monto,
                'pasarela':       'epayco',
            }
        }).execute()
        
        logger.info(f"✅ CUENTA ACTIVADA: {email} → {plan} (ref: {ref_payco})")
        
    except Exception as e:
        logger.error(f"❌ Error activando cuenta: {e}")


def _on_pago_rechazado(data: dict):
    """Pago rechazado — Registrar para análisis."""
    diagnostico_id = data.get('x_extra1')
    email          = data.get('x_extra3')
    razon          = data.get('x_response_reason_text', 'Desconocida')
    
    logger.warning(f"⚠️  Pago RECHAZADO: {email} - Razón: {razon}")
    
    # TODO Fase 2: enviar email al usuario notificando el rechazo


def _on_pago_pendiente(data: dict):
    """Pago pendiente — PSE o pago en efectivo."""
    diagnostico_id = data.get('x_extra1')
    email          = data.get('x_extra3')
    
    logger.info(f"⏳ Pago PENDIENTE: {email} (probablemente PSE o efectivo)")
    
    # TODO Fase 2: enviar email notificando que el pago está en proceso


# ==============================================================================
# OBTENER INFORMACIÓN DE PLANES (para el frontend)
# ==============================================================================

def obtener_planes():
    """Retorna los planes disponibles para mostrar en la UI."""
    return PLANES