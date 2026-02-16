/** Scroll reveal animations and hero image parallax motion. */

export function initScrollReveal() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('visible'); });
    }, { threshold: 0.1 });
    document.querySelectorAll('.scroll-reveal').forEach(el => observer.observe(el));
}

let heroMotionHandler = null;
let heroMotionRaf = null;
let heroMotionTarget = 0;
let heroMotionCurrent = 0;

export function initHeroScrollMotion() {
    const heroSection = document.querySelector('.hero-section');
    const heroVisual = document.querySelector('.hero-visual');
    if (!heroSection || !heroVisual) return;

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        heroVisual.style.setProperty('--hero-x', '0px');
        heroVisual.style.setProperty('--hero-y', '0px');
        heroVisual.style.setProperty('--hero-z', '0px');
        heroVisual.style.setProperty('--hero-scale', '1');
        return;
    }

    const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

    const apply = (progress) => {
        const wave = Math.sin(progress * Math.PI);
        heroVisual.style.setProperty('--hero-x', `${(-8 * wave).toFixed(2)}px`);
        heroVisual.style.setProperty('--hero-y', `${(12 * wave).toFixed(2)}px`);
        heroVisual.style.setProperty('--hero-z', `${(120 * wave).toFixed(2)}px`);
        heroVisual.style.setProperty('--hero-scale', (1 + 0.25 * wave).toFixed(3));
    };

    const tick = () => {
        heroMotionCurrent += (heroMotionTarget - heroMotionCurrent) * 0.12;
        apply(heroMotionCurrent);
        if (Math.abs(heroMotionTarget - heroMotionCurrent) > 0.001) {
            heroMotionRaf = requestAnimationFrame(tick);
        } else {
            heroMotionCurrent = heroMotionTarget;
            apply(heroMotionCurrent);
            heroMotionRaf = null;
        }
    };

    const update = () => {
        const scrollY = window.scrollY || window.pageYOffset;
        const range = Math.max(360, Math.min(600, heroSection.offsetHeight));
        heroMotionTarget = clamp((scrollY - heroSection.offsetTop) / range, 0, 1);
        if (!heroMotionRaf) heroMotionRaf = requestAnimationFrame(tick);
    };

    if (!heroMotionHandler) {
        let inView = false;
        new IntersectionObserver((entries) => { inView = entries[0].isIntersecting; }, { threshold: 0 }).observe(heroSection);
        heroMotionHandler = () => { if (inView) update(); };
        window.addEventListener('scroll', heroMotionHandler, { passive: true });
        window.addEventListener('resize', heroMotionHandler);
    }

    heroMotionHandler();
}
