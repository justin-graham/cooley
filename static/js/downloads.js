/** Download previews and button wiring. */

import { api } from './api.js';

export async function loadDownloadPreviews(auditId) {
    try {
        const [minuteBook, issues] = await Promise.all([
            api.getPreview(auditId, 'minute-book').catch(() => ({ preview: 'Preview unavailable' })),
            api.getPreview(auditId, 'issues').catch(() => ({ preview: 'Preview unavailable' })),
        ]);

        const mbEl = document.getElementById('minute-book-preview');
        const isEl = document.getElementById('issues-preview');
        if (mbEl) mbEl.textContent = minuteBook.preview || 'Preview unavailable';
        if (isEl) isEl.textContent = issues.preview || 'Preview unavailable';

        const mbBtn = document.getElementById('download-minute-book');
        if (mbBtn) { mbBtn.onclick = () => { window.location.href = `/api/audits/${auditId}/download/minute-book`; }; mbBtn.disabled = false; }

        const isBtn = document.getElementById('download-issues');
        if (isBtn) { isBtn.onclick = () => { window.location.href = `/api/audits/${auditId}/download/issues`; }; isBtn.disabled = false; }
    } catch (error) {
        const mbEl = document.getElementById('minute-book-preview');
        const isEl = document.getElementById('issues-preview');
        if (mbEl) mbEl.textContent = 'Preview unavailable';
        if (isEl) isEl.textContent = 'Preview unavailable';
    }
}
