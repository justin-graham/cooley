/**
 * Corporate Governance Audit Platform - Frontend Logic
 * Handles file upload, status polling, and results rendering
 */

// State
let currentAuditId = null;
let pollInterval = null;

// DOM Elements
const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');
const progressSection = document.getElementById('progress');
const progressStep = document.getElementById('progress-step');
const progressText = document.getElementById('progress-text');
const resultsSection = document.getElementById('results');
const uploadSection = document.getElementById('upload-section');

// ============================================================================
// PROGRESS STEP MAPPING
// ============================================================================

/**
 * Map backend progress messages to user-friendly step labels
 */
function getProgressStep(message) {
    if (!message) return 'Processing';

    const msg = message.toLowerCase();

    // Check specific phase markers FIRST (before generic keywords)
    if (msg.includes('pass 1') || msg.includes('classifying')) {
        return 'Classifying';
    } else if (msg.includes('pass 2') || msg.includes('extracting data')) {
        return 'Analyzing';
    } else if (msg.includes('pass 3') || msg.includes('synthesizing') || msg.includes('building') || msg.includes('generating') || msg.includes('finalizing')) {
        return 'Synthesizing';
    } else if (msg.includes('complete')) {
        return 'Complete';
    } else if (msg.includes('parsing') || (msg.includes('found') && msg.includes('files'))) {
        return 'Extracting';
    } else if (msg.includes('extracting files') || msg.includes('starting')) {
        return 'Uploading';
    }

    return 'Processing';
}

// ============================================================================
// UPLOAD HANDLING
// ============================================================================

// Click to browse
uploadZone.addEventListener('click', () => {
    fileInput.click();
});

// File selection
fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        handleFileUpload(file);
    }
});

// Drag and drop
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragging');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragging');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragging');

    const file = e.dataTransfer.files[0];
    if (file) {
        handleFileUpload(file);
    }
});

/**
 * Upload file to server and start processing
 */
async function handleFileUpload(file) {
    // Validate file type
    if (!file.name.endsWith('.zip')) {
        alert('Please upload a .zip file');
        return;
    }

    // Validate file size (50MB)
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
        alert(`File too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Maximum is 50MB.`);
        return;
    }

    // Show progress section
    uploadSection.style.display = 'none';
    progressSection.style.display = 'flex';
    progressStep.textContent = 'Uploading';
    progressText.textContent = 'Uploading zip file...';

    try {
        // Upload file
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }

        const data = await response.json();
        currentAuditId = data.audit_id;

        // Start polling for status
        startPolling();

    } catch (error) {
        console.error('Upload error:', error);
        progressText.textContent = `Error: ${error.message}`;
        setTimeout(() => {
            progressSection.style.display = 'none';
            uploadSection.style.display = 'block';
        }, 3000);
    }
}

// ============================================================================
// STATUS POLLING
// ============================================================================

/**
 * Start polling the status endpoint
 */
function startPolling() {
    pollInterval = setInterval(checkStatus, 2000); // Poll every 2 seconds
    checkStatus(); // Check immediately
}

/**
 * Check audit status
 */
async function checkStatus() {
    if (!currentAuditId) return;

    try {
        const response = await fetch(`/status/${currentAuditId}`);

        if (!response.ok) {
            throw new Error('Failed to fetch status');
        }

        const data = await response.json();

        // Update progress text and step
        if (data.progress) {
            progressStep.textContent = getProgressStep(data.progress);
            progressText.textContent = data.progress;
        }

        // Handle completion
        if (data.status === 'complete') {
            clearInterval(pollInterval);
            progressSection.style.display = 'none';
            renderResults(data.results);
        }

        // Handle error
        if (data.status === 'error') {
            clearInterval(pollInterval);
            progressText.textContent = `Processing failed: ${data.error}`;
            setTimeout(() => {
                progressSection.style.display = 'none';
                uploadSection.style.display = 'block';
            }, 5000);
        }

    } catch (error) {
        console.error('Status check error:', error);
        clearInterval(pollInterval);
        progressText.textContent = 'Error checking status';
    }
}

// ============================================================================
// RESULTS RENDERING
// ============================================================================

/**
 * Render complete audit results
 */
function renderResults(results) {
    // Show results section
    resultsSection.style.display = 'block';

    // Render terminal-style company header
    renderCompanyHeader(results);

    // Render documents
    renderDocuments(results.documents);

    // Render timeline
    renderTimeline(results.timeline);

    // Render cap table
    renderCapTable(results.cap_table);

    // Render issues
    renderIssues(results.issues);

    // Render failed documents (if any)
    if (results.failed_documents && results.failed_documents.length > 0) {
        renderFailedDocuments(results.failed_documents);
    }

    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

/**
 * Render terminal-style company header with stats
 */
function renderCompanyHeader(results) {
    const container = document.querySelector('.company-header');

    // Calculate stats
    const docCount = results.documents ? results.documents.length : 0;
    const timeline = results.timeline || [];
    const dates = timeline.map(e => e.date).filter(d => d).sort();
    const yearSpan = dates.length > 1 ? `${dates[0]} to ${dates[dates.length - 1]}` : dates[0] || 'N/A';

    const html = `
        <div class="terminal-line">
            <span class="terminal-prompt">$</span> audit-report --company="${results.company_name || 'Unknown Company'}"
        </div>
        <div class="terminal-line">
            <span class="terminal-prompt">&gt;</span> Analysis complete
        </div>
        <div class="terminal-stats">
            <span class="terminal-stat">${docCount} documents</span>
            <span class="terminal-stat">${timeline.length} events</span>
            <span class="terminal-stat">${yearSpan}</span>
        </div>
    `;

    container.innerHTML = html;
}

/**
 * Render document inventory grouped by category with card grid
 */
function renderDocuments(documents) {
    const container = document.getElementById('documents-content');

    // Group documents by category
    const grouped = documents.reduce((acc, doc) => {
        const category = doc.category || 'Other';
        if (!acc[category]) acc[category] = [];
        acc[category].push(doc);
        return acc;
    }, {});

    // Render card grid (all collapsed by default)
    let html = '<div class="documents-grid">';
    for (const [category, docs] of Object.entries(grouped)) {
        html += `
            <div class="document-category collapsed">
                <h3 onclick="toggleCategory(this)">${category} <span class="doc-count">(${docs.length})</span></h3>
                <ul class="document-list">
                    ${docs.map(doc => `
                        <li>
                            ${doc.filename}
                            ${doc.error ? '<span class="error-badge">(Failed)</span>' : ''}
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
    }
    html += '</div>';

    container.innerHTML = html;
}

/**
 * Render timeline of corporate events with vertical line and dots
 */
function renderTimeline(timeline) {
    const container = document.getElementById('timeline-content');

    if (!timeline || timeline.length === 0) {
        container.innerHTML = '<p class="monospace">No timeline events found.</p>';
        return;
    }

    const html = timeline.map(event => `
        <div class="timeline-event">
            <div class="timeline-date">${event.date || 'Unknown'}</div>
            <div class="timeline-dot"></div>
            <div class="timeline-description">${event.description || 'No description'}</div>
        </div>
    `).join('');

    container.innerHTML = html;
}

/**
 * Render cap table with progress bars and verification indicators
 */
function renderCapTable(capTable) {
    const container = document.getElementById('cap-table-content');

    if (!capTable || capTable.length === 0) {
        container.innerHTML = '<p class="monospace">No equity issuances found in documents.</p>';
        return;
    }

    // Calculate totals
    const totalShares = capTable.reduce((sum, entry) => sum + (entry.shares || 0), 0);
    const totalOwnership = capTable.reduce((sum, entry) => sum + (entry.ownership_pct || 0), 0);

    const html = `
        <table>
            <thead>
                <tr>
                    <th>Shareholder</th>
                    <th>Class</th>
                    <th>Shares</th>
                    <th>Ownership</th>
                </tr>
            </thead>
            <tbody>
                ${capTable.map(entry => {
                    // Get verification badge if available
                    const verificationBadge = getVerificationBadge(entry.verification);

                    return `
                        <tr>
                            <td>${entry.shareholder || 'Unknown'}${verificationBadge}</td>
                            <td>${entry.share_class || 'N/A'}</td>
                            <td>${formatNumber(entry.shares)}</td>
                            <td>
                                <div class="ownership-cell">
                                    <div class="ownership-bar">
                                        <div class="ownership-fill" style="width: ${entry.ownership_pct || 0}%"></div>
                                    </div>
                                    <span class="ownership-text">${formatPercent(entry.ownership_pct)}</span>
                                </div>
                            </td>
                        </tr>
                    `;
                }).join('')}
                <tr class="total-row">
                    <td colspan="2">TOTAL</td>
                    <td>${formatNumber(totalShares)}</td>
                    <td><span class="ownership-text">${formatPercent(totalOwnership)}</span></td>
                </tr>
            </tbody>
        </table>
    `;

    container.innerHTML = html;
}

/**
 * Get verification badge HTML based on confidence score
 */
function getVerificationBadge(verification) {
    if (!verification || !verification.confidence_score) {
        return '';
    }

    const score = verification.confidence_score;
    const badgeClass = score >= 70 ? 'verification-high' : 'verification-low';
    const symbol = score >= 70 ? '✓' : '⚠';

    return `<span class="verification-badge ${badgeClass}" title="Verification confidence: ${score}%">${symbol} ${score}%</span>`;
}

/**
 * Render issues and recommendations
 */
function renderIssues(issues) {
    const container = document.getElementById('issues-content');

    if (!issues || issues.length === 0) {
        container.innerHTML = '<p class="monospace" style="color: var(--text-secondary);">✓ No issues detected</p>';
        return;
    }

    const html = issues.map(issue => `
        <div class="issue ${issue.severity}">
            <div class="issue-category">${issue.category || 'General Issue'}</div>
            <div class="issue-description">${issue.description || 'No description'}</div>
        </div>
    `).join('');

    container.innerHTML = html;
}

/**
 * Render failed documents section
 */
function renderFailedDocuments(failedDocs) {
    const section = document.getElementById('failed-section');
    const container = document.getElementById('failed-docs-content');

    section.style.display = 'block';

    const html = `
        <ul class="document-list">
            ${failedDocs.map(doc => `
                <li>
                    ${doc.filename}
                    <span class="error-badge">${doc.error || 'Unknown error'}</span>
                </li>
            `).join('')}
        </ul>
    `;

    container.innerHTML = html;
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Format number with commas
 */
function formatNumber(num) {
    if (num == null || isNaN(num)) return 'N/A';
    return num.toLocaleString();
}

/**
 * Format percentage
 */
function formatPercent(num) {
    if (num == null || isNaN(num)) return 'N/A';
    return `${num.toFixed(2)}%`;
}

/**
 * Toggle document category collapse/expand
 */
function toggleCategory(header) {
    const category = header.parentElement;
    category.classList.toggle('collapsed');
    category.classList.toggle('expanded');
}
