/** Centralized API client — single place for fetch, CSRF, and error handling. */

import { getCsrfHeaders } from './utils.js';

async function apiFetch(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: { ...getCsrfHeaders(), ...options.headers },
    });
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || body.error || response.statusText);
    }
    return response;
}

async function apiJson(url, options) {
    const response = await apiFetch(url, options);
    return response.json();
}

export const api = {
    upload(file, captableFile) {
        const formData = new FormData();
        formData.append('file', file);
        if (captableFile) formData.append('captable', captableFile);
        return apiJson('/upload', { method: 'POST', body: formData });
    },

    getStatus: (auditId) => apiJson(`/status/${auditId}`),
    getEvents: (auditId) => apiJson(`/api/audits/${auditId}/events`),
    getCapTable: (auditId, asOfDate) => apiJson(`/api/audits/${auditId}/captable?as_of_date=${asOfDate}`),
    getOptions: (auditId, asOfDate) => apiJson(`/api/audits/${auditId}/options?as_of_date=${asOfDate}`),
    getAudits: () => apiJson('/api/audits'),
    deleteAudit: (auditId) => apiFetch(`/api/audits/${auditId}`, { method: 'DELETE' }),
    getDocument: (auditId, docId) => apiJson(`/api/audits/${auditId}/documents/${docId}`),
    getPreview: (auditId, type) => apiJson(`/api/audits/${auditId}/preview/${type}`),
    getDemoData: () => apiJson('/static/demo-data.json'),

    async logout() {
        await apiFetch('/api/auth/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
    },
};
