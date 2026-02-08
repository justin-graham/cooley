/**
 * Corporate Governance Audit Platform - Frontend Logic
 * Handles file upload, status polling, and results rendering
 */

// State
let currentAuditId = null;
let pollInterval = null;
let isDemoModeActive = false;  // Track if currently in demo mode
let demoDataCache = null;      // Cache demo data for client-side rendering

// DOM Elements
const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');
const progressSection = document.getElementById('progress');
const progressStep = document.getElementById('progress-step');
const progressText = document.getElementById('progress-text');
const resultsSection = document.getElementById('results');
const uploadSection = document.getElementById('upload-section');

// ============================================================================
// DATA ROOM MAPPING
// ============================================================================

const DATA_ROOM_MAPPING = [
    {
        title: '1. Authority and Governance',
        subitems: [
            { label: 'Certificate of Incorporation (all versions)', categories: ['Charter Document'] },
            { label: 'Board consents approving equity plans, grants, SAFEs, notes, and share increases', categories: ['Board/Shareholder Minutes'] },
            { label: 'Stockholder consents approving equity plans, charter amendments, and financings', categories: [] }
        ]
    },
    {
        title: '2. Equity',
        subitems: [
            { label: 'Investors\u2019 Rights, Voting, and ROFR / Co-Sale Agreements', categories: [] },
            { label: 'Equity Incentive Plan, amendments, and share reserve changes', categories: ['Equity Incentive Plan'] },
            { label: 'Founder and investor stock purchase agreements', categories: ['Stock Purchase Agreement'] },
            { label: 'Option, RSU, and warrant agreements', categories: ['Option Grant Agreement'] },
            { label: 'SAFEs, convertible notes, and side letters', categories: ['SAFE', 'Convertible Note'] },
            { label: 'Option exercise notices and payment records', categories: [] },
            { label: 'Share repurchases, forfeitures, and cancellations', categories: ['Share Repurchase Agreement'] },
            { label: 'Current and historical cap tables', categories: ['Financial Statement', 'Stock Certificate'] },
            { label: 'Fully diluted calculations and waterfalls', categories: [] }
        ]
    },
    {
        title: '3. Employment and Advisors',
        subitems: [
            { label: 'Employee offer letters and employment agreements', categories: ['Employment Agreement'] },
            { label: 'Contractor and advisor agreements', categories: [] },
            { label: 'Equity grants tied to each individual', categories: [] },
            { label: 'Vesting schedules and acceleration provisions', categories: [] }
        ]
    },
    {
        title: '4. Intellectual Property Ownership',
        subitems: [
            { label: 'Founder, employee, contractor, and advisor IP assignment agreements', categories: ['IP/Proprietary Info Agreement'] },
            { label: 'Confidentiality agreements', categories: [] },
            { label: 'Inbound IP licenses and open source disclosures', categories: [] },
            { label: 'University or prior employer IP agreements', categories: [] },
            { label: 'IP carve-outs and side letters', categories: [] }
        ]
    },
    {
        title: '5. Securities Law Compliance',
        subitems: [
            { label: 'Rule 701 disclosures and financials', categories: ['Corporate Records'] },
            { label: 'Form D filings and investor questionnaires', categories: ['83(b) Election'] }
        ]
    },
    {
        title: '6. Exceptions and Risk Items',
        subitems: [
            { label: 'Missing approvals or undocumented issuances', categories: [] },
            { label: 'Disputed ownership', categories: [] },
            { label: 'Unassigned or encumbered IP', categories: [] },
            { label: 'Non-standard equity or side arrangements', categories: ['Other', 'Indemnification Agreement'] }
        ]
    }
];

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
// DEMO MODE
// ============================================================================

/**
 * Load and display demo data without requiring file upload
 */
async function loadDemoMode() {
    try {
        // Show progress section
        uploadSection.style.display = 'none';
        progressSection.style.display = 'flex';
        progressStep.textContent = 'Loading Demo';
        progressText.textContent = 'Loading demo audit data...';

        // Fetch demo data
        const response = await fetch('/static/demo-data.json');
        if (!response.ok) {
            throw new Error('Failed to load demo data');
        }

        const demoData = await response.json();

        // Set demo mode flags and cache data
        isDemoModeActive = true;
        demoDataCache = demoData;
        currentAuditId = demoData.id;
        console.log('[DEMO] Flags set:', { isDemoModeActive, hasDemoData: !!demoDataCache, auditId: currentAuditId });

        // Simulate a brief loading delay for realism
        await new Promise(resolve => setTimeout(resolve, 1000));

        // Hide progress and show results
        progressSection.style.display = 'none';
        await renderResults(demoData);

    } catch (error) {
        console.error('Demo mode error:', error);
        progressText.textContent = `Error loading demo: ${error.message}`;
        setTimeout(() => {
            progressSection.style.display = 'none';
            uploadSection.style.display = 'block';
        }, 3000);
    }
}

/**
 * Convert demo timeline to EquityEvent format for time-travel feature
 */
function convertDemoTimelineToEvents(timeline, documents) {
    console.log('[CONVERT] Timeline events:', timeline?.length || 0);
    console.log('[CONVERT] Full timeline data:', timeline);

    if (!timeline || !Array.isArray(timeline)) return [];

    const results = timeline.map((event, index) => {
        // Extract shareholder name from description if present
        let shareholderName = null;
        let shareClass = null;
        let shareDelta = 0;

        // Try to extract from event description
        const descMatch = event.description.match(/([\w\s]+)\s+(purchased|granted|received|repurchased)/i);
        if (descMatch) {
            shareholderName = descMatch[1].trim();
        }

        // Determine event type and share delta from description
        let eventType = 'formation';
        if (event.description.includes('purchased') || event.description.includes('Financing')) {
            eventType = 'issuance';
            const sharesMatch = event.description.match(/([\d,]+)\s+(common|preferred|shares)/i);
            if (sharesMatch) {
                shareDelta = parseInt(sharesMatch[1].replace(/,/g, ''));
                shareClass = sharesMatch[2];
            }
        } else if (event.description.includes('granted')) {
            eventType = 'option_grant';
            const sharesMatch = event.description.match(/([\d,]+)\s+/);
            if (sharesMatch) {
                shareDelta = parseInt(sharesMatch[1].replace(/,/g, ''));
                shareClass = 'Option';
            }
        } else if (event.description.includes('repurchased')) {
            eventType = 'repurchase';
            const sharesMatch = event.description.match(/([\d,]+)\s+shares/i);
            if (sharesMatch) {
                shareDelta = -parseInt(sharesMatch[1].replace(/,/g, ''));
            }
        }

        console.log(`[CONVERT] Event ${index}:`, {
            date: event.date,
            description: event.description,
            extractedType: eventType,
            shareholderName,
            shareDelta
        });

        return {
            id: `demo-event-${index}`,
            audit_id: 999,
            event_date: event.date,
            event_type: eventType,
            shareholder_name: shareholderName,
            share_class: shareClass || 'Common',
            share_delta: shareDelta,
            source_snippet: event.description,
            approval_snippet: null,
            compliance_status: 'VERIFIED',
            compliance_note: null,
            source_doc_id: event.source_documents ? event.source_documents[0] : null,
            approval_doc_id: null,
            details: {}
        };
    });

    console.log('[CONVERT] Generated events:', results.length);
    console.log('[CONVERT] Event details:', results);

    return results;
}

/**
 * Convert demo cap_table to CapTableState format
 */
function convertDemoCapTable(capTable, asOfDate) {
    if (!capTable || typeof capTable !== 'object') {
        return { shareholders: [], total_shares: 0, as_of_date: asOfDate };
    }

    const shareholders = Object.entries(capTable).map(([name, data]) => ({
        shareholder: name,
        share_class: data.share_type || 'Common',
        shares: data.shares || 0,
        ownership_pct: data.ownership_percent || 0,
        compliance_issues: []
    }));

    const totalShares = shareholders.reduce((sum, sh) => sum + sh.shares, 0);

    return {
        shareholders,
        total_shares: totalShares,
        as_of_date: asOfDate
    };
}

/**
 * Check if we're in demo mode (via URL parameter)
 */
function isDemoMode() {
    const params = new URLSearchParams(window.location.search);
    return params.get('demo') === 'true';
}

/**
 * Initialize demo mode if URL parameter is present
 */
function initDemoModeIfNeeded() {
    if (isDemoMode()) {
        loadDemoMode();
    }
}

// Check for demo mode on page load
document.addEventListener('DOMContentLoaded', initDemoModeIfNeeded);

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
            progressSection.innerHTML = `
                <div role="alert" style="text-align: center; padding: 2rem;">
                    <p style="font-family: var(--font-grotesk); font-size: var(--text-lg); margin-bottom: 0.5rem;">Processing failed</p>
                    <p style="color: var(--gray-600); margin-bottom: 1.5rem;">${escapeHtml(data.error || 'An unexpected error occurred')}</p>
                    <button class="btn btn-primary" onclick="showUploadPage()">Try Again</button>
                </div>
            `;
        }

    } catch (error) {
        clearInterval(pollInterval);
        progressSection.innerHTML = `
            <div role="alert" style="text-align: center; padding: 2rem;">
                <p style="font-family: var(--font-grotesk); font-size: var(--text-lg); margin-bottom: 0.5rem;">Connection error</p>
                <p style="color: var(--gray-600); margin-bottom: 1.5rem;">Unable to check processing status.</p>
                <button class="btn btn-primary" onclick="showUploadPage()">Try Again</button>
            </div>
        `;
    }
}

// ============================================================================
// RESULTS RENDERING
// ============================================================================

/**
 * Render complete audit results
 */
async function renderResults(results) {
    // Hide upload page elements
    document.getElementById('upload-header').style.display = 'none';

    // Ensure nav shows Home when off the landing screen
    setHomeLinkVisibility(true);

    // Show results section
    resultsSection.style.display = 'block';

    // Render two-column hero header
    renderCompanyHeader(results);
    initHeroScrollMotion();

    // Normalize compliance issues source
    const complianceArray = results.compliance_issues || results.issues || [];

    // Render document breakdown accordion
    renderDocumentAccordion(
        results.documents || [],
        results.company_name,
        results.failed_documents || [],
        complianceArray
    );

    // NOTE: renderDocuments() and renderIssues() removed - those DOM containers no longer exist
    // Documents are now displayed in the accordion above

    // Update summary counts on the left
    const docCount = results.documents ? results.documents.length : 0;
    const categoryCount = new Set((results.documents || []).map(doc => (doc.category || doc.classification || 'Other'))).size;
    const issuesCount = complianceArray.length;
    const failedCount = results.failed_documents ? results.failed_documents.length : 0;

    const docCountEl = document.getElementById('doc-count');
    const catCountEl = document.getElementById('category-count');
    const issuesCountEl = document.getElementById('issues-count');
    const failedCountEl = document.getElementById('failed-count');
    if (docCountEl) docCountEl.textContent = docCount;
    if (catCountEl) catCountEl.textContent = categoryCount;
    if (issuesCountEl) issuesCountEl.textContent = issuesCount;
    if (failedCountEl) failedCountEl.textContent = failedCount;

    // Dynamic CTA company name
    const ctaName = document.getElementById('cta-company-name');
    if (ctaName && results.company_name) {
        ctaName.textContent = results.company_name;
    }

    // Initialize time-travel view with error handling
    try {
        await initTimeTravel(currentAuditId);
    } catch (error) {
        console.error('Failed to initialize time-travel view:', error);
        // Show a user-friendly error message
        document.getElementById('cap-table-container').innerHTML =
            '<p style="color: var(--accent); padding: 1rem;">Unable to load cap table. Please refresh the page.</p>';
        document.getElementById('event-stream-container').innerHTML =
            '<p style="color: var(--accent); padding: 1rem;">Unable to load event stream. Please refresh the page.</p>';
    }

    // Load download previews
    loadDownloadPreviews(currentAuditId);

    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

/**
 * Render user-friendly company header with graphic and stats in two-column hero layout
 */
function renderCompanyHeader(results) {
    const leftContainer = document.querySelector('.hero-left .company-header-content');

    // Calculate stats
    const docCount = results.documents ? results.documents.length : 0;
    const timeline = results.timeline || [];
    const dates = timeline.map(e => e.date).filter(d => d).sort();

    // Format dates as MMM DD, YYYY
    const formatDate = (dateStr) => {
        if (!dateStr || dateStr === 'N/A') return 'N/A';
        return new Date(dateStr).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        });
    };

    const firstDate = dates.length > 0 ? formatDate(dates[0]) : 'N/A';
    const lastDate = dates.length > 1 ? formatDate(dates[dates.length - 1]) : '';
    const dateRange = lastDate ? `${firstDate} - ${lastDate}` : firstDate;

    // Render left column: Company info and stats with scroll-reveal classes
    const leftHTML = `
        <h1 class="company-name scroll-reveal">${results.company_name || 'Unknown Company'}</h1>
        <p class="company-period scroll-reveal" data-delay="1">${dateRange}</p>
        <div class="company-stats scroll-reveal" data-delay="1">
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
    `;

    leftContainer.innerHTML = leftHTML;

    // Re-initialize scroll reveal for dynamically added elements
    if (typeof initScrollReveal === 'function') {
        initScrollReveal();
    }
}

/**
 * Render document breakdown accordion (Martian-style)
 */
function renderDocumentAccordion(documents, companyName, failedDocuments = [], complianceIssues = []) {
    const container = document.getElementById('document-accordion');
    const nameSpan = document.getElementById('company-name-breakdown');

    // Update company name in heading
    if (nameSpan && companyName) {
        nameSpan.textContent = companyName;
    }

    const complianceItem = `
        <div class="accordion-item">
            <div class="accordion-header" role="button" tabindex="0" aria-expanded="false" onclick="toggleAccordion(this)" onkeydown="handleAccordionKeydown(event)">
                <h3 class="accordion-title">Compliance Issues</h3>
                <span class="accordion-toggle" aria-hidden="true">+</span>
            </div>
            <div class="accordion-content" role="region" aria-hidden="true">
                <div class="accordion-body">
                    ${complianceIssues.length
                        ? complianceIssues.map(issue => {
                            if (typeof issue === 'string') return `<div class="issue-note spacer">${issue}</div>`;
                            const sev = issue.severity ? issue.severity.toUpperCase() : 'ISSUE';
                            const desc = issue.description || issue.message || JSON.stringify(issue);
                            const sevClass = sev === 'CRITICAL' ? 'issue-critical' : sev === 'WARNING' ? 'issue-warning' : 'issue-note';
                            return `<div class="${sevClass} spacer"><strong>${sev}:</strong> ${desc}</div>`;
                          }).join('')
                        : 'No compliance issues.'}
                </div>
            </div>
        </div>
    `;

    const failedItem = `
        <div class="accordion-item">
            <div class="accordion-header" role="button" tabindex="0" aria-expanded="false" onclick="toggleAccordion(this)" onkeydown="handleAccordionKeydown(event)">
                <h3 class="accordion-title">Failed Documents</h3>
                <span class="accordion-toggle" aria-hidden="true">+</span>
            </div>
            <div class="accordion-content" role="region" aria-hidden="true">
                <div class="accordion-body">
                    ${failedDocuments.length
                        ? failedDocuments.map(doc => `<div>${doc.filename || doc}</div>`).join('')
                        : 'No failed documents.'}
                </div>
            </div>
        </div>
    `;

    // Build Data Room accordion item (nested folder structure)
    const dataRoomItem = buildDataRoomItem(documents);

    const html = complianceItem + failedItem + dataRoomItem;

    container.innerHTML = html || '<p style="text-align: center; color: var(--text-secondary);">No documents to display</p>';

    // Wire up newly added document links to open modal
    const docLinks = container.querySelectorAll('.doc-link');
    docLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.stopPropagation();
            const docId = link.getAttribute('data-doc-id');
            const snippet = link.getAttribute('data-snippet') || '';
            if (docId) {
                showDocumentModal(AuditViewState.auditId, docId, snippet || null);
            }
        });
    });
}

/**
 * Toggle accordion item open/closed with accessibility support
 */
function toggleAccordion(headerElement) {
    const item = headerElement.parentElement;
    const wasActive = item.classList.contains('active');
    const content = item.querySelector('.accordion-content');

    // Close all accordion items and update ARIA
    document.querySelectorAll('.accordion-item').forEach(el => {
        el.classList.remove('active');
        const header = el.querySelector('.accordion-header');
        const contentEl = el.querySelector('.accordion-content');
        if (header) header.setAttribute('aria-expanded', 'false');
        if (contentEl) contentEl.setAttribute('aria-hidden', 'true');
    });

    // Toggle current item (if it wasn't already open)
    if (!wasActive) {
        item.classList.add('active');
        headerElement.setAttribute('aria-expanded', 'true');
        if (content) content.setAttribute('aria-hidden', 'false');
    }
}

/**
 * Handle keyboard events for accordion accessibility
 */
function handleAccordionKeydown(event) {
    if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleAccordion(event.target);
    }
}

/**
 * Toggle Data Room sub-folder open/closed (independent of top-level accordion)
 */
function toggleDataRoomFolder(headerElement) {
    const folder = headerElement.parentElement;
    folder.classList.toggle('open');
}

/**
 * Build the Data Room accordion item HTML from classified documents
 */
function buildDataRoomItem(documents) {
    // Group docs by category for lookup
    const docsByCategory = {};
    documents.forEach(doc => {
        const cat = doc.category || doc.classification || 'Other';
        if (!docsByCategory[cat]) docsByCategory[cat] = [];
        docsByCategory[cat].push(doc);
    });

    // Track which categories are placed into the Data Room
    const placedCategories = new Set();

    const foldersHtml = DATA_ROOM_MAPPING.map(folder => {
        let folderDocCount = 0;

        const subitemsHtml = folder.subitems.map(subitem => {
            const docs = [];
            subitem.categories.forEach(cat => {
                placedCategories.add(cat);
                if (docsByCategory[cat]) {
                    docs.push(...docsByCategory[cat]);
                }
            });
            folderDocCount += docs.length;

            if (docs.length === 0) {
                return `
                    <div class="data-room-subitem">
                        <div class="data-room-subitem-header">${subitem.label}</div>
                        <div class="data-room-subitem-empty">No documents</div>
                    </div>
                `;
            }

            return `
                <div class="data-room-subitem">
                    <div class="data-room-subitem-header">${subitem.label} (${docs.length})</div>
                    <div class="data-room-subitem-docs">
                        ${docs.map(doc => {
                            const docId = doc.document_id || doc.id || '';
                            const name = doc.filename || 'Untitled';
                            return `<div class="doc-link" data-doc-id="${docId}" data-snippet="" title="View document" role="button" tabindex="0">${name}</div>`;
                        }).join('')}
                    </div>
                </div>
            `;
        }).join('');

        return `
            <div class="data-room-folder">
                <div class="data-room-folder-header" onclick="toggleDataRoomFolder(this)" role="button" tabindex="0">
                    <span class="data-room-folder-title">${folder.title}</span>
                    <span class="data-room-folder-count">${folderDocCount} doc${folderDocCount !== 1 ? 's' : ''}</span>
                    <span class="data-room-folder-toggle">+</span>
                </div>
                <div class="data-room-folder-content">
                    ${subitemsHtml}
                </div>
            </div>
        `;
    }).join('');

    // Catch any unplaced documents and add them to Exceptions
    const unplacedDocs = [];
    Object.keys(docsByCategory).forEach(cat => {
        if (!placedCategories.has(cat)) {
            unplacedDocs.push(...docsByCategory[cat]);
        }
    });

    let unplacedHtml = '';
    if (unplacedDocs.length > 0) {
        unplacedHtml = `
            <div class="data-room-subitem">
                <div class="data-room-subitem-header">Other documents (${unplacedDocs.length})</div>
                <div class="data-room-subitem-docs">
                    ${unplacedDocs.map(doc => {
                        const docId = doc.document_id || doc.id || '';
                        const name = doc.filename || 'Untitled';
                        return `<div class="doc-link" data-doc-id="${docId}" data-snippet="" title="View document" role="button" tabindex="0">${name}</div>`;
                    }).join('')}
                </div>
            </div>
        `;
    }

    return `
        <div class="accordion-item">
            <div class="accordion-header" role="button" tabindex="0" aria-expanded="false" onclick="toggleAccordion(this)" onkeydown="handleAccordionKeydown(event)">
                <h3 class="accordion-title">Data Room</h3>
                <span class="accordion-toggle" aria-hidden="true">+</span>
            </div>
            <div class="accordion-content" role="region" aria-hidden="true">
                <div class="accordion-body data-room-body">
                    ${foldersHtml}
                    ${unplacedHtml}
                </div>
            </div>
        </div>
    `;
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

    // Tab view state
    currentView: 'issued',  // 'issued', 'fully-diluted', 'options'
    optionPoolData: null    // Cache option pool data
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
        console.log('[INIT TIMETRAVEL] Checking demo mode:', {
            isDemoModeActive,
            hasDemoData: !!demoDataCache,
            willUseDemoData: isDemoModeActive && !!demoDataCache
        });

        // Demo mode: Use cached data instead of API calls
        if (isDemoModeActive && demoDataCache) {
            // Convert demo timeline to EquityEvent format
            AuditViewState.allEvents = convertDemoTimelineToEvents(
                demoDataCache.timeline,
                demoDataCache.documents
            );
        } else {
            // Production mode: Fetch from API
            const response = await fetch(`/api/audits/${auditId}/events`);
            if (!response.ok) {
                throw new Error(`Failed to fetch events: ${response.statusText}`);
            }
            AuditViewState.allEvents = await response.json();
        }

        if (AuditViewState.allEvents.length === 0) {
            console.error('[TIMETRAVEL] No events generated!');
            // No events found - show empty state
            document.getElementById('horizontal-timeline').innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No events found.</p>';
            document.getElementById('cap-table-container').innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No equity events found in this audit.</p>';
            document.getElementById('event-stream-container').innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No transactions to display.</p>';
            return;
        }

        console.log('[TIMETRAVEL] Events loaded:', AuditViewState.allEvents.length);

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

        // Initialize tab controls
        initCapTableTabs();

    } catch (error) {
        console.error('Failed to initialize time travel:', error);
        alert(`Failed to load audit data: ${error.message}`);
    }
}

/**
 * Initialize tab controls for cap table views
 */
function initCapTableTabs() {
    const tabs = document.querySelectorAll('.cap-table-tab');

    tabs.forEach(tab => {
        tab.addEventListener('click', async () => {
            // Remove active from all tabs
            tabs.forEach(t => t.classList.remove('active'));

            // Add active to clicked tab
            tab.classList.add('active');

            // Update view state
            AuditViewState.currentView = tab.dataset.view;

            // Re-render cap table with new view
            await renderCapTable();
        });
    });
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
                const color = '#334C6A';

                return `
                    <div class="timeline-node-wrapper" style="left: ${positionPercent}%;" data-event-id="${event.id}">
                        <div class="timeline-node" style="background-color: ${color};" title="${event.event_type}: ${event.shareholder_name || 'Company'} - ${new Date(event.event_date).toLocaleDateString()}"></div>
                        ${index % 3 === 0 || index === 0 || index === events.length - 1 ?
                            `<div class="timeline-date-label">${new Date(event.event_date).toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric'})}</div>`
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
function selectTimelineEvent(eventId) {
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

    // Re-render cap table (debounced) and event stream
    debouncedRenderCapTable();
    renderEventStream();
}

/**
 * Render cap table (fetches from API, view-aware)
 */
async function renderCapTable() {
    const dateStr = new Date(AuditViewState.currentDate).toISOString().split('T')[0];
    const container = document.getElementById('cap-table-container');
    const noteContainer = document.getElementById('cap-table-note');

    try {
        let capTableData;
        let optionsData = [];

        // Fetch issued & outstanding cap table
        if (isDemoModeActive && demoDataCache) {
            capTableData = convertDemoCapTable(demoDataCache.cap_table, dateStr);
            // TODO: Add demo options data
        } else {
            const response = await fetch(`/api/audits/${AuditViewState.auditId}/captable?as_of_date=${dateStr}`);
            if (!response.ok) throw new Error(`API error: ${response.statusText}`);
            capTableData = await response.json();

            // Fetch option pool data
            const optionsResponse = await fetch(`/api/audits/${AuditViewState.auditId}/options?as_of_date=${dateStr}`);
            if (optionsResponse.ok) {
                optionsData = await optionsResponse.json();
            }
        }

        // Store for view switching
        AuditViewState.currentCapTable = capTableData;
        AuditViewState.optionPoolData = optionsData;

        // Render based on current view
        switch (AuditViewState.currentView) {
            case 'issued':
                renderIssuedView(capTableData, container, noteContainer);
                break;
            case 'fully-diluted':
                renderFullyDilutedView(capTableData, optionsData, container, noteContainer);
                break;
            case 'options':
                renderOptionsView(optionsData, container, noteContainer);
                break;
        }

    } catch (error) {
        console.error('Failed to render cap table:', error);
        container.innerHTML = `<p style="color: var(--accent); font-size: 0.875rem;">Error loading cap table: ${error.message}</p>`;
    }
}

/**
 * Render Issued & Outstanding view
 */
function renderIssuedView(capTableData, container, noteContainer) {
    noteContainer.textContent = 'Shows current ownership. Options are excluded until exercised.';

    if (capTableData.shareholders.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No shareholders at this date.</p>';
        return;
    }

    const table = document.createElement('table');
    table.className = 'cap-table';

    // Build tbody
    const tbody = document.createElement('tbody');

    capTableData.shareholders.forEach(sh => {
        const row = document.createElement('tr');
        row.className = 'cap-table-row';
        row.setAttribute('data-shareholder', sh.shareholder);

        const color = getShareholderColor(sh.shareholder);

        row.innerHTML = `
            <td>
                <span class="shareholder-dot" style="background-color: ${color};"></span>
                ${sh.shareholder}
                ${sh.compliance_issues && sh.compliance_issues.length > 0 ?
                    `<span style="color: var(--accent); font-size: 0.625rem; margin-left: 4px;" title="${sh.compliance_issues.join('; ')}">⚠</span>`
                    : ''}
            </td>
            <td>${sh.share_class || 'Common'}</td>
            <td class="monospace">${formatNumber(sh.shares)}</td>
            <td class="monospace ownership-number">${formatPercent(sh.ownership_pct)}</td>
        `;

        tbody.appendChild(row);
    });

    // Header
    const thead = document.createElement('thead');
    thead.innerHTML = `
        <tr>
            <th>Shareholder</th>
            <th>Class</th>
            <th>Shares</th>
            <th>Ownership</th>
        </tr>
    `;

    // Footer
    const tfoot = document.createElement('tfoot');
    tfoot.innerHTML = `
        <tr>
            <td colspan="2">Total</td>
            <td>${formatNumber(capTableData.total_shares)}</td>
            <td>100.00%</td>
        </tr>
    `;

    table.appendChild(thead);
    table.appendChild(tbody);
    table.appendChild(tfoot);
    container.innerHTML = '';
    container.appendChild(table);
}

/**
 * Render Fully Diluted view
 */
function renderFullyDilutedView(capTableData, optionsData, container, noteContainer) {
    noteContainer.textContent = 'Shows ownership if all options and convertibles are exercised.';

    // Combine issued shares + options
    const shareholderMap = new Map();

    // Add issued shares
    capTableData.shareholders.forEach(sh => {
        shareholderMap.set(sh.shareholder, {
            shareholder: sh.shareholder,
            share_class: sh.share_class,
            issued_shares: sh.shares,
            option_shares: 0,
            total_shares: sh.shares
        });
    });

    // Add option shares
    optionsData.forEach(opt => {
        const existing = shareholderMap.get(opt.recipient) || {
            shareholder: opt.recipient,
            share_class: 'Common',
            issued_shares: 0,
            option_shares: 0,
            total_shares: 0
        };

        existing.option_shares += opt.shares;
        existing.total_shares = existing.issued_shares + existing.option_shares;
        shareholderMap.set(opt.recipient, existing);
    });

    // Calculate total and percentages
    const allShareholders = Array.from(shareholderMap.values());
    const totalShares = allShareholders.reduce((sum, sh) => sum + sh.total_shares, 0);

    allShareholders.forEach(sh => {
        sh.ownership_pct = (sh.total_shares / totalShares * 100);
    });

    // Sort by ownership desc
    allShareholders.sort((a, b) => b.total_shares - a.total_shares);

    // Render table
    const table = document.createElement('table');
    table.className = 'cap-table';

    const thead = document.createElement('thead');
    thead.innerHTML = `
        <tr>
            <th>Shareholder</th>
            <th>Issued</th>
            <th>Options</th>
            <th>Total</th>
            <th>%</th>
        </tr>
    `;

    const tbody = document.createElement('tbody');
    allShareholders.forEach(sh => {
        const row = document.createElement('tr');
        row.className = 'cap-table-row';
        row.setAttribute('data-shareholder', sh.shareholder);

        const color = getShareholderColor(sh.shareholder);

        row.innerHTML = `
            <td>
                <span class="shareholder-dot" style="background-color: ${color};"></span>
                ${sh.shareholder}
            </td>
            <td class="monospace">${formatNumber(sh.issued_shares)}</td>
            <td class="monospace">${formatNumber(sh.option_shares)}</td>
            <td class="monospace"><strong>${formatNumber(sh.total_shares)}</strong></td>
            <td class="monospace">${sh.ownership_pct.toFixed(2)}%</td>
        `;

        tbody.appendChild(row);
    });

    const tfoot = document.createElement('tfoot');
    tfoot.innerHTML = `
        <tr>
            <td>Total</td>
            <td>${formatNumber(capTableData.total_shares)}</td>
            <td>${formatNumber(optionsData.reduce((sum, opt) => sum + opt.shares, 0))}</td>
            <td>${formatNumber(totalShares)}</td>
            <td>100.00%</td>
        </tr>
    `;

    table.appendChild(thead);
    table.appendChild(tbody);
    table.appendChild(tfoot);
    container.innerHTML = '';
    container.appendChild(table);
}

/**
 * Render Option Pool view
 */
function renderOptionsView(optionsData, container, noteContainer) {
    noteContainer.textContent = 'Shows option grants and unallocated option pool.';

    if (optionsData.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No option grants found.</p>';
        return;
    }

    // Sort by grant date
    optionsData.sort((a, b) => new Date(b.grant_date) - new Date(a.grant_date));

    const table = document.createElement('table');
    table.className = 'cap-table';

    const thead = document.createElement('thead');
    thead.innerHTML = `
        <tr>
            <th>Recipient</th>
            <th>Grant Date</th>
            <th>Shares</th>
            <th>Strike Price</th>
            <th>Vesting</th>
        </tr>
    `;

    const tbody = document.createElement('tbody');
    optionsData.forEach(opt => {
        const row = document.createElement('tr');
        row.className = 'cap-table-row option-grant';

        const color = getShareholderColor(opt.recipient);

        row.innerHTML = `
            <td>
                <span class="shareholder-dot" style="background-color: ${color};"></span>
                ${opt.recipient}
            </td>
            <td class="monospace">${opt.grant_date || 'N/A'}</td>
            <td class="monospace">${formatNumber(opt.shares)}</td>
            <td class="monospace">$${(opt.strike_price || 0).toFixed(4)}</td>
            <td style="font-size: 0.75rem;">${opt.vesting_schedule || 'Not specified'}</td>
        `;

        tbody.appendChild(row);
    });

    const totalOptions = optionsData.reduce((sum, opt) => sum + opt.shares, 0);

    const tfoot = document.createElement('tfoot');
    tfoot.innerHTML = `
        <tr>
            <td colspan="2">Total Granted</td>
            <td>${formatNumber(totalOptions)}</td>
            <td colspan="2"></td>
        </tr>
    `;

    table.appendChild(thead);
    table.appendChild(tbody);
    table.appendChild(tfoot);
    container.innerHTML = '';
    container.appendChild(table);
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
        let shareholderColor = null;
        if (event.shareholder_name) {
            shareholderColor = getShareholderColor(event.shareholder_name);
            card.style.borderLeftColor = shareholderColor;
        }

        const eventDateStr = new Date(event.event_date).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });

        // Format event type for display
        const eventTypeDisplay = event.event_type.replace(/_/g, ' ').toUpperCase();

        // Build details text with colored pill
        let detailsText = '';
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

        const focusY = event.details && typeof event.details.preview_focus_y === 'number'
            ? event.details.preview_focus_y
            : null;
        const previewStyle = focusY !== null ? `object-position: 50% ${focusY * 100}%;` : '';

        card.innerHTML = `
            <div class="event-card-header">
                <span class="event-type">${eventTypeDisplay}</span>
                <span class="event-date">${eventDateStr}</span>
            </div>

            ${event.summary ? `
                <div class="event-summary">${event.summary}</div>
            ` : (detailsText ? `<div class="event-details" style="${shareholderColor ? `border-left: 5px solid ${shareholderColor}; padding-left: 8px;` : ''}">${detailsText}</div>` : '')}

            ${event.preview_image ? `
                <div class="event-preview" data-doc-id="${event.source_doc_id}" title="Click to view full document">
                    <img src="${event.preview_image}"
                         alt="Document preview"
                         class="event-preview-image"
                         loading="lazy"
                         style="${previewStyle}" />
                </div>
            ` : ''}

            ${event.share_delta !== undefined && event.share_delta !== 0 ? `
                <div class="event-metadata">
                    <div class="event-amount">
                        <span class="label">Shares:</span>
                        <span class="value">${event.share_delta > 0 ? '+' : ''}${formatNumber(event.share_delta)}</span>
                    </div>
                    ${event.details && event.details.price_per_share ? `
                        <div class="event-price">
                            <span class="label">Price:</span>
                            <span class="value">$${parseFloat(event.details.price_per_share).toFixed(4)}</span>
                        </div>
                    ` : ''}
                </div>
            ` : ''}

            ${!event.summary && event.source_snippet ? `<div class="source-quote">"${event.source_snippet}"</div>` : ''}
            ${event.compliance_note ? `<div class="compliance-note">${event.compliance_note}</div>` : ''}

            <div class="event-links">
                ${event.source_doc_id ? `<a href="#" class="event-link" data-doc-id="${event.source_doc_id}" data-snippet="${event.source_snippet || ''}" title="View source document">Source Document</a>` : ''}
                ${event.approval_doc_id ? `<a href="#" class="event-link" data-doc-id="${event.approval_doc_id}" data-snippet="${event.approval_snippet || ''}" title="View approval document">Board Approval</a>` : ''}
            </div>
        `;

        // Add hover listeners for cap table interaction
        if (event.shareholder_name) {
            card.addEventListener('mouseenter', () => highlightShareholder(event.shareholder_name, 'enter'));
            card.addEventListener('mouseleave', () => highlightShareholder(event.shareholder_name, 'leave'));
        }

        fragment.appendChild(card);

        // Add click handlers to document links
        const eventLinks = card.querySelectorAll('.event-link');
        eventLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const docId = link.getAttribute('data-doc-id');
                const snippet = link.getAttribute('data-snippet');
                if (docId) {
                    showDocumentModal(AuditViewState.auditId, docId, snippet || null, event.preview_image || null);
                }
            });
        });

        // Add click handler to preview image to expand fullscreen
        const eventPreview = card.querySelector('.event-preview');
        if (eventPreview) {
            eventPreview.addEventListener('click', (e) => {
                e.stopPropagation();
                const docId = eventPreview.getAttribute('data-doc-id');
                if (docId) {
                    showDocumentModal(AuditViewState.auditId, docId, null, event.preview_image || null);
                }
            });
        }
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

// Debounced cap table render to avoid hammering API during rapid timeline clicks
const debouncedRenderCapTable = debounce(() => renderCapTable(), 200);

/**
 * Toggle Home link visibility in the nav
 */
function setHomeLinkVisibility(isVisible) {
    const homeLink = document.getElementById('home-link');
    if (!homeLink) return;
    homeLink.style.display = isVisible ? '' : 'none';
}

// ============================================================================
// PAST AUDITS FEATURE
// ============================================================================

/**
 * Load and display past audits list
 */
async function loadPastAudits() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    const container = document.getElementById('past-audits-accordion');
    const section = document.getElementById('past-audits-section');

    try {
        // Show section
        hideAllSections();
        section.style.display = 'grid';
        setHomeLinkVisibility(true);

        // Show loading state
        container.innerHTML = '<p style="color: var(--text-secondary);">Loading past audits...</p>';

        // Fetch audits
        const response = await fetch('/api/audits');
        if (!response.ok) {
            throw new Error('Failed to fetch audits');
        }

        const audits = await response.json();

        // Render accordion
        if (audits.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary);">No past audits yet. Upload your first document set to get started.</p>';
            return;
        }

        const html = audits.map(audit => {
            const date = new Date(audit.created_at).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });

            // Determine display name
            const displayName = audit.company_name || audit.upload_filename || 'Unknown Company';

            // Status badge
            let statusBadge = '';
            if (audit.status === 'complete') {
                statusBadge = '<span class="status-badge status-complete">✓ Complete</span>';
            } else if (audit.status === 'processing') {
                statusBadge = '<span class="status-badge status-processing">Processing...</span>';
            } else if (audit.status === 'error') {
                statusBadge = '<span class="status-badge status-error">⚠ Failed</span>';
            }

            return `
                <div class="accordion-item audit-item ${audit.status !== 'complete' ? 'disabled' : ''}"
                     data-audit-id="${audit.id}"
                     ${audit.status === 'complete' ? 'onclick="loadAuditById(\'' + audit.id + '\')"' : ''}>
                    <div class="accordion-header">
                        <div class="audit-header-content">
                            <h3 class="accordion-title">${displayName}</h3>
                            <p class="audit-metadata">
                                ${date} • ${audit.document_count} documents ${statusBadge}
                            </p>
                            ${audit.upload_filename && audit.company_name ?
                                `<p class="audit-filename">${audit.upload_filename}</p>` : ''}
                        </div>
                        ${audit.status === 'complete' ? '<span class="accordion-toggle">→</span>' : ''}
                    </div>
                </div>
            `;
        }).join('');

        container.innerHTML = html;

    } catch (error) {
        console.error('Error loading past audits:', error);
        container.innerHTML = '<p style="color: var(--accent);">Error loading past audits. Please refresh the page.</p>';
    }
}

/**
 * Load specific audit by ID and render results
 */
async function loadAuditById(auditId) {
    try {
        // Show progress
        hideAllSections();
        progressSection.style.display = 'flex';
        progressStep.textContent = 'Loading';
        progressText.textContent = 'Loading past audit...';

        // Fetch audit data
        const response = await fetch(`/status/${auditId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch audit');
        }

        const data = await response.json();

        if (data.status === 'complete') {
            // Set current audit ID (for time-travel features)
            currentAuditId = auditId;

            // Hide progress, render results
            progressSection.style.display = 'none';
            await renderResults(data.results);

        } else if (data.status === 'error') {
            throw new Error(data.error || 'Audit failed');
        } else {
            throw new Error('Audit is still processing');
        }

    } catch (error) {
        progressSection.innerHTML = `
            <div role="alert" style="text-align: center; padding: 2rem;">
                <p style="font-family: var(--font-grotesk); font-size: var(--text-lg); margin-bottom: 0.5rem;">Failed to load audit</p>
                <p style="color: var(--gray-600); margin-bottom: 1.5rem;">${escapeHtml(error.message)}</p>
                <button class="btn btn-secondary" onclick="loadPastAudits()" style="margin-right: 0.5rem;">Back to Audits</button>
                <button class="btn btn-primary" onclick="loadAuditById('${auditId}')">Retry</button>
            </div>
        `;
    }
}

/**
 * Hide all main sections
 */
function hideAllSections() {
    uploadSection.style.display = 'none';
    progressSection.style.display = 'none';
    resultsSection.style.display = 'none';
    document.getElementById('past-audits-section').style.display = 'none';
    document.getElementById('upload-header').style.display = 'none';
}

/**
 * Show upload page
 */
function showUploadPage() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    hideAllSections();
    uploadSection.style.display = 'block';
    document.getElementById('upload-header').style.display = 'block';
    setHomeLinkVisibility(false);

    // Restore progress section HTML if it was replaced by error message
    progressSection.innerHTML = `
        <div class="loader-container">
            <div class="loader"></div><div class="loader"></div><div class="loader"></div>
        </div>
        <p id="progress-step" class="progress-step">Processing</p>
        <p id="progress-text" class="progress-text" aria-live="polite" aria-busy="true">Starting...</p>
    `;
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

        // Arrow keys: Navigate timeline (only when timeline is visible)
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            const timelineEl = document.querySelector('.horizontal-timeline');
            const isTimelineVisible = timelineEl && timelineEl.offsetParent !== null;
            if (isTimelineVisible && AuditViewState.allEvents && AuditViewState.allEvents.length > 0) {
                e.preventDefault();
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

    // Navigation event handlers
    const homeLink = document.getElementById('home-link');
    if (homeLink) {
        homeLink.addEventListener('click', (e) => {
            e.preventDefault();
            showUploadPage();
        });
    }

    const pastAuditsLink = document.getElementById('past-audits-link');
    if (pastAuditsLink) {
        pastAuditsLink.addEventListener('click', (e) => {
            e.preventDefault();
            loadPastAudits();
        });
    }

    // Logout handler
    const logoutLink = document.getElementById('logout-link');
    if (logoutLink) {
        logoutLink.addEventListener('click', async (e) => {
            e.preventDefault();

            try {
                const response = await fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                if (response.ok) {
                    // Clear any local state
                    currentAuditId = null;
                    if (pollInterval) {
                        clearInterval(pollInterval);
                    }

                    // Redirect to landing page
                    window.location.href = '/';
                } else {
                    console.error('Logout failed:', response.statusText);
                    alert('Logout failed. Please try again.');
                }
            } catch (error) {
                console.error('Logout error:', error);
                alert('Network error during logout. Please try again.');
            }
        });
    }

    // Logo click handler - navigate to home
    const navLogo = document.querySelector('.nav-logo');
    if (navLogo) {
        navLogo.style.cursor = 'pointer';  // Visual affordance
        navLogo.addEventListener('click', (e) => {
            e.preventDefault();
            showUploadPage();
        });
    }

    // On initial load we're on the home screen, so hide the redundant Home nav item
    setHomeLinkVisibility(false);
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
async function showDocumentModal(auditId, docId, snippetToHighlight = null, previewImage = null) {
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
        let doc;

        // Demo mode: Find document in cached data
        if (isDemoModeActive && demoDataCache) {
            // Find document by filename (docId in demo is often a filename)
            doc = demoDataCache.documents.find(d =>
                d.filename === docId ||
                d.filename.includes(docId) ||
                docId.includes(d.filename)
            );

            if (!doc) {
                throw new Error('Document not found in demo data');
            }

            // Add mock full_text if not present
            if (!doc.full_text) {
                doc.full_text = `[Demo Document: ${doc.filename}]\n\n` +
                    `Classification: ${doc.classification}\n\n` +
                    `This is a demonstration document. In production, the full document text ` +
                    `would be displayed here with searchable content and highlighted snippets.\n\n` +
                    `Extracted Data:\n${JSON.stringify(doc.extracted_data, null, 2)}`;
            }
        } else {
            // Production mode: Fetch from API
            const response = await fetch(`/api/audits/${auditId}/documents/${docId}`);
            if (!response.ok) {
                throw new Error(`Failed to fetch document: ${response.statusText}`);
            }
            doc = await response.json();
        }

        // Update modal content
        modalFilename.textContent = doc.filename || 'Document';
        modalClassification.textContent = doc.classification || 'Unknown Document Type';

        // If we have a preview image, show that instead of raw text
        if (previewImage) {
            modalContent.innerHTML = `
                <img src="${previewImage}" alt="Document preview"
                     style="width: 100%; max-height: 70vh; object-fit: contain; background: var(--gray-50);" />
            `;
        } else {
            let fullText = doc.full_text || 'No text content available';

            // Highlight snippet if provided — escape first, then insert mark tags
            if (snippetToHighlight && fullText.includes(snippetToHighlight)) {
                const escapedText = escapeHtml(fullText);
                const escapedSnippet = escapeHtml(snippetToHighlight);
                modalContent.innerHTML = escapedText.replace(
                    escapedSnippet,
                    `<mark>${escapedSnippet}</mark>`
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
        }

        // Lock body scroll and trap focus
        document.body.style.overflow = 'hidden';
        _trapFocusInModal(modal);

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
    document.body.style.overflow = '';
    _removeFocusTrap();
}

// Focus trap state
let _focusTrapHandler = null;

function _trapFocusInModal(modal) {
    _removeFocusTrap();
    const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    _focusTrapHandler = function(e) {
        if (e.key !== 'Tab') return;
        const focusable = modal.querySelectorAll(focusableSelector);
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey) {
            if (document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else {
            if (document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
    };
    document.addEventListener('keydown', _focusTrapHandler);
    // Focus the close button
    const closeBtn = modal.querySelector('.modal-close');
    if (closeBtn) closeBtn.focus();
}

function _removeFocusTrap() {
    if (_focusTrapHandler) {
        document.removeEventListener('keydown', _focusTrapHandler);
        _focusTrapHandler = null;
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Toggle section collapse/expand
 */
function toggleSection(sectionId) {
    const title = document.querySelector(`[onclick="toggleSection('${sectionId}')"]`);
    const content = document.getElementById(`${sectionId}-filters`);

    if (title && content) {
        title.classList.toggle('collapsed');
        content.classList.toggle('hidden');
    }
}

/**
 * Load download previews and wire up download buttons
 * @param {string} auditId - UUID of the audit
 */
async function loadDownloadPreviews(auditId) {
    try {
        // Fetch Minute Book preview
        const minuteBookRes = await fetch(`/api/audits/${auditId}/preview/minute-book`);
        const minuteBookData = await minuteBookRes.json();
        const minuteBookPreview = document.getElementById('minute-book-preview');
        if (minuteBookPreview) {
            minuteBookPreview.textContent = minuteBookData.preview || 'Preview unavailable';
        }

        // Fetch Issues preview
        const issuesRes = await fetch(`/api/audits/${auditId}/preview/issues`);
        const issuesData = await issuesRes.json();
        const issuesPreview = document.getElementById('issues-preview');
        if (issuesPreview) {
            issuesPreview.textContent = issuesData.preview || 'Preview unavailable';
        }

        // Attach download handlers and enable buttons
        const downloadMinuteBookBtn = document.getElementById('download-minute-book');
        if (downloadMinuteBookBtn) {
            downloadMinuteBookBtn.onclick = () => {
                window.location.href = `/api/audits/${auditId}/download/minute-book`;
            };
            downloadMinuteBookBtn.disabled = false;
        }

        const downloadIssuesBtn = document.getElementById('download-issues');
        if (downloadIssuesBtn) {
            downloadIssuesBtn.onclick = () => {
                window.location.href = `/api/audits/${auditId}/download/issues`;
            };
            downloadIssuesBtn.disabled = false;
        }

    } catch (error) {
        console.error('Failed to load download previews:', error);
        const minuteBookPreview = document.getElementById('minute-book-preview');
        const issuesPreview = document.getElementById('issues-preview');
        if (minuteBookPreview) minuteBookPreview.textContent = 'Preview unavailable';
        if (issuesPreview) issuesPreview.textContent = 'Preview unavailable';
    }
}

// ============================================================================
// SCROLL REVEAL ANIMATIONS
// ============================================================================

/**
 * Initialize scroll reveal animations using IntersectionObserver
 */
function initScrollReveal() {
    const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.scroll-reveal').forEach(el => {
        revealObserver.observe(el);
    });
}

// Initialize scroll reveal on page load
document.addEventListener('DOMContentLoaded', initScrollReveal);

// ============================================================================
// HERO IMAGE SCROLL MOTION
// ============================================================================

let heroMotionUpdate = null;
let heroMotionHandler = null;
let heroMotionRaf = null;
let heroMotionTarget = 0;
let heroMotionCurrent = 0;

/**
 * Animate the hero image based on scroll position.
 */
function initHeroScrollMotion() {
    const heroSection = document.querySelector('.hero-section');
    const heroVisual = document.querySelector('.hero-visual');

    if (!heroSection || !heroVisual) return;

    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduceMotion) {
        heroVisual.style.setProperty('--hero-x', '0px');
        heroVisual.style.setProperty('--hero-y', '0px');
        heroVisual.style.setProperty('--hero-z', '0px');
        heroVisual.style.setProperty('--hero-scale', '1');
        return;
    }

    const applyHeroMotion = (progress) => {
        const wave = Math.sin(progress * Math.PI);
        const scale = 1 + (0.25 * wave);
        const translateY = 12 * wave;
        const translateX = -8 * wave;
        const translateZ = 120 * wave;

        heroVisual.style.setProperty('--hero-x', `${translateX.toFixed(2)}px`);
        heroVisual.style.setProperty('--hero-y', `${translateY.toFixed(2)}px`);
        heroVisual.style.setProperty('--hero-z', `${translateZ.toFixed(2)}px`);
        heroVisual.style.setProperty('--hero-scale', scale.toFixed(3));
    };

    const tick = () => {
        heroMotionCurrent += (heroMotionTarget - heroMotionCurrent) * 0.12;
        applyHeroMotion(heroMotionCurrent);

        if (Math.abs(heroMotionTarget - heroMotionCurrent) > 0.001) {
            heroMotionRaf = window.requestAnimationFrame(tick);
        } else {
            heroMotionCurrent = heroMotionTarget;
            applyHeroMotion(heroMotionCurrent);
            heroMotionRaf = null;
        }
    };

    heroMotionUpdate = () => {
        const scrollY = window.scrollY || window.pageYOffset;
        const heroTop = heroSection.offsetTop;
        const heroHeight = heroSection.offsetHeight;
        const range = Math.max(360, Math.min(600, heroHeight));

        heroMotionTarget = clamp((scrollY - heroTop) / range, 0, 1);

        if (!heroMotionRaf) {
            heroMotionRaf = window.requestAnimationFrame(tick);
        }
    };

    if (!heroMotionHandler) {
        let heroInView = false;

        // Only run scroll animation when hero is visible
        const observer = new IntersectionObserver((entries) => {
            heroInView = entries[0].isIntersecting;
        }, { threshold: 0 });
        observer.observe(heroSection);

        heroMotionHandler = () => {
            if (heroInView && heroMotionUpdate) heroMotionUpdate();
        };

        window.addEventListener('scroll', heroMotionHandler, { passive: true });
        window.addEventListener('resize', heroMotionHandler);
    }

    heroMotionHandler();
}

// Hero motion is initialized in renderResults() when results are displayed
