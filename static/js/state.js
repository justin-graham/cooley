/** Application state management and view transitions. */

import { escapeHtml } from './utils.js';

// Mutable application state
export const appState = {
    currentAuditId: null,
    pollInterval: null,
    isDemoModeActive: false,
    demoDataCache: null,
    isUploading: false,
    selectedCaptableFile: null,
    selectedZipFile: null,
    pollRetryCount: 0,
};

export const MAX_POLL_RETRIES = 5;

// Section display modes
const SECTION_DISPLAY = {
    'upload-header': 'block',
    'upload-section': 'grid',
    'begin-tieout-section': 'flex',
    'progress': 'flex',
    'results': 'block',
    'past-audits-section': 'grid',
};

const VIEW_SECTIONS = {
    upload: ['upload-header', 'upload-section', 'begin-tieout-section'],
    processing: ['progress'],
    results: ['results'],
    pastAudits: ['past-audits-section'],
};

const ALL_SECTION_IDS = Object.keys(SECTION_DISPLAY);

/** Hide all main sections, then show only those belonging to the target view. */
export function showView(viewName) {
    ALL_SECTION_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    (VIEW_SECTIONS[viewName] || []).forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = SECTION_DISPLAY[id] || 'block';
    });
    setHomeLinkVisibility(viewName !== 'upload');
}

export function setHomeLinkVisibility(visible) {
    const homeLink = document.getElementById('home-link');
    if (homeLink) homeLink.style.display = visible ? '' : 'none';
}

export function setProgressState(step, text) {
    const stepEl = document.getElementById('progress-step');
    const textEl = document.getElementById('progress-text');
    if (stepEl && step != null) stepEl.textContent = step;
    if (textEl && text != null) textEl.textContent = text;
}

export function showUiNotice(message) {
    const id = 'ui-notice-banner';
    let banner = document.getElementById(id);
    if (!banner) {
        banner = document.createElement('div');
        banner.id = id;
        Object.assign(banner.style, {
            position: 'fixed', top: '68px', left: '50%', transform: 'translateX(-50%)',
            padding: '0.75rem 1rem', background: '#fef2f2', border: '1px solid #fecaca',
            color: '#991b1b', fontSize: '0.875rem', zIndex: '9999',
            maxWidth: '90vw', textAlign: 'center',
        });
        document.body.appendChild(banner);
    }
    banner.textContent = message;
    banner.style.display = 'block';
    setTimeout(() => { if (banner) banner.style.display = 'none'; }, 5000);
}

export function renderProgressError(title, message, actionsHtml) {
    const el = document.getElementById('progress');
    if (!el) return;
    el.innerHTML = `
        <div role="alert" style="text-align: center; padding: 2rem;">
            <p style="font-family: var(--font-grotesk); font-size: var(--text-lg); margin-bottom: 0.5rem;">${escapeHtml(title)}</p>
            <p style="color: var(--gray-600); margin-bottom: 1.5rem;">${escapeHtml(message)}</p>
            ${actionsHtml || ''}
        </div>
    `;
}

/** Restore progress section to its default loader HTML. */
export function resetProgressSection() {
    const el = document.getElementById('progress');
    if (!el) return;
    el.innerHTML = `
        <div class="loader-row" aria-hidden="true">
            <div class="loader"></div><div class="loader"></div><div class="loader"></div>
        </div>
        <div id="progress-wrapper">
            <span id="progress-step" role="status">Processing</span>
            <span id="progress-text">Starting...</span>
        </div>
    `;
}
