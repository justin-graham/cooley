// ============================================================================
// FIBONACCI SPIRAL ANIMATION
// ============================================================================

const canvas = document.getElementById("fig18Canvas");
const wrap = document.getElementById("fig18Wrap");
const ctx = canvas.getContext("2d");

let time = 0;
const phi = (1 + Math.sqrt(5)) / 2;

function resizeCanvas() {
    const rect = wrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const size = Math.min(rect.width, rect.height);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function animate() {
    const width = canvas.width / (window.devicePixelRatio || 1);
    const height = canvas.height / (window.devicePixelRatio || 1);

    ctx.clearRect(0, 0, width, height);
    ctx.save();
    ctx.translate(width / 2, height / 2);

    const maxRectangles = Math.min(60, Math.floor((time * 0.02) % 80));
    let rectW = width * 0.55;
    let rectH = rectW / phi;
    let scale = 1;
    const angleOffset = time * 0.00025;

    for (let i = 0; i < maxRectangles; i++) {
        ctx.save();
        const spiralAngle = i * 0.174533;
        const radius = scale * (width * 0.18);
        const x = Math.cos(spiralAngle) * radius;
        const y = Math.sin(spiralAngle) * radius;
        ctx.translate(x, y);
        ctx.rotate(spiralAngle + angleOffset);

        const alpha = 0.5 - i * 0.01;
        if (alpha <= 0) {
            ctx.restore();
            continue;
        }

        ctx.strokeStyle = `rgba(0, 0, 0, ${alpha})`;
        ctx.lineWidth = 0.8;
        ctx.strokeRect(-rectW / 2, -rectH / 2, rectW, rectH);

        if (i % 3 === 0) {
            ctx.beginPath();
            ctx.moveTo(-rectW / 2, -rectH / 2);
            ctx.lineTo(rectW / 2, rectH / 2);
            ctx.moveTo(rectW / 2, -rectH / 2);
            ctx.lineTo(-rectW / 2, rectH / 2);
            ctx.strokeStyle = `rgba(50, 50, 50, ${alpha * 0.2})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
        }

        ctx.restore();
        rectW *= 0.95;
        rectH *= 0.95;
        scale *= 0.98;
    }

    ctx.beginPath();
    for (let i = 0; i <= maxRectangles; i++) {
        const spiralAngle = i * 0.174533;
        const radius = Math.pow(0.98, i) * (width * 0.18);
        const x = Math.cos(spiralAngle) * radius;
        const y = Math.sin(spiralAngle) * radius;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = "rgba(150, 150, 150, 0.3)";
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.restore();
    time += 3;
    requestAnimationFrame(animate);
}

window.addEventListener("resize", resizeCanvas);
resizeCanvas();
animate();

// ============================================================================
// AUTH FORM SUBMISSION
// ============================================================================

document.getElementById('auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(e.target);
    const errorDiv = document.getElementById('auth-error');
    const submitBtn = e.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.textContent;

    // Show loading state
    submitBtn.textContent = 'Signing in...';
    submitBtn.disabled = true;
    errorDiv.style.display = 'none';

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            // Redirect to app
            window.location.href = '/app';
        } else {
            const data = await response.json();
            errorDiv.textContent = data.detail || 'Invalid credentials';
            errorDiv.style.display = 'block';
            submitBtn.textContent = originalText;
            submitBtn.disabled = false;
        }
    } catch (error) {
        console.error('Login error:', error);
        errorDiv.textContent = 'Login failed. Please try again.';
        errorDiv.style.display = 'block';
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
    }
});

// ============================================================================
// ACCESS REQUEST FORM SUBMISSION
// ============================================================================

document.getElementById('access-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(e.target);
    const submitBtn = e.target.querySelector('button');
    const originalText = submitBtn.textContent;

    // Show loading state
    submitBtn.textContent = 'Submitting...';
    submitBtn.disabled = true;

    try {
        const response = await fetch('/api/access-request', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            submitBtn.textContent = 'Request submitted!';
            e.target.reset();
            setTimeout(() => {
                submitBtn.textContent = originalText;
                submitBtn.disabled = false;
            }, 3000);
        } else {
            submitBtn.textContent = 'Error. Try again.';
            setTimeout(() => {
                submitBtn.textContent = originalText;
                submitBtn.disabled = false;
            }, 3000);
        }
    } catch (error) {
        console.error('Access request error:', error);
        submitBtn.textContent = 'Error. Try again.';
        setTimeout(() => {
            submitBtn.textContent = originalText;
            submitBtn.disabled = false;
        }, 3000);
    }
});
