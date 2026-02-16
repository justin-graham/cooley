/** Document viewer modal with focus trapping. */

import { escapeHtml, escapeAttr, sanitizeImageSrc } from './utils.js';
import { appState } from './state.js';
import { api } from './api.js';

let focusTrapHandler = null;

export async function showDocumentModal(auditId, docId, snippet = null, previewImage = null) {
    const modal = document.getElementById('document-modal');
    const modalFilename = document.getElementById('modal-filename');
    const modalClassification = document.getElementById('modal-classification');
    const modalContent = document.getElementById('modal-content');

    modal.style.display = 'flex';
    modalFilename.textContent = 'Loading...';
    modalClassification.textContent = '';
    modalContent.innerHTML = '<div style="text-align: center; padding: 2rem;">Loading document...</div>';

    try {
        let doc;
        if (appState.isDemoModeActive && appState.demoDataCache) {
            doc = appState.demoDataCache.documents.find(d =>
                d.filename === docId || d.filename.includes(docId) || docId.includes(d.filename)
            );
            if (!doc) throw new Error('Document not found in demo data');
            if (!doc.full_text) {
                doc.full_text = `[Demo Document: ${doc.filename}]\n\nClassification: ${doc.classification}\n\nExtracted Data:\n${JSON.stringify(doc.extracted_data, null, 2)}`;
            }
        } else {
            doc = await api.getDocument(auditId, docId);
        }

        modalFilename.textContent = doc.filename || 'Document';
        modalClassification.textContent = doc.classification || 'Unknown Document Type';

        if (previewImage) {
            const src = sanitizeImageSrc(previewImage);
            if (!src) throw new Error('Invalid preview image source');
            modalContent.innerHTML = `<img src="${escapeAttr(src)}" alt="Document preview" style="width: 100%; max-height: 70vh; object-fit: contain; background: var(--gray-50);" />`;
        } else {
            const fullText = doc.full_text || 'No text content available';
            if (snippet && fullText.includes(snippet)) {
                const escaped = escapeHtml(fullText);
                const escapedSnippet = escapeHtml(snippet);
                modalContent.innerHTML = escaped.replace(escapedSnippet, `<mark>${escapedSnippet}</mark>`);
                setTimeout(() => {
                    const mark = modalContent.querySelector('mark');
                    if (mark) mark.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }, 100);
            } else {
                modalContent.textContent = fullText;
            }
        }

        document.body.style.overflow = 'hidden';
        trapFocus(modal);
    } catch (error) {
        modalFilename.textContent = 'Error';
        modalClassification.textContent = '';
        modalContent.innerHTML = `<div style="color: var(--accent); padding: 2rem; text-align: center;">Failed to load document: ${escapeHtml(error.message)}</div>`;
    }
}

export function hideDocumentModal() {
    document.getElementById('document-modal').style.display = 'none';
    document.body.style.overflow = '';
    removeFocusTrap();
}

function trapFocus(modal) {
    removeFocusTrap();
    const sel = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    focusTrapHandler = function(e) {
        if (e.key !== 'Tab') return;
        const focusable = modal.querySelectorAll(sel);
        if (!focusable.length) return;
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', focusTrapHandler);
    const closeBtn = modal.querySelector('.modal-close');
    if (closeBtn) closeBtn.focus();
}

function removeFocusTrap() {
    if (focusTrapHandler) { document.removeEventListener('keydown', focusTrapHandler); focusTrapHandler = null; }
}
