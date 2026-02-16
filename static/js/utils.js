/** Shared utility functions. */

export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

export const escapeAttr = escapeHtml;

export function sanitizeImageSrc(src) {
    if (typeof src !== 'string') return '';
    const trimmed = src.trim();
    if (trimmed.startsWith('data:image/')) return trimmed;
    if (trimmed.startsWith('/')) return trimmed;
    if (/^https?:\/\//i.test(trimmed)) return trimmed;
    return '';
}

export function formatNumber(num) {
    if (num == null || isNaN(num)) return 'N/A';
    return num.toLocaleString();
}

export function formatPercent(num) {
    if (num == null || isNaN(num)) return 'N/A';
    return `${num.toFixed(2)}%`;
}

export function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

export function getCookie(name) {
    const encoded = `${name}=`;
    for (const part of document.cookie.split(';')) {
        const trimmed = part.trim();
        if (trimmed.startsWith(encoded)) {
            return decodeURIComponent(trimmed.substring(encoded.length));
        }
    }
    return null;
}

export function getCsrfHeaders() {
    const csrf = getCookie('csrf_token');
    return csrf ? { 'X-CSRF-Token': csrf } : {};
}
