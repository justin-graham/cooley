/** Past audits listing and loading. */

import { escapeHtml, escapeAttr } from './utils.js';
import { api } from './api.js';
import { appState, showView, setProgressState, showUiNotice, renderProgressError } from './state.js';
import { renderResults } from './results.js';

const PROCESSING_STATUSES = ['queued', 'parsing', 'classifying', 'extracting', 'reconciling', 'processing'];
const PAST_AUDITS_POLL_MS = 3000;

function renderAuditList(audits, container) {
    container.innerHTML = audits.map(audit => {
        const date = new Date(audit.created_at).toLocaleDateString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
        });
        const name = audit.company_name || audit.upload_filename || 'Unknown Company';
        let badge = '';
        if (audit.status === 'complete') badge = '<span class="status-badge status-complete">✓ Complete</span>';
        else if (audit.status === 'needs_review') badge = '<span class="status-badge status-error">Review Required</span>';
        else if (PROCESSING_STATUSES.includes(audit.status)) badge = '<span class="status-badge status-processing">Processing...</span>';
        else if (audit.status === 'error') badge = '<span class="status-badge status-error">⚠ Failed</span>';

        const loadable = audit.status === 'complete' || audit.status === 'needs_review';
        return `<div class="accordion-item audit-item ${!loadable ? 'disabled' : ''}" data-audit-id="${escapeAttr(audit.id)}" data-loadable="${loadable}">
                <div class="accordion-header"${loadable ? ' role="button" tabindex="0"' : ''}>
                    <div class="audit-header-content">
                        <h3 class="accordion-title">${escapeHtml(name)}</h3>
                        <p class="audit-metadata">${date} • ${audit.document_count} documents ${badge}</p>
                        ${audit.upload_filename && audit.company_name ? `<p class="audit-filename">${escapeHtml(audit.upload_filename)}</p>` : ''}
                    </div>
                    <span class="audit-delete-btn" role="button" title="Delete audit">&times;</span>
                    ${loadable ? '<span class="accordion-toggle">→</span>' : ''}
                </div>
            </div>`;
    }).join('');

    container.querySelectorAll('.audit-delete-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const item = btn.closest('.audit-item');
            const auditId = item.getAttribute('data-audit-id');
            if (!confirm('Delete this audit? This cannot be undone.')) return;
            try {
                await api.deleteAudit(auditId);
                item.remove();
                if (!container.querySelector('.audit-item')) {
                    container.innerHTML = '<p style="color: var(--text-secondary);">No past audits yet. Upload your first document set to get started.</p>';
                }
            } catch (err) {
                alert('Failed to delete audit: ' + err.message);
            }
        });
    });

    container.querySelectorAll('.audit-item[data-loadable="true"]').forEach(item => {
        const handler = () => { const id = item.getAttribute('data-audit-id'); if (id) loadAuditById(id); };
        item.addEventListener('click', handler);
        item.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handler(); }
        });
    });
}

export async function loadPastAudits() {
    if (appState.pollInterval) { clearInterval(appState.pollInterval); appState.pollInterval = null; }
    const container = document.getElementById('past-audits-accordion');

    showView('pastAudits');
    container.innerHTML = '<p style="color: var(--text-secondary);">Loading past audits...</p>';

    try {
        const audits = await api.getAudits();
        if (!audits.length) {
            container.innerHTML = '<p style="color: var(--text-secondary);">No past audits yet. Upload your first document set to get started.</p>';
            return;
        }

        renderAuditList(audits, container);

        // Poll for updates if any audits are still processing
        const hasProcessing = audits.some(a => PROCESSING_STATUSES.includes(a.status));
        if (hasProcessing) {
            appState.pollInterval = setInterval(async () => {
                try {
                    const updated = await api.getAudits();
                    renderAuditList(updated, container);
                    const stillProcessing = updated.some(a => PROCESSING_STATUSES.includes(a.status));
                    if (!stillProcessing && appState.pollInterval) {
                        clearInterval(appState.pollInterval);
                        appState.pollInterval = null;
                    }
                } catch (_) { /* silently retry on next interval */ }
            }, PAST_AUDITS_POLL_MS);
        }
    } catch (error) {
        container.innerHTML = '<p style="color: var(--accent);">Error loading past audits. Please refresh the page.</p>';
    }
}

export async function loadAuditById(auditId) {
    if (appState.pollInterval) { clearInterval(appState.pollInterval); appState.pollInterval = null; }
    showView('processing');
    setProgressState('Loading', 'Loading past audit...');

    try {
        const data = await api.getStatus(auditId);
        if (data.status === 'complete' || data.status === 'needs_review') {
            appState.currentAuditId = auditId;
            showView('results');
            await renderResults(data.results);
            if (data.review_required) {
                showUiNotice('This audit is marked review-required. Validate confidence warnings and evidence links before use.');
            }
        } else if (data.status === 'error') {
            throw new Error(data.error || 'Audit failed');
        } else {
            throw new Error('Audit is still processing');
        }
    } catch (error) {
        renderProgressError(
            'Failed to load audit',
            error.message,
            `<button class="btn btn-secondary" onclick="window._loadPastAudits()" style="margin-right: 0.5rem;">Back to Audits</button>
             <button class="btn btn-primary" onclick="window._loadAuditById('${escapeAttr(auditId)}')">Retry</button>`
        );
    }
}
