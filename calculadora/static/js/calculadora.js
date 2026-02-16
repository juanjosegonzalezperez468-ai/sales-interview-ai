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
    updateUI();
    setupEventListeners();
});

// Event listeners
function setupEventListeners() {
    // Navegación
    btnNext.addEventListener('click', nextStep);
    btnPrev.addEventListener('click', prevStep);
    
    // Submit
    form.addEventListener('submit', handleSubmit);
    
    // Auto-avanzar al seleccionar radio button
    const radioInputs = form.querySelectorAll('input[type="radio"]');
    radioInputs.forEach(input => {
        input.addEventListener('change', () => {
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
    if (!validateStep(currentStep)) {
        showError('Por favor selecciona una opción antes de continuar');
        return;
    }
    
    if (currentStep < totalSteps) {
        hideStep(currentStep);
        currentStep++;
        showStep(currentStep);
        updateUI();
    }
}

// Retroceder paso
function prevStep() {
    if (currentStep > 1) {
        hideStep(currentStep);
        currentStep--;
        showStep(currentStep);
        updateUI();
    }
}

// Mostrar paso
function showStep(step) {
    const stepCard = document.querySelector(`[data-step="${step}"]`);
    if (stepCard) {
        stepCard.classList.remove('hidden');
        // Scroll suave al top
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

// Ocultar paso
function hideStep(step) {
    const stepCard = document.querySelector(`[data-step="${step}"]`);
    if (stepCard) {
        stepCard.classList.add('hidden');
    }
}

// Actualizar UI (botones, progress bar)
function updateUI() {
    // Actualizar contador
    currentStepSpan.textContent = currentStep;
    
    // Actualizar progress dots
    for (let i = 1; i <= totalSteps; i++) {
        const dot = document.getElementById(`progress-dot-${i}`);
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
    
    // Mostrar/ocultar botones
    if (currentStep === 1) {
        btnPrev.classList.add('hidden');
    } else {
        btnPrev.classList.remove('hidden');
    }
    
    if (currentStep === totalSteps) {
        btnNext.classList.add('hidden');
        btnSubmit.classList.remove('hidden');
    } else {
        btnNext.classList.remove('hidden');
        btnSubmit.classList.add('hidden');
    }
}

// Validar paso actual
function validateStep(step) {
    const stepCard = document.querySelector(`[data-step="${step}"]`);
    
    // Para pasos con radio buttons
    const radioInputs = stepCard.querySelectorAll('input[type="radio"]');
    if (radioInputs.length > 0) {
        const radioName = radioInputs[0].name;
        const checked = stepCard.querySelector(`input[name="${radioName}"]:checked`);
        return checked !== null;
    }
    
    // Para paso de datos de contacto (step 7)
    if (step === 7) {
        const nombre = stepCard.querySelector('input[name="nombre"]');
        const email = stepCard.querySelector('input[name="email"]');
        const empresa = stepCard.querySelector('input[name="empresa"]');
        const cargo = stepCard.querySelector('input[name="cargo"]');
        
        if (!nombre.value.trim()) {
            showError('Por favor ingresa tu nombre');
            nombre.focus();
            return false;
        }
        
        if (!email.value.trim() || !isValidEmail(email.value)) {
            showError('Por favor ingresa un email válido');
            email.focus();
            return false;
        }
        
        if (!empresa.value.trim()) {
            showError('Por favor ingresa el nombre de tu empresa');
            empresa.focus();
            return false;
        }
        
        if (!cargo.value.trim()) {
            showError('Por favor ingresa tu cargo');
            cargo.focus();
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
    
    if (!validateStep(totalSteps)) {
        return;
    }
    
    // Obtener datos del formulario
    const formData = new FormData(form);
    const data = {};
    formData.forEach((value, key) => {
        data[key] = value;
    });
    
    // Mostrar loading
    btnSubmit.classList.add('hidden');
    loading.classList.remove('hidden');
    
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
        
        if (result.success) {
            // Éxito - redirigir a resultados
            showSuccess('¡Diagnóstico completado!');
            setTimeout(() => {
                window.location.href = result.redirect_url;
            }, 500);
        } else {
            // Error
            showError(result.error || 'Hubo un error. Por favor intenta de nuevo.');
            btnSubmit.classList.remove('hidden');
            loading.classList.add('hidden');
        }
    } catch (error) {
        console.error('Error:', error);
        showError('Error de conexión. Por favor intenta de nuevo.');
        btnSubmit.classList.remove('hidden');
        loading.classList.add('hidden');
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