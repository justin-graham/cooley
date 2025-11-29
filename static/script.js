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
async function renderResults(results) {
    // Show results section
    resultsSection.style.display = 'block';

    // Render terminal-style company header
    renderCompanyHeader(results);

    // Update tab counts
    document.getElementById('doc-count').textContent = `(${results.documents ? results.documents.length : 0})`;
    document.getElementById('issue-count').textContent = `(${results.issues ? results.issues.length : 0})`;

    // Render documents in tab
    renderDocuments(results.documents);

    // Render issues in tab
    renderIssues(results.issues);

    // Render failed documents (if any)
    if (results.failed_documents && results.failed_documents.length > 0) {
        renderFailedDocuments(results.failed_documents);
    }

    // Initialize time-travel view
    await initTimeTravel(currentAuditId);

    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

/**
 * Render user-friendly company header with graphic and stats
 */
function renderCompanyHeader(results) {
    const container = document.querySelector('.company-header');

    // Calculate stats
    const docCount = results.documents ? results.documents.length : 0;
    const timeline = results.timeline || [];
    const dates = timeline.map(e => e.date).filter(d => d).sort();
    const firstDate = dates.length > 0 ? dates[0] : 'N/A';
    const lastDate = dates.length > 1 ? dates[dates.length - 1] : '';
    const dateRange = lastDate ? `${firstDate} - ${lastDate}` : firstDate;

    const html = `
        <img src="/static/stripe.png" alt="Company graphic" class="company-header-graphic">
        <div class="company-header-content">
            <h1 class="company-name">${results.company_name || 'Unknown Company'}</h1>
            <div class="company-stats">
                <div class="company-stat">
                    <span class="company-stat-label">Documents</span>
                    <span class="company-stat-value">${docCount}</span>
                </div>
                <div class="company-stat">
                    <span class="company-stat-label">Events</span>
                    <span class="company-stat-value">${timeline.length}</span>
                </div>
                <div class="company-stat">
                    <span class="company-stat-label">Period</span>
                    <span class="company-stat-value">${dateRange}</span>
                </div>
            </div>
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

// ============================================================================
// TIME-TRAVEL CAP TABLE VIEW
// ============================================================================

// State for audit view
const AuditViewState = {
    auditId: null,
    allEvents: [],      // Fetched once on load
    dateRange: { min: null, max: null },
    currentDate: null,  // Controlled by slider
    currentCapTable: null,
    previousCapTable: null  // For detecting changes
};

// ============================================================================
// SHAREHOLDER COLOR SYSTEM
// ============================================================================

const SHAREHOLDER_COLORS = [
    '#60A5FA', // blue
    '#34D399', // green
    '#A78BFA', // purple
    '#FB923C', // orange
    '#2DD4BF', // teal
    '#F472B6', // pink
    '#FBBF24', // amber
    '#818CF8'  // indigo
];

/**
 * Hash string to index (deterministic color assignment)
 */
function hashStringToIndex(str, arrayLength) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash = hash & hash; // Convert to 32-bit integer
    }
    return Math.abs(hash) % arrayLength;
}

/**
 * Get color for shareholder (deterministic based on name)
 */
function getShareholderColor(shareholderName) {
    if (!shareholderName) return SHAREHOLDER_COLORS[0];
    const index = hashStringToIndex(shareholderName, SHAREHOLDER_COLORS.length);
    return SHAREHOLDER_COLORS[index];
}

/**
 * Initialize the time-travel audit view
 */
async function initTimeTravel(auditId) {
    AuditViewState.auditId = auditId;

    try {
        // Fetch all events once
        const response = await fetch(`/api/audits/${auditId}/events`);
        if (!response.ok) {
            throw new Error(`Failed to fetch events: ${response.statusText}`);
        }
        AuditViewState.allEvents = await response.json();

        if (AuditViewState.allEvents.length === 0) {
            // No events found - show empty state
            document.getElementById('horizontal-timeline').innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No events found.</p>';
            document.getElementById('cap-table-container').innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No equity events found in this audit.</p>';
            document.getElementById('event-stream-container').innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No transactions to display.</p>';
            return;
        }

        // Calculate date range
        const dates = AuditViewState.allEvents.map(e => new Date(e.event_date));
        AuditViewState.dateRange.min = Math.min(...dates);
        AuditViewState.dateRange.max = Math.max(...dates);

        // Start at latest event
        const latestEvent = AuditViewState.allEvents[AuditViewState.allEvents.length - 1];
        AuditViewState.currentDate = new Date(latestEvent.event_date).getTime();

        // Render horizontal timeline
        renderHorizontalTimeline();

        // Initial render of cap table and events (select latest event)
        await selectTimelineEvent(latestEvent.id);

    } catch (error) {
        console.error('Failed to initialize time travel:', error);
        alert(`Failed to load audit data: ${error.message}`);
    }
}

/**
 * Render horizontal interactive timeline
 */
function renderHorizontalTimeline() {
    const container = document.getElementById('horizontal-timeline');
    const dateDisplay = document.getElementById('timeline-date-display');

    if (!AuditViewState.allEvents || AuditViewState.allEvents.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary);">No events to display.</p>';
        return;
    }

    const events = AuditViewState.allEvents;
    const minDate = AuditViewState.dateRange.min;
    const maxDate = AuditViewState.dateRange.max;
    const totalDuration = maxDate - minDate || 1; // Avoid division by zero

    // Create timeline HTML with equal spacing
    const timelineHTML = `
        <div class="timeline-track">
            <div class="timeline-line"></div>
            ${events.map((event, index) => {
                // Equal spacing with edge padding for cleaner look
                const padding = 4;
                const usableWidth = 100 - (2 * padding);
                const positionPercent = padding + (events.length > 1
                    ? (index / (events.length - 1)) * usableWidth
                    : usableWidth / 2);
                const color = event.shareholder_name ? getShareholderColor(event.shareholder_name) : '#666';

                return `
                    <div class="timeline-node-wrapper" style="left: ${positionPercent}%;" data-event-id="${event.id}">
                        <div class="timeline-node" style="background-color: ${color};" title="${event.event_type}: ${event.shareholder_name || 'Company'} - ${new Date(event.event_date).toLocaleDateString()}"></div>
                        ${index % 3 === 0 || index === 0 || index === events.length - 1 ?
                            `<div class="timeline-date-label">${new Date(event.event_date).toLocaleDateString('en-US', {month: 'short', year: 'numeric'})}</div>`
                            : ''}
                    </div>
                `;
            }).join('')}
        </div>
    `;

    container.innerHTML = timelineHTML;

    // Add click handlers to nodes
    const nodes = container.querySelectorAll('.timeline-node-wrapper');
    nodes.forEach(nodeWrapper => {
        nodeWrapper.addEventListener('click', () => {
            const eventId = nodeWrapper.getAttribute('data-event-id');
            selectTimelineEvent(eventId);
        });
    });

    // Update date display
    const currentEvent = events.find(e => e.id === events[events.length - 1].id);
    if (currentEvent) {
        const dateStr = new Date(currentEvent.event_date).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
        dateDisplay.textContent = `Viewing: ${dateStr}`;
    }
}

/**
 * Select a timeline event and update all views
 */
async function selectTimelineEvent(eventId) {
    const event = AuditViewState.allEvents.find(e => e.id === eventId);
    if (!event) return;

    // Update current date
    AuditViewState.currentDate = new Date(event.event_date).getTime();

    // Update visual selection on timeline
    const allNodes = document.querySelectorAll('.timeline-node-wrapper');
    allNodes.forEach(node => {
        const nodeEventId = node.getAttribute('data-event-id');
        const nodeCircle = node.querySelector('.timeline-node');

        if (nodeEventId === eventId) {
            nodeCircle.classList.add('selected');
        } else {
            nodeCircle.classList.remove('selected');
        }
    });

    // Update date display
    const dateStr = new Date(event.event_date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
    document.getElementById('timeline-date-display').textContent = `Viewing: ${dateStr}`;

    // Re-render cap table and event stream
    await renderCapTable();
    renderEventStream();
}

/**
 * Render cap table (fetches from API)
 */
async function renderCapTable() {
    const dateStr = new Date(AuditViewState.currentDate).toISOString().split('T')[0];

    try {
        const response = await fetch(`/api/audits/${AuditViewState.auditId}/captable?as_of_date=${dateStr}`);
        if (!response.ok) {
            throw new Error(`API error: ${response.statusText}`);
        }

        const newCapTable = await response.json();

        // Detect changed shareholders
        const changedShareholders = new Set();
        if (AuditViewState.previousCapTable) {
            const prevMap = new Map(
                AuditViewState.previousCapTable.shareholders.map(sh => [sh.shareholder, sh])
            );
            newCapTable.shareholders.forEach(sh => {
                const prev = prevMap.get(sh.shareholder);
                if (!prev || prev.shares !== sh.shares) {
                    changedShareholders.add(sh.shareholder);
                }
            });
        }

        AuditViewState.previousCapTable = AuditViewState.currentCapTable;
        AuditViewState.currentCapTable = newCapTable;

        const container = document.getElementById('cap-table-container');
        container.innerHTML = ''; // Clear

        if (AuditViewState.currentCapTable.shareholders.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem; margin-top: 1rem;">No shareholders at this date.</p>';
            return;
        }

        // Add color legend
        const legend = document.createElement('div');
        legend.className = 'color-legend';
        legend.innerHTML = `
            <div class="legend-title">Shareholders:</div>
            <div class="legend-items">
                ${AuditViewState.currentCapTable.shareholders.map(sh => {
                    const color = getShareholderColor(sh.shareholder);
                    return `<span class="legend-item"><span class="legend-square" style="background-color: ${color};"></span>${sh.shareholder}</span>`;
                }).join('')}
            </div>
        `;
        container.appendChild(legend);

        // Build table
        const table = document.createElement('table');
        table.className = 'cap-table';

        // Create tbody separately to add event listeners
        const tbody = document.createElement('tbody');

        AuditViewState.currentCapTable.shareholders.forEach(sh => {
            const row = document.createElement('tr');
            row.className = 'cap-table-row';
            row.setAttribute('data-shareholder', sh.shareholder);

            const color = getShareholderColor(sh.shareholder);
            const isChanged = changedShareholders.has(sh.shareholder);

            if (isChanged) {
                row.classList.add('changed');
            }

            row.innerHTML = `
                <td>
                    ${sh.shareholder}
                    ${sh.compliance_issues.length > 0 ?
                        `<span style="color: var(--accent); font-size: 0.625rem; margin-left: 4px;" title="${sh.compliance_issues.join('; ')}">⚠</span>`
                        : ''}
                </td>
                <td>${sh.share_class}</td>
                <td>${formatNumber(sh.shares)}</td>
                <td class="ownership-number">${formatPercent(sh.ownership_pct)}</td>
            `;

            // Add hover listeners
            row.addEventListener('mouseenter', () => highlightShareholder(sh.shareholder, 'enter'));
            row.addEventListener('mouseleave', () => highlightShareholder(sh.shareholder, 'leave'));

            tbody.appendChild(row);
        });

        // Create thead
        const thead = document.createElement('thead');
        thead.innerHTML = `
            <tr>
                <th>Shareholder</th>
                <th>Class</th>
                <th>Shares</th>
                <th>Ownership %</th>
            </tr>
        `;

        // Create tfoot
        const tfoot = document.createElement('tfoot');
        tfoot.innerHTML = `
            <tr>
                <td colspan="2">Total</td>
                <td>${formatNumber(AuditViewState.currentCapTable.total_shares)}</td>
                <td>100.00%</td>
            </tr>
        `;

        // Assemble table (append elements to preserve event listeners)
        table.appendChild(thead);
        table.appendChild(tbody);
        table.appendChild(tfoot);

        container.appendChild(table);

    } catch (error) {
        console.error('Failed to render cap table:', error);
        document.getElementById('cap-table-container').innerHTML =
            `<p style="color: var(--accent); font-size: 0.875rem;">Error loading cap table: ${error.message}</p>`;
    }
}

/**
 * Render event stream (pure client-side filtering, no API call)
 */
function renderEventStream() {
    const container = document.getElementById('event-stream-container');
    container.innerHTML = ''; // Clear

    // Filter events by current date
    const visibleEvents = AuditViewState.allEvents.filter(
        e => new Date(e.event_date).getTime() <= AuditViewState.currentDate
    );

    if (visibleEvents.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No events at this date.</p>';
        return;
    }

    // Create cards
    const fragment = document.createDocumentFragment();
    visibleEvents.forEach(event => {
        const card = document.createElement('div');
        const statusClass = event.compliance_status.toLowerCase();
        card.className = `event-card ${statusClass}`;

        const eventDateStr = new Date(event.event_date).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });

        // Format event type for display
        const eventTypeDisplay = event.event_type.replace(/_/g, ' ').toUpperCase();

        // Build details text with colored pill
        let detailsText = '';
        let shareholderColor = null;
        if (event.shareholder_name) {
            shareholderColor = getShareholderColor(event.shareholder_name);
            detailsText = `<span class="shareholder-pill" style="background-color: ${shareholderColor};">${event.shareholder_name}</span>`;
            if (event.share_delta !== 0) {
                detailsText += ` ${event.share_delta > 0 ? '+' : ''}${formatNumber(event.share_delta)} ${event.share_class || 'shares'}`;
            }
        }

        // Add shareholder data attribute for hover interactions
        if (event.shareholder_name) {
            card.setAttribute('data-shareholder', event.shareholder_name);
        }

        card.innerHTML = `
            <div class="event-card-header">
                <span class="event-type">${eventTypeDisplay}</span>
                <span class="event-date">${eventDateStr}</span>
            </div>
            ${detailsText ? `<div class="event-details" style="${shareholderColor ? `border-left: 5px solid ${shareholderColor}; padding-left: 8px;` : ''}">${detailsText}</div>` : ''}
            ${event.source_snippet ? `<div class="source-quote">"${event.source_snippet}"</div>` : ''}
            ${event.compliance_note ? `<div class="compliance-note">${event.compliance_note}</div>` : ''}
            <div class="doc-reference">
                ${event.source_doc_id ? `<span class="doc-link" data-doc-id="${event.source_doc_id}" data-snippet="${event.source_snippet || ''}" title="View source document">Source: ${event.source_doc_id.substring(0, 8)}...</span>` : ''}
                ${event.approval_doc_id ? ` <span class="doc-link" data-doc-id="${event.approval_doc_id}" data-snippet="${event.approval_snippet || ''}" title="View approval document">Approval: ${event.approval_doc_id.substring(0, 8)}...</span>` : ''}
            </div>
        `;

        // Add hover listeners for cap table interaction
        if (event.shareholder_name) {
            card.addEventListener('mouseenter', () => highlightShareholder(event.shareholder_name, 'enter'));
            card.addEventListener('mouseleave', () => highlightShareholder(event.shareholder_name, 'leave'));
        }

        fragment.appendChild(card);

        // Add click handlers to document links
        const docLinks = card.querySelectorAll('.doc-link');
        docLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.stopPropagation();
                const docId = link.getAttribute('data-doc-id');
                const snippet = link.getAttribute('data-snippet');
                showDocumentModal(AuditViewState.auditId, docId, snippet || null);
            });
        });
    });

    container.appendChild(fragment);

    // Auto-scroll to latest event
    if (container.lastChild) {
        container.lastChild.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
}

/**
 * Highlight/unhighlight shareholder across cap table and event stream
 * @param {string} shareholderName - Name of shareholder
 * @param {string} action - 'enter' or 'leave'
 */
function highlightShareholder(shareholderName, action) {
    if (!shareholderName) return;

    // Find all elements with this shareholder
    const capTableRows = document.querySelectorAll(`.cap-table-row[data-shareholder="${shareholderName}"]`);
    const eventCards = document.querySelectorAll(`.event-card[data-shareholder="${shareholderName}"]`);

    if (action === 'enter') {
        capTableRows.forEach(row => row.classList.add('highlight'));
        eventCards.forEach(card => card.classList.add('highlight'));
    } else {
        capTableRows.forEach(row => row.classList.remove('highlight'));
        eventCards.forEach(card => card.classList.remove('highlight'));
    }
}

/**
 * Utility: Debounce function to limit API calls
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Tab switching
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active class from all tabs
            tabBtns.forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.add('hidden'));

            // Add active class to clicked tab
            btn.classList.add('active');
            const tabId = btn.getAttribute('data-tab');
            document.getElementById(`${tabId}-tab`).classList.remove('hidden');
        });
    });

    // Modal event listeners
    const modal = document.getElementById('document-modal');
    const modalBackdrop = modal?.querySelector('.modal-backdrop');
    const modalClose = modal?.querySelector('.modal-close');

    if (modalBackdrop) {
        modalBackdrop.addEventListener('click', hideDocumentModal);
    }

    if (modalClose) {
        modalClose.addEventListener('click', hideDocumentModal);
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Escape key: Close modal
        if (e.key === 'Escape' && modal?.style.display === 'flex') {
            hideDocumentModal();
            return;
        }

        // Arrow keys: Navigate timeline
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            if (AuditViewState.allEvents && AuditViewState.allEvents.length > 0) {
                e.preventDefault(); // Prevent page scroll
                const currentIndex = AuditViewState.allEvents.findIndex(
                    evt => new Date(evt.event_date).getTime() === AuditViewState.currentDate
                );

                let newIndex = currentIndex;
                if (e.key === 'ArrowLeft' && currentIndex > 0) {
                    newIndex = currentIndex - 1;
                } else if (e.key === 'ArrowRight' && currentIndex < AuditViewState.allEvents.length - 1) {
                    newIndex = currentIndex + 1;
                }

                if (newIndex !== currentIndex) {
                    selectTimelineEvent(AuditViewState.allEvents[newIndex].id);
                }
            }
        }
    });
});

// ============================================================================
// DOCUMENT VIEWER MODAL
// ============================================================================

/**
 * Show document viewer modal with full text
 * @param {string} auditId - UUID of the audit
 * @param {string} docId - UUID of the document
 * @param {string} [snippetToHighlight] - Optional text snippet to highlight
 */
async function showDocumentModal(auditId, docId, snippetToHighlight = null) {
    const modal = document.getElementById('document-modal');
    const modalFilename = document.getElementById('modal-filename');
    const modalClassification = document.getElementById('modal-classification');
    const modalContent = document.getElementById('modal-content');

    // Show modal immediately with loading state
    modal.style.display = 'flex';
    modalFilename.textContent = 'Loading...';
    modalClassification.textContent = '';
    modalContent.innerHTML = '<div style="text-align: center; padding: 2rem;">Loading document...</div>';

    try {
        // Fetch document
        const response = await fetch(`/api/audits/${auditId}/documents/${docId}`);
        if (!response.ok) {
            throw new Error(`Failed to fetch document: ${response.statusText}`);
        }

        const doc = await response.json();

        // Update modal content
        modalFilename.textContent = doc.filename || 'Document';
        modalClassification.textContent = doc.classification || 'Unknown Document Type';

        let fullText = doc.full_text || 'No text content available';

        // Highlight snippet if provided
        if (snippetToHighlight && fullText.includes(snippetToHighlight)) {
            fullText = fullText.replace(
                snippetToHighlight,
                `<mark>${escapeHtml(snippetToHighlight)}</mark>`
            );
            modalContent.innerHTML = escapeHtml(fullText).replace(
                `&lt;mark&gt;${escapeHtml(snippetToHighlight)}&lt;/mark&gt;`,
                `<mark>${escapeHtml(snippetToHighlight)}</mark>`
            );

            // Scroll to highlighted snippet after a brief delay
            setTimeout(() => {
                const mark = modalContent.querySelector('mark');
                if (mark) {
                    mark.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }, 100);
        } else {
            modalContent.textContent = fullText;
        }

    } catch (error) {
        console.error('Error loading document:', error);
        modalFilename.textContent = 'Error';
        modalClassification.textContent = '';
        modalContent.innerHTML = `<div style="color: var(--accent); padding: 2rem; text-align: center;">
            Failed to load document: ${escapeHtml(error.message)}
        </div>`;
    }
}

/**
 * Hide document viewer modal
 */
function hideDocumentModal() {
    const modal = document.getElementById('document-modal');
    modal.style.display = 'none';
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
