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
const progressText = document.getElementById('progress-text');
const resultsSection = document.getElementById('results');
const uploadSection = document.getElementById('upload-section');

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
    progressSection.style.display = 'block';
    progressText.textContent = 'Uploading...';

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

        // Update progress text
        if (data.progress) {
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

    // Render company name
    document.getElementById('company-name').textContent = results.company_name || 'Unknown Company';

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
 * Render document inventory grouped by category
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

    // Render each category
    let html = '';
    for (const [category, docs] of Object.entries(grouped)) {
        html += `
            <div class="document-category">
                <h3>${category} (${docs.length})</h3>
                <ul class="document-list">
                    ${docs.map(doc => `
                        <li>
                            ${doc.filename}
                            ${doc.error ? '<span class="error-badge">(Failed to parse)</span>' : ''}
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
    }

    container.innerHTML = html;
}

/**
 * Render timeline of corporate events
 */
function renderTimeline(timeline) {
    const container = document.getElementById('timeline-content');

    if (!timeline || timeline.length === 0) {
        container.innerHTML = '<p class="monospace">No timeline events found.</p>';
        return;
    }

    const html = timeline.map(event => `
        <div class="timeline-event">
            <div class="timeline-date">${event.date || 'Unknown Date'}</div>
            <div class="timeline-description">${event.description || 'No description'}</div>
        </div>
    `).join('');

    container.innerHTML = html;
}

/**
 * Render cap table
 */
function renderCapTable(capTable) {
    const container = document.getElementById('cap-table-content');

    if (!capTable || capTable.length === 0) {
        container.innerHTML = '<p class="monospace">No equity issuances found in documents.</p>';
        return;
    }

    const html = `
        <table>
            <thead>
                <tr>
                    <th>Shareholder</th>
                    <th>Class</th>
                    <th>Shares</th>
                    <th>Ownership %</th>
                </tr>
            </thead>
            <tbody>
                ${capTable.map(entry => `
                    <tr>
                        <td>${entry.shareholder || 'Unknown'}</td>
                        <td>${entry.share_class || 'N/A'}</td>
                        <td>${formatNumber(entry.shares)}</td>
                        <td>${formatPercent(entry.ownership_pct)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;

    container.innerHTML = html;
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
