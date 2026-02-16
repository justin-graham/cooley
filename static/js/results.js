/** Results rendering — company header, document accordion, data room. */

import { escapeHtml, escapeAttr } from './utils.js';
import { appState, setHomeLinkVisibility, showUiNotice } from './state.js';
import { initTimeTravel } from './time-travel.js';
import { showDocumentModal } from './modal.js';
import { AuditViewState } from './time-travel.js';
import { loadDownloadPreviews } from './downloads.js';
import { initHeroScrollMotion, initScrollReveal } from './scroll.js';

const DATA_ROOM_MAPPING = [
    { title: '1. Authority and Governance', subitems: [
        { label: 'Certificate of Incorporation (all versions)', categories: ['Charter Document'] },
        { label: 'Board consents approving equity plans, grants, SAFEs, notes, and share increases', categories: ['Board/Shareholder Minutes'] },
        { label: 'Stockholder consents approving equity plans, charter amendments, and financings', categories: [] },
    ]},
    { title: '2. Equity', subitems: [
        { label: 'Investors\u2019 Rights, Voting, and ROFR / Co-Sale Agreements', categories: [] },
        { label: 'Equity Incentive Plan, amendments, and share reserve changes', categories: ['Equity Incentive Plan'] },
        { label: 'Founder and investor stock purchase agreements', categories: ['Stock Purchase Agreement'] },
        { label: 'Option, RSU, and warrant agreements', categories: ['Option Grant Agreement'] },
        { label: 'SAFEs, convertible notes, and side letters', categories: ['SAFE', 'Convertible Note'] },
        { label: 'Option exercise notices and payment records', categories: [] },
        { label: 'Share repurchases, forfeitures, and cancellations', categories: ['Share Repurchase Agreement'] },
        { label: 'Current and historical cap tables', categories: ['Financial Statement', 'Stock Certificate'] },
        { label: 'Fully diluted calculations and waterfalls', categories: [] },
    ]},
    { title: '3. Employment and Advisors', subitems: [
        { label: 'Employee offer letters and employment agreements', categories: ['Employment Agreement'] },
        { label: 'Contractor and advisor agreements', categories: [] },
        { label: 'Equity grants tied to each individual', categories: [] },
        { label: 'Vesting schedules and acceleration provisions', categories: [] },
    ]},
    { title: '4. Intellectual Property Ownership', subitems: [
        { label: 'Founder, employee, contractor, and advisor IP assignment agreements', categories: ['IP/Proprietary Info Agreement'] },
        { label: 'Confidentiality agreements', categories: [] },
        { label: 'Inbound IP licenses and open source disclosures', categories: [] },
        { label: 'University or prior employer IP agreements', categories: [] },
        { label: 'IP carve-outs and side letters', categories: [] },
    ]},
    { title: '5. Securities Law Compliance', subitems: [
        { label: 'Rule 701 disclosures and financials', categories: ['Corporate Records'] },
        { label: 'Form D filings and investor questionnaires', categories: ['83(b) Election'] },
    ]},
    { title: '6. Exceptions and Risk Items', subitems: [
        { label: 'Missing approvals or undocumented issuances', categories: [] },
        { label: 'Disputed ownership', categories: [] },
        { label: 'Unassigned or encumbered IP', categories: [] },
        { label: 'Non-standard equity or side arrangements', categories: ['Other', 'Indemnification Agreement'] },
    ]},
];

export async function renderResults(results) {
    document.getElementById('upload-header').style.display = 'none';
    setHomeLinkVisibility(true);
    document.getElementById('results').style.display = 'block';

    renderCompanyHeader(results);
    initHeroScrollMotion();

    const issues = results.compliance_issues || results.issues || [];
    renderDocumentAccordion(results.documents || [], results.company_name, results.failed_documents || [], issues);

    // Update summary counts
    const docs = results.documents || [];
    const setCount = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    setCount('doc-count', docs.length);
    setCount('category-count', new Set(docs.map(d => d.category || d.classification || 'Other')).size);
    setCount('issues-count', issues.length);
    setCount('failed-count', (results.failed_documents || []).length);

    const ctaName = document.getElementById('cta-company-name');
    if (ctaName && results.company_name) ctaName.textContent = results.company_name;

    // Initialize time-travel
    try {
        await initTimeTravel(appState.currentAuditId);
    } catch (error) {
        const msg = error.message || '';
        let capMsg, eventMsg;
        if (msg.includes('401') || msg.includes('403')) {
            capMsg = eventMsg = 'Session expired. Please log in again.';
        } else if (msg.includes('404') || msg.includes('No equity events')) {
            capMsg = 'No equity events found. Check the compliance issues section.';
            eventMsg = 'No equity events found.';
        } else {
            capMsg = eventMsg = 'Failed to load data. Try refreshing the page.';
        }
        document.getElementById('cap-table-container').innerHTML = `<p style="color: var(--accent); padding: 1rem;">${escapeHtml(capMsg)}</p>`;
        document.getElementById('event-stream-container').innerHTML = `<p style="color: var(--accent); padding: 1rem;">${escapeHtml(eventMsg)}</p>`;
    }

    loadDownloadPreviews(appState.currentAuditId);
    document.getElementById('results').scrollIntoView({ behavior: 'smooth' });
}

function renderCompanyHeader(results) {
    const container = document.querySelector('.hero-left .company-header-content');
    const docs = results.documents || [];
    const timeline = results.timeline || [];
    const dates = timeline.map(e => e.date).filter(Boolean).sort();

    const fmt = (d) => {
        if (!d || d === 'N/A') return 'N/A';
        return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    };
    const dateRange = dates.length > 1 ? `${fmt(dates[0])} - ${fmt(dates[dates.length - 1])}` : fmt(dates[0]);

    container.innerHTML = `
        <h1 class="company-name scroll-reveal">${results.company_name ? escapeHtml(results.company_name) : '<span style="color: var(--gray-400);">Company name not extracted</span>'}</h1>
        <p class="company-period scroll-reveal" data-delay="1">${dateRange}</p>
        <div class="company-stats scroll-reveal" data-delay="1">
            <div class="company-stat"><span class="company-stat-label">Documents</span><span class="company-stat-value">${docs.length}</span></div>
            <div class="company-stat"><span class="company-stat-label">Events</span><span class="company-stat-value">${timeline.length}</span></div>
            <div class="company-stat"><span class="company-stat-label">Period</span><span class="company-stat-value">${dateRange}</span></div>
        </div>
    `;
    initScrollReveal();
}

function renderDocumentAccordion(documents, companyName, failedDocuments, complianceIssues) {
    const container = document.getElementById('document-accordion');
    const nameSpan = document.getElementById('company-name-breakdown');
    if (nameSpan && companyName) nameSpan.textContent = companyName;

    const hasCritical = complianceIssues.some(i => i.severity && i.severity.toUpperCase() === 'CRITICAL');
    const issueCount = complianceIssues.length;

    const complianceItem = `
        <div class="accordion-item${hasCritical ? ' active' : ''}">
            <div class="accordion-header" role="button" tabindex="0" aria-expanded="${hasCritical}" onclick="window._toggleAccordion(this)" onkeydown="window._handleAccordionKeydown(event)">
                <h3 class="accordion-title">Compliance Issues${issueCount > 0 ? ` (${issueCount})` : ''}</h3>
                <span class="accordion-toggle" aria-hidden="true">${hasCritical ? '-' : '+'}</span>
            </div>
            <div class="accordion-content" role="region" aria-hidden="${!hasCritical}" ${hasCritical ? 'style="max-height: 2000px;"' : ''}>
                <div class="accordion-body">
                    ${complianceIssues.length
                        ? complianceIssues.map(issue => {
                            if (typeof issue === 'string') return `<div class="issue-note spacer">${escapeHtml(issue)}</div>`;
                            const sev = issue.severity ? issue.severity.toUpperCase() : 'ISSUE';
                            const desc = issue.description || issue.message || JSON.stringify(issue);
                            const cls = sev === 'CRITICAL' ? 'issue-critical' : sev === 'WARNING' ? 'issue-warning' : 'issue-note';
                            return `<div class="${cls} spacer"><strong>${escapeHtml(sev)}:</strong> ${escapeHtml(desc)}</div>`;
                          }).join('')
                        : 'No compliance issues.'}
                </div>
            </div>
        </div>`;

    const failedItem = `
        <div class="accordion-item">
            <div class="accordion-header" role="button" tabindex="0" aria-expanded="false" onclick="window._toggleAccordion(this)" onkeydown="window._handleAccordionKeydown(event)">
                <h3 class="accordion-title">Failed Documents</h3>
                <span class="accordion-toggle" aria-hidden="true">+</span>
            </div>
            <div class="accordion-content" role="region" aria-hidden="true">
                <div class="accordion-body">
                    ${failedDocuments.length
                        ? failedDocuments.map(doc => `<div>${escapeHtml(doc.filename || String(doc))}</div>`).join('')
                        : 'No failed documents.'}
                </div>
            </div>
        </div>`;

    container.innerHTML = complianceItem + failedItem + buildDataRoomItem(documents)
        || '<p style="text-align: center; color: var(--text-secondary);">No documents to display</p>';

    // Wire up document links
    container.querySelectorAll('.doc-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.stopPropagation();
            const docId = link.getAttribute('data-doc-id');
            if (docId) showDocumentModal(AuditViewState.auditId, docId, link.getAttribute('data-snippet') || null);
        });
        // Keyboard: Enter/Space opens document
        link.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                link.click();
            }
        });
    });
}

function buildDataRoomItem(documents) {
    const docsByCategory = {};
    documents.forEach(doc => {
        const cat = doc.category || doc.classification || 'Other';
        (docsByCategory[cat] = docsByCategory[cat] || []).push(doc);
    });

    const placedCategories = new Set();

    const foldersHtml = DATA_ROOM_MAPPING.map(folder => {
        let count = 0;
        const subs = folder.subitems.map(sub => {
            const docs = [];
            sub.categories.forEach(cat => { placedCategories.add(cat); if (docsByCategory[cat]) docs.push(...docsByCategory[cat]); });
            count += docs.length;
            if (!docs.length) return `<div class="data-room-subitem"><div class="data-room-subitem-header">${escapeHtml(sub.label)}</div><div class="data-room-subitem-empty">No documents</div></div>`;
            return `<div class="data-room-subitem"><div class="data-room-subitem-header">${escapeHtml(sub.label)} (${docs.length})</div><div class="data-room-subitem-docs">${docs.map(d => `<div class="doc-link" data-doc-id="${escapeAttr(d.document_id || d.id || '')}" data-snippet="" title="View document" role="button" tabindex="0">${escapeHtml(d.filename || 'Untitled')}</div>`).join('')}</div></div>`;
        }).join('');
        return `<div class="data-room-folder"><div class="data-room-folder-header" onclick="window._toggleDataRoomFolder(this)" onkeydown="window._handleDataRoomFolderKeydown(event)" role="button" tabindex="0"><span class="data-room-folder-title">${escapeHtml(folder.title)}</span><span class="data-room-folder-count">${count} doc${count !== 1 ? 's' : ''}</span><span class="data-room-folder-toggle">+</span></div><div class="data-room-folder-content">${subs}</div></div>`;
    }).join('');

    // Unplaced docs
    const unplaced = [];
    Object.keys(docsByCategory).forEach(cat => { if (!placedCategories.has(cat)) unplaced.push(...docsByCategory[cat]); });
    const unplacedHtml = unplaced.length
        ? `<div class="data-room-subitem"><div class="data-room-subitem-header">Other documents (${unplaced.length})</div><div class="data-room-subitem-docs">${unplaced.map(d => `<div class="doc-link" data-doc-id="${escapeAttr(d.document_id || d.id || '')}" data-snippet="" title="View document" role="button" tabindex="0">${escapeHtml(d.filename || 'Untitled')}</div>`).join('')}</div></div>`
        : '';

    return `<div class="accordion-item"><div class="accordion-header" role="button" tabindex="0" aria-expanded="false" onclick="window._toggleAccordion(this)" onkeydown="window._handleAccordionKeydown(event)"><h3 class="accordion-title">Data Room</h3><span class="accordion-toggle" aria-hidden="true">+</span></div><div class="accordion-content" role="region" aria-hidden="true"><div class="accordion-body data-room-body">${foldersHtml}${unplacedHtml}</div></div></div>`;
}

// Accordion helpers — exposed to window in app.js
export function toggleAccordion(headerElement) {
    const item = headerElement.parentElement;
    const wasActive = item.classList.contains('active');
    document.querySelectorAll('.accordion-item').forEach(el => {
        el.classList.remove('active');
        const h = el.querySelector('.accordion-header');
        const c = el.querySelector('.accordion-content');
        if (h) h.setAttribute('aria-expanded', 'false');
        if (c) c.setAttribute('aria-hidden', 'true');
    });
    if (!wasActive) {
        item.classList.add('active');
        headerElement.setAttribute('aria-expanded', 'true');
        const content = item.querySelector('.accordion-content');
        if (content) content.setAttribute('aria-hidden', 'false');
    }
}

export function handleAccordionKeydown(event) {
    if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleAccordion(event.currentTarget || event.target);
    }
}

export function toggleDataRoomFolder(headerElement) {
    headerElement.parentElement.classList.toggle('open');
}

export function handleDataRoomFolderKeydown(event) {
    if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleDataRoomFolder(event.currentTarget || event.target);
    }
}
