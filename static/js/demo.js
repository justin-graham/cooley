/** Demo mode — loads static JSON data for preview without upload. */

import { api } from './api.js';
import { appState, showView, setProgressState } from './state.js';
import { renderResults } from './results.js';

export function isDemoMode() {
    return new URLSearchParams(window.location.search).get('demo') === 'true';
}

export async function initDemoModeIfNeeded() {
    if (!isDemoMode()) return;

    showView('processing');
    setProgressState('Loading Demo', 'Loading demo audit data...');

    try {
        const demoData = await api.getDemoData();
        appState.isDemoModeActive = true;
        appState.demoDataCache = demoData;
        appState.currentAuditId = demoData.id;

        await new Promise(r => setTimeout(r, 1000));

        showView('results');
        await renderResults(demoData);
    } catch (error) {
        setProgressState(null, `Error loading demo: ${error.message}`);
        setTimeout(() => showView('upload'), 3000);
    }
}
