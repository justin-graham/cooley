/** Entry point — initializes all modules and wires up global event handlers. */

import { appState, showView, setHomeLinkVisibility, showUiNotice, resetProgressSection } from './state.js';
import { getCsrfHeaders } from './utils.js';
import { api } from './api.js';
import { initUpload } from './upload.js';
import { initDemoModeIfNeeded } from './demo.js';
import { hideDocumentModal } from './modal.js';
import { loadPastAudits, loadAuditById } from './past-audits.js';
import { toggleAccordion, handleAccordionKeydown, toggleDataRoomFolder, handleDataRoomFolderKeydown } from './results.js';
import { AuditViewState, navigateTimeline } from './time-travel.js';
import { initScrollReveal } from './scroll.js';

// Expose functions needed by dynamically generated onclick handlers
window._toggleAccordion = toggleAccordion;
window._handleAccordionKeydown = handleAccordionKeydown;
window._toggleDataRoomFolder = toggleDataRoomFolder;
window._handleDataRoomFolderKeydown = handleDataRoomFolderKeydown;
window._showUploadPage = showUploadPage;
window._loadPastAudits = loadPastAudits;
window._loadAuditById = loadAuditById;

function showUploadPage() {
    if (appState.pollInterval) { clearInterval(appState.pollInterval); appState.pollInterval = null; }
    showView('upload');
    resetProgressSection();

    // Reset cap table upload state
    appState.selectedCaptableFile = null;
    const zone = document.getElementById('captable-upload-zone');
    if (zone) {
        zone.classList.remove('file-selected');
        zone.querySelector('.primary-text').textContent = 'Drop your .xlsx file here or click to browse.';
        zone.querySelector('.secondary-text').textContent = 'Optional. Carta export (.xlsx)';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Initialize upload zones
    initUpload();

    // Scroll reveal
    initScrollReveal();

    // Check for demo mode
    initDemoModeIfNeeded();

    // Modal close handlers
    const modal = document.getElementById('document-modal');
    const backdrop = modal?.querySelector('.modal-backdrop');
    const closeBtn = modal?.querySelector('.modal-close');
    if (backdrop) backdrop.addEventListener('click', hideDocumentModal);
    if (closeBtn) closeBtn.addEventListener('click', hideDocumentModal);

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal?.style.display === 'flex') { hideDocumentModal(); return; }
        if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && AuditViewState.allEvents.length > 0) {
            const timeline = document.getElementById('horizontal-timeline');
            if (timeline && timeline.offsetParent !== null) {
                e.preventDefault();
                navigateTimeline(e.key === 'ArrowLeft' ? -1 : 1);
            }
        }
    });

    // Navigation
    const homeLink = document.getElementById('home-link');
    if (homeLink) homeLink.addEventListener('click', (e) => { e.preventDefault(); showUploadPage(); });

    const pastLink = document.getElementById('past-audits-link');
    if (pastLink) pastLink.addEventListener('click', (e) => { e.preventDefault(); loadPastAudits(); });

    const logoutLink = document.getElementById('logout-link');
    if (logoutLink) {
        logoutLink.addEventListener('click', async (e) => {
            e.preventDefault();
            try {
                await api.logout();
                appState.currentAuditId = null;
                if (appState.pollInterval) clearInterval(appState.pollInterval);
                window.location.href = '/';
            } catch (error) {
                showUiNotice('Logout failed. Please try again.');
            }
        });
    }

    // Logo click → home
    const logo = document.querySelector('.nav-logo');
    if (logo) { logo.style.cursor = 'pointer'; logo.addEventListener('click', (e) => { e.preventDefault(); showUploadPage(); }); }

    // Start with Home link hidden
    setHomeLinkVisibility(false);
});
