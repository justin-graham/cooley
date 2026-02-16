/** File upload handling — zip and optional Carta cap table. */

import { api } from './api.js';
import { appState, showView, setProgressState, showUiNotice } from './state.js';
import { startPolling } from './polling.js';

export function initUpload() {
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const captableZone = document.getElementById('captable-upload-zone');
    const captableInput = document.getElementById('captable-file-input');

    // Zip upload zone
    uploadZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
        if (e.target.files[0]) handleFileUpload(e.target.files[0]);
    });
    uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('dragging'); });
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragging'));
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragging');
        if (e.dataTransfer.files[0]) handleFileUpload(e.dataTransfer.files[0]);
    });

    // Keyboard: Enter/Space triggers file picker
    uploadZone.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
    });

    // Cap table upload zone
    captableZone.addEventListener('click', () => captableInput.click());
    captableInput.addEventListener('change', (e) => {
        if (e.target.files[0]) handleCaptableFile(e.target.files[0]);
    });
    captableZone.addEventListener('dragover', (e) => { e.preventDefault(); captableZone.classList.add('dragging'); });
    captableZone.addEventListener('dragleave', () => captableZone.classList.remove('dragging'));
    captableZone.addEventListener('drop', (e) => {
        e.preventDefault();
        captableZone.classList.remove('dragging');
        if (e.dataTransfer.files[0]) handleCaptableFile(e.dataTransfer.files[0]);
    });

    // Keyboard: Enter/Space triggers file picker
    captableZone.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); captableInput.click(); }
    });
}

function handleCaptableFile(file) {
    if (!file.name.endsWith('.xlsx')) {
        showUiNotice('Please upload a .xlsx file (Carta export).');
        return;
    }
    appState.selectedCaptableFile = file;
    const zone = document.getElementById('captable-upload-zone');
    zone.classList.add('file-selected');
    zone.querySelector('.primary-text').textContent = file.name;
    zone.querySelector('.secondary-text').textContent = 'Cap table selected. Now upload your .zip file.';
}

function handleFileUpload(file) {
    if (!file.name.endsWith('.zip')) { showUiNotice('Please upload a .zip file.'); return; }
    if (file.size > 50 * 1024 * 1024) {
        showUiNotice(`File too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Maximum is 50MB.`);
        return;
    }

    appState.selectedZipFile = file;
    const zone = document.getElementById('upload-zone');
    zone.classList.add('file-selected');
    zone.querySelector('.primary-text').textContent = file.name;
    zone.querySelector('.secondary-text').textContent = 'Zip file selected.';
    updateBeginButton();
}

function updateBeginButton() {
    const btn = document.getElementById('begin-tieout-btn');
    if (btn) btn.disabled = !appState.selectedZipFile;
}

export async function beginTieout() {
    if (appState.isUploading || !appState.selectedZipFile) return;

    appState.isUploading = true;
    const uploadZone = document.getElementById('upload-zone');
    if (uploadZone) uploadZone.classList.add('uploading');

    showView('processing');
    setProgressState('Uploading', 'Uploading files...');

    try {
        const data = await api.upload(appState.selectedZipFile, appState.selectedCaptableFile);
        appState.currentAuditId = data.audit_id;
        startPolling();
    } catch (error) {
        setProgressState(null, `Error: ${error.message}`);
        setTimeout(() => showView('upload'), 3000);
    } finally {
        appState.isUploading = false;
        if (uploadZone) uploadZone.classList.remove('uploading');
    }
}
