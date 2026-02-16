// calculadora/static/js/calculadora.js
// JavaScript para formulario multi-step

let currentStep = 1;
const totalSteps = 8;

// Elementos del DOM
const form = document.getElementById('calculadora-form');
const btnPrev = document.getElementById('btn-prev');
const btnNext = document.getElementById('btn-next');
const btnSubmit = document.getElementById('btn-submit');
const loading = document.getElementById('loading');
const currentStepSpan = document.getElementById('current-step');

// Inicializar
document.addEventListener('DOMContentLoaded', () => {
    console.log('Formulario inicializado');
    updateUI();
    setupEventListeners();
});

// Event listeners
function setupEventListeners() {
    // Navegación
    if (btnNext) {
        btnNext.addEventListener('click', nextStep);
        console.log('Evento click en btnNext agregado');
    }
    if (btnPrev) {
        btnPrev.addEventListener('click', prevStep);
    }
    
    // Submit
    if (form) {
        form.addEventListener('submit', handleSubmit);
    }
    
    // Auto-avanzar al seleccionar radio button
    const radioInputs = form.querySelectorAll('input[type="radio"]');
    console.log(`Radio inputs encontrados: ${radioInputs.length}`);
    radioInputs.forEach(input => {
        input.addEventListener('change', () => {
            console.log('Radio seleccionado:', input.name, input.value);
            // Pequeño delay para que se vea la selección
            setTimeout(() => {
                if (currentStep < totalSteps) {
                    nextStep();
                }
            }, 300);
        });
    });
}

// Avanzar paso
function nextStep() {
    console.log('nextStep llamado. Step actual:', currentStep);
    
    const isValid = validateStep(currentStep);
    console.log('Validación resultado:', isValid);
    
    if (!isValid) {
        showError('Por favor selecciona una opción antes de continuar');
        return;
    }
    
    if (currentStep < totalSteps) {
        hideStep(currentStep);
        currentStep++;
        showStep(currentStep);
        updateUI();
        console.log('Avanzado a step:', currentStep);
    }
}

// Retroceder paso
function prevStep() {
    if (currentStep > 1) {
        hideStep(currentStep);
        currentStep--;
        showStep(currentStep);
        updateUI();
        console.log('Retrocedido a step:', currentStep);
    }
}

// Mostrar paso
function showStep(step) {
    const stepCard = document.querySelector(`[data-step="${step}"]`);
    if (stepCard) {
        stepCard.classList.remove('hidden');
        // Scroll suave al top
        window.scrollTo({ top: 0, behavior: 'smooth' });
        console.log('Mostrando step:', step);
    } else {
        console.error('Step card no encontrado:', step);
    }
}

// Ocultar paso
function hideStep(step) {
    const stepCard = document.querySelector(`[data-step="${step}"]`);
    if (stepCard) {
        stepCard.classList.add('hidden');
        console.log('Ocultando step:', step);
    }
}

// Actualizar UI (botones, progress bar)
function updateUI() {
    // Actualizar contador
    if (currentStepSpan) {
        currentStepSpan.textContent = currentStep;
    }
    
    // Actualizar progress dots
    for (let i = 1; i <= totalSteps; i++) {
        const dot = document.getElementById(`progress-dot-${i}`);
        if (dot) {
            if (i < currentStep) {
                dot.classList.add('completed');
                dot.classList.remove('active');
            } else if (i === currentStep) {
                dot.classList.add('active');
                dot.classList.remove('completed');
            } else {
                dot.classList.remove('active', 'completed');
            }
        }
    }
    
    // Mostrar/ocultar botones
    if (btnPrev) {
        if (currentStep === 1) {
            btnPrev.classList.add('hidden');
        } else {
            btnPrev.classList.remove('hidden');
        }
    }
    
    if (btnNext && btnSubmit) {
        if (currentStep === totalSteps) {
            btnNext.classList.add('hidden');
            btnSubmit.classList.remove('hidden');
        } else {
            btnNext.classList.remove('hidden');
            btnSubmit.classList.add('hidden');
        }
    }
}

// Validar paso actual
function validateStep(step) {
    const stepCard = document.querySelector(`[data-step="${step}"]`);
    
    if (!stepCard) {
        console.error(`Step card ${step} not found`);
        return false;
    }
    
    // Para pasos con radio buttons
    const radioInputs = stepCard.querySelectorAll('input[type="radio"]');
    if (radioInputs.length > 0) {
        const radioName = radioInputs[0].name;
        const checked = stepCard.querySelector(`input[name="${radioName}"]:checked`);
        console.log(`Step ${step}: Radio name=${radioName}, checked=`, checked);
        return checked !== null;
    }
    
    // Para paso de datos de contacto (step 7)
    if (step === 7) {
        const nombre = stepCard.querySelector('input[name="nombre"]');
        const email = stepCard.querySelector('input[name="email"]');
        const empresa = stepCard.querySelector('input[name="empresa"]');
        const cargo = stepCard.querySelector('input[name="cargo"]');
        
        if (!nombre || !nombre.value.trim()) {
            showError('Por favor ingresa tu nombre');
            if (nombre) nombre.focus();
            return false;
        }
        
        if (!email || !email.value.trim() || !isValidEmail(email.value)) {
            showError('Por favor ingresa un email válido');
            if (email) email.focus();
            return false;
        }
        
        if (!empresa || !empresa.value.trim()) {
            showError('Por favor ingresa el nombre de tu empresa');
            if (empresa) empresa.focus();
            return false;
        }
        
        if (!cargo || !cargo.value.trim()) {
            showError('Por favor ingresa tu cargo');
            if (cargo) cargo.focus();
            return false;
        }
        
        return true;
    }
    
    return true;
}

// Validar email
function isValidEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

// Mostrar error
function showError(message) {
    console.log('Error mostrado:', message);
    // Crear toast de error
    const toast = document.createElement('div');
    toast.className = 'fixed top-4 right-4 bg-red-500 text-white px-6 py-3 rounded-lg shadow-lg z-50 animate-slide-in';
    toast.textContent = message;
    document.body.appendChild(toast);
    
    // Remover después de 3 segundos
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// Mostrar éxito
function showSuccess(message) {
    console.log('Éxito:', message);
    const toast = document.createElement('div');
    toast.className = 'fixed top-4 right-4 bg-green-500 text-white px-6 py-3 rounded-lg shadow-lg z-50 animate-slide-in';
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// Manejar envío del formulario
async function handleSubmit(e) {
    e.preventDefault();
    console.log('Formulario enviado');
    
    if (!validateStep(totalSteps)) {
        return;
    }
    
    // Obtener datos del formulario
    const formData = new FormData(form);
    const data = {};
    formData.forEach((value, key) => {
        data[key] = value;
    });
    
    console.log('Datos del formulario:', data);
    
    // Mostrar loading
    if (btnSubmit) btnSubmit.classList.add('hidden');
    if (loading) loading.classList.remove('hidden');
    
    try {
        // Enviar a la API
        const response = await fetch('/calculadora/api/submit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        console.log('Respuesta API:', result);
        
        if (result.success) {
            // Éxito - redirigir a resultados
            showSuccess('¡Diagnóstico completado!');
            setTimeout(() => {
                window.location.href = result.redirect_url;
            }, 500);
        } else {
            // Error
            showError(result.error || 'Hubo un error. Por favor intenta de nuevo.');
            if (btnSubmit) btnSubmit.classList.remove('hidden');
            if (loading) loading.classList.add('hidden');
        }
    } catch (error) {
        console.error('Error:', error);
        showError('Error de conexión. Por favor intenta de nuevo.');
        if (btnSubmit) btnSubmit.classList.remove('hidden');
        if (loading) loading.classList.add('hidden');
    }
}

// Agregar estilos para toast
const style = document.createElement('style');
style.textContent = `
    @keyframes slide-in {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    .animate-slide-in {
        animation: slide-in 0.3s ease-out;
    }
`;
document.head.appendChild(style);

console.log('calculadora.js cargado completamente');