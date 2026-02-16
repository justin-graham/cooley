/** Status polling with progress step mapping. */

import { api } from './api.js';
import { appState, MAX_POLL_RETRIES, showView, setProgressState, showUiNotice, renderProgressError } from './state.js';
import { renderResults } from './results.js';

export function startPolling() {
    appState.pollRetryCount = 0;
    appState.pollInterval = setInterval(checkStatus, 2000);
    checkStatus();
}

async function checkStatus() {
    if (!appState.currentAuditId) return;

    try {
        const data = await api.getStatus(appState.currentAuditId);
        appState.pollRetryCount = 0;

        if (data.progress) {
            const stepLabel = data.pipeline_state
                ? getProgressStepFromState(data.pipeline_state)
                : getProgressStep(data.progress);
            setProgressState(stepLabel, data.progress);
        }

        if (data.status === 'complete' || data.status === 'needs_review') {
            clearInterval(appState.pollInterval);
            appState.pollInterval = null;
            showView('results');
            await renderResults(data.results);
            if (data.review_required) {
                showUiNotice('Audit completed with review-required flags. Validate highlighted issues before relying on outputs.');
            }
        }

        if (data.status === 'error') {
            clearInterval(appState.pollInterval);
            appState.pollInterval = null;
            renderProgressError(
                'Processing failed',
                data.error || 'An unexpected error occurred',
                '<button class="btn btn-primary" onclick="window._showUploadPage()">Try Again</button>'
            );
        }
    } catch (error) {
        appState.pollRetryCount++;
        if (appState.pollRetryCount >= MAX_POLL_RETRIES) {
            clearInterval(appState.pollInterval);
            appState.pollInterval = null;
            renderProgressError(
                'Connection lost',
                `Unable to reach the server after ${MAX_POLL_RETRIES} attempts. Your audit may still be processing.`,
                '<button class="btn btn-primary" onclick="window._showUploadPage()">Try Again</button>'
            );
        }
    }
}

function getProgressStep(message) {
    if (!message) return 'Processing';
    const msg = message.toLowerCase();
    if (msg.includes('pass 1') || msg.includes('classifying')) return 'Classifying';
    if (msg.includes('pass 2') || msg.includes('extracting data')) return 'Analyzing';
    if (msg.includes('pass 3') || msg.includes('synthesizing') || msg.includes('building') || msg.includes('generating') || msg.includes('finalizing')) return 'Synthesizing';
    if (msg.includes('complete')) return 'Complete';
    if (msg.includes('parsing') || (msg.includes('found') && msg.includes('files'))) return 'Extracting';
    if (msg.includes('extracting files') || msg.includes('starting')) return 'Uploading';
    return 'Processing';
}

function getProgressStepFromState(state) {
    const labels = {
        queued: 'Queued', parsing: 'Extracting', classifying: 'Classifying',
        extracting: 'Analyzing', reconciling: 'Reconciling',
        needs_review: 'Review Required', complete: 'Complete', error: 'Error',
    };
    return labels[(state || '').toLowerCase()] || 'Processing';
}
