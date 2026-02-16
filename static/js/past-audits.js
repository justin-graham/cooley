/** Past audits listing and loading. */

import { escapeHtml, escapeAttr } from './utils.js';
import { api } from './api.js';
import { appState, showView, setProgressState, showUiNotice, renderProgressError } from './state.js';
import { renderResults } from './results.js';

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

        container.innerHTML = audits.map(audit => {
            const date = new Date(audit.created_at).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
            });
            const name = audit.company_name || audit.upload_filename || 'Unknown Company';
            let badge = '';
            if (audit.status === 'complete') badge = '<span class="status-badge status-complete">✓ Complete</span>';
            else if (audit.status === 'needs_review') badge = '<span class="status-badge status-error">Review Required</span>';
            else if (['queued', 'parsing', 'classifying', 'extracting', 'reconciling', 'processing'].includes(audit.status)) badge = '<span class="status-badge status-processing">Processing...</span>';
            else if (audit.status === 'error') badge = '<span class="status-badge status-error">⚠ Failed</span>';

            const loadable = audit.status === 'complete' || audit.status === 'needs_review';
            return `<div class="accordion-item audit-item ${!loadable ? 'disabled' : ''}" data-audit-id="${escapeAttr(audit.id)}" data-loadable="${loadable}">
                <div class="accordion-header"${loadable ? ' role="button" tabindex="0"' : ''}>
                    <div class="audit-header-content">
                        <h3 class="accordion-title">${escapeHtml(name)}</h3>
                        <p class="audit-metadata">${date} • ${audit.document_count} documents ${badge}</p>
                        ${audit.upload_filename && audit.company_name ? `<p class="audit-filename">${escapeHtml(audit.upload_filename)}</p>` : ''}
                    </div>
                    ${loadable ? '<span class="accordion-toggle">→</span>' : ''}
                </div>
            </div>`;
        }).join('');

        container.querySelectorAll('.audit-item[data-loadable="true"]').forEach(item => {
            const handler = () => { const id = item.getAttribute('data-audit-id'); if (id) loadAuditById(id); };
            item.addEventListener('click', handler);
            item.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handler(); }
            });
        });
    } catch (error) {
        container.innerHTML = '<p style="color: var(--accent);">Error loading past audits. Please refresh the page.</p>';
    }
}

export async function loadAuditById(auditId) {
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
