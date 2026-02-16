/** Time-travel cap table view — timeline, cap table, event stream. */

import { escapeHtml, escapeAttr, formatNumber, formatPercent, sanitizeImageSrc, debounce } from './utils.js';
import { appState, showUiNotice } from './state.js';
import { api } from './api.js';
import { showDocumentModal } from './modal.js';

export const AuditViewState = {
    auditId: null,
    allEvents: [],
    dateRange: { min: null, max: null },
    currentDate: null,
    currentCapTable: null,
    currentView: 'issued',
    optionPoolData: null,
};

const SHAREHOLDER_COLORS = [
    '#60A5FA', '#34D399', '#A78BFA', '#FB923C',
    '#2DD4BF', '#F472B6', '#FBBF24', '#818CF8',
];

function hashStringToIndex(str, len) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash = hash & hash;
    }
    return Math.abs(hash) % len;
}

function getShareholderColor(name) {
    return name ? SHAREHOLDER_COLORS[hashStringToIndex(name, SHAREHOLDER_COLORS.length)] : SHAREHOLDER_COLORS[0];
}

export async function initTimeTravel(auditId) {
    AuditViewState.auditId = auditId;

    if (appState.isDemoModeActive && appState.demoDataCache) {
        AuditViewState.allEvents = convertDemoTimelineToEvents(appState.demoDataCache.timeline);
    } else {
        const events = await api.getEvents(auditId);
        if (!Array.isArray(events)) throw new Error('Invalid response: expected array of events');
        AuditViewState.allEvents = events.filter(e => e.event_date && e.event_type);
    }

    if (AuditViewState.allEvents.length === 0) {
        const emptyMsg = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No events found.</p>';
        document.getElementById('horizontal-timeline').innerHTML = emptyMsg;
        document.getElementById('cap-table-container').innerHTML = emptyMsg;
        document.getElementById('event-stream-container').innerHTML = emptyMsg;
        return;
    }

    const dates = AuditViewState.allEvents.map(e => new Date(e.event_date));
    AuditViewState.dateRange.min = Math.min(...dates);
    AuditViewState.dateRange.max = Math.max(...dates);

    const latestEvent = AuditViewState.allEvents[AuditViewState.allEvents.length - 1];
    AuditViewState.currentDate = new Date(latestEvent.event_date).getTime();

    renderHorizontalTimeline();
    await selectTimelineEvent(latestEvent.id);
    initCapTableTabs();
}

function initCapTableTabs() {
    document.querySelectorAll('.cap-table-tab').forEach(tab => {
        tab.addEventListener('click', async () => {
            document.querySelectorAll('.cap-table-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            AuditViewState.currentView = tab.dataset.view;
            await renderCapTable();
        });
    });
}

function renderHorizontalTimeline() {
    const container = document.getElementById('horizontal-timeline');
    const dateDisplay = document.getElementById('timeline-date-display');
    const events = AuditViewState.allEvents;

    if (!events.length) { container.innerHTML = '<p style="color: var(--text-secondary);">No events.</p>'; return; }

    container.innerHTML = `
        <div class="timeline-track">
            <div class="timeline-line"></div>
            <div class="timeline-line-active"></div>
            ${events.map((event, i) => {
                const pad = 4, usable = 100 - 2 * pad;
                const pos = pad + (events.length > 1 ? (i / (events.length - 1)) * usable : usable / 2);
                return `<div class="timeline-node-wrapper" style="left: ${pos}%;" data-event-id="${escapeAttr(event.id || '')}" data-index="${i}">
                    <div class="timeline-node" title="${escapeAttr((event.event_type || 'event') + ': ' + (event.shareholder_name || 'Company'))}"></div>
                    ${i % 3 === 0 || i === 0 || i === events.length - 1 ? `<div class="timeline-date-label">${new Date(event.event_date).toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric'})}</div>` : ''}
                </div>`;
            }).join('')}
        </div>`;

    container.querySelectorAll('.timeline-node-wrapper').forEach(n => {
        n.addEventListener('click', () => selectTimelineEvent(n.getAttribute('data-event-id')));
    });

    const last = events[events.length - 1];
    dateDisplay.textContent = `Viewing: ${new Date(last.event_date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}`;
}

function selectTimelineEvent(eventId) {
    const event = AuditViewState.allEvents.find(e => e.id === eventId);
    if (!event) return;

    AuditViewState.currentDate = new Date(event.event_date).getTime();

    const allNodes = document.querySelectorAll('.timeline-node-wrapper');
    let selectedLeft = 0;
    allNodes.forEach(node => {
        const tick = node.querySelector('.timeline-node');
        const isSelected = node.getAttribute('data-event-id') === eventId;
        const idx = parseInt(node.getAttribute('data-index'));
        const selIdx = Array.from(allNodes).findIndex(n => n.getAttribute('data-event-id') === eventId);
        tick.classList.toggle('selected', isSelected);
        tick.classList.toggle('before-selected', idx < selIdx);
        if (isSelected) selectedLeft = node.style.left;
    });

    const activeLine = document.querySelector('.timeline-line-active');
    if (activeLine) activeLine.style.width = selectedLeft;

    document.getElementById('timeline-date-display').textContent =
        `Viewing: ${new Date(event.event_date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}`;

    debouncedRenderCapTable();
    renderEventStream();
}

// Navigate timeline with arrow keys (called from app.js)
export function navigateTimeline(direction) {
    if (!AuditViewState.allEvents.length) return;
    const idx = AuditViewState.allEvents.findIndex(e => new Date(e.event_date).getTime() === AuditViewState.currentDate);
    const newIdx = idx + direction;
    if (newIdx >= 0 && newIdx < AuditViewState.allEvents.length) {
        selectTimelineEvent(AuditViewState.allEvents[newIdx].id);
    }
}

async function renderCapTable() {
    const dateStr = new Date(AuditViewState.currentDate).toISOString().split('T')[0];
    const container = document.getElementById('cap-table-container');
    const noteContainer = document.getElementById('cap-table-note');

    try {
        let capData, optionsData = [];
        if (appState.isDemoModeActive && appState.demoDataCache) {
            capData = convertDemoCapTable(appState.demoDataCache.cap_table, dateStr);
        } else {
            capData = await api.getCapTable(AuditViewState.auditId, dateStr);
            try { optionsData = await api.getOptions(AuditViewState.auditId, dateStr); } catch {}
        }
        AuditViewState.currentCapTable = capData;
        AuditViewState.optionPoolData = optionsData;

        if (AuditViewState.currentView === 'issued') renderIssuedView(capData, container, noteContainer);
        else if (AuditViewState.currentView === 'fully-diluted') renderFullyDilutedView(capData, optionsData, container, noteContainer);
        else if (AuditViewState.currentView === 'options') renderOptionsView(optionsData, container, noteContainer);
    } catch (error) {
        container.innerHTML = `<p style="color: var(--accent); font-size: 0.875rem;">Error loading cap table: ${escapeHtml(error.message)}</p>`;
    }
}

const debouncedRenderCapTable = debounce(() => renderCapTable(), 200);

function renderIssuedView(data, container, note) {
    note.textContent = 'Shows current ownership. Options are excluded until exercised.';
    if (!data.shareholders.length) { container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No shareholders at this date.</p>'; return; }

    container.innerHTML = '';
    const table = buildCapTable(
        ['Shareholder', 'Class', 'Shares', 'Ownership'],
        data.shareholders.map(sh => shareholderRow(sh, [
            escapeHtml(sh.share_class || 'Common'),
            `<span class="monospace">${formatNumber(sh.shares)}</span>`,
            `<span class="monospace ownership-number">${formatPercent(sh.ownership_pct)}</span>`,
        ], sh.compliance_issues)),
        `<td colspan="2">Total</td><td>${formatNumber(data.total_shares)}</td><td>100.00%</td>`
    );
    container.appendChild(table);
}

function renderFullyDilutedView(capData, optionsData, container, note) {
    note.textContent = 'Shows ownership if all option grants are exercised. Convertibles are not currently modeled.';
    const map = new Map();
    capData.shareholders.forEach(sh => map.set(sh.shareholder, { shareholder: sh.shareholder, share_class: sh.share_class, issued: sh.shares, options: 0, total: sh.shares }));
    optionsData.forEach(opt => {
        const e = map.get(opt.recipient) || { shareholder: opt.recipient, share_class: 'Common', issued: 0, options: 0, total: 0 };
        e.options += opt.shares;
        e.total = e.issued + e.options;
        map.set(opt.recipient, e);
    });
    const all = Array.from(map.values());
    const totalShares = all.reduce((s, x) => s + x.total, 0);
    all.forEach(x => x.pct = x.total / totalShares * 100);
    all.sort((a, b) => b.total - a.total);

    container.innerHTML = '';
    const table = buildCapTable(
        ['Shareholder', 'Issued', 'Options', 'Total', '%'],
        all.map(sh => shareholderRow(sh, [
            `<span class="monospace">${formatNumber(sh.issued)}</span>`,
            `<span class="monospace">${formatNumber(sh.options)}</span>`,
            `<span class="monospace"><strong>${formatNumber(sh.total)}</strong></span>`,
            `<span class="monospace">${sh.pct.toFixed(2)}%</span>`,
        ])),
        `<td>Total</td><td>${formatNumber(capData.total_shares)}</td><td>${formatNumber(optionsData.reduce((s, o) => s + o.shares, 0))}</td><td>${formatNumber(totalShares)}</td><td>100.00%</td>`
    );
    container.appendChild(table);
}

function renderOptionsView(optionsData, container, note) {
    note.textContent = 'Shows option grants and unallocated option pool.';
    if (!optionsData.length) { container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No option grants found.</p>'; return; }
    optionsData.sort((a, b) => new Date(b.grant_date) - new Date(a.grant_date));

    container.innerHTML = '';
    const table = buildCapTable(
        ['Recipient', 'Grant Date', 'Shares', 'Strike Price', 'Vesting'],
        optionsData.map(opt => {
            const color = getShareholderColor(opt.recipient);
            const row = document.createElement('tr');
            row.className = 'cap-table-row option-grant';
            row.innerHTML = `<td><span class="shareholder-dot" style="background-color: ${color};"></span>${escapeHtml(opt.recipient)}</td>
                <td class="monospace">${escapeHtml(opt.grant_date || 'N/A')}</td>
                <td class="monospace">${formatNumber(opt.shares)}</td>
                <td class="monospace">$${(opt.strike_price || 0).toFixed(4)}</td>
                <td style="font-size: 0.75rem;">${escapeHtml(opt.vesting_schedule || 'Not specified')}</td>`;
            return row;
        }),
        `<td colspan="2">Total Granted</td><td>${formatNumber(optionsData.reduce((s, o) => s + o.shares, 0))}</td><td colspan="2"></td>`
    );
    container.appendChild(table);
}

// Shared cap table builder
function buildCapTable(headers, bodyRows, footerHtml) {
    const table = document.createElement('table');
    table.className = 'cap-table';
    const thead = document.createElement('thead');
    thead.innerHTML = `<tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>`;
    const tbody = document.createElement('tbody');
    bodyRows.forEach(row => tbody.appendChild(row instanceof HTMLElement ? row : row));
    const tfoot = document.createElement('tfoot');
    tfoot.innerHTML = `<tr>${footerHtml}</tr>`;
    table.append(thead, tbody, tfoot);
    return table;
}

function shareholderRow(sh, cells, complianceIssues) {
    const row = document.createElement('tr');
    row.className = 'cap-table-row';
    row.setAttribute('data-shareholder', sh.shareholder);
    const color = getShareholderColor(sh.shareholder);
    const warn = complianceIssues && complianceIssues.length
        ? `<span style="color: var(--accent); font-size: 0.625rem; margin-left: 4px;" title="${escapeHtml(complianceIssues.join('; '))}">⚠</span>` : '';
    row.innerHTML = `<td><span class="shareholder-dot" style="background-color: ${color};"></span>${escapeHtml(sh.shareholder)}${warn}</td>${cells.map(c => `<td>${c}</td>`).join('')}`;
    return row;
}

function renderEventStream() {
    const container = document.getElementById('event-stream-container');
    container.innerHTML = '';
    const visible = AuditViewState.allEvents.filter(e => new Date(e.event_date).getTime() <= AuditViewState.currentDate);
    if (!visible.length) { container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">No events at this date.</p>'; return; }

    const fragment = document.createDocumentFragment();
    visible.forEach(event => {
        const card = document.createElement('div');
        const status = ['verified', 'warning', 'critical'].includes((event.compliance_status || '').toLowerCase()) ? event.compliance_status.toLowerCase() : 'warning';
        card.className = `event-card ${status}`;
        const color = event.shareholder_name ? getShareholderColor(event.shareholder_name) : null;
        if (color) card.style.borderLeftColor = color;
        if (event.shareholder_name) card.setAttribute('data-shareholder', event.shareholder_name);

        const dateStr = new Date(event.event_date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
        const typeDisplay = event.event_type.replace(/_/g, ' ').toUpperCase();

        let details = '';
        if (event.shareholder_name) {
            details = `<span class="shareholder-pill" style="background-color: ${color};">${escapeHtml(event.shareholder_name)}</span>`;
            if (event.share_delta !== 0) details += ` ${event.share_delta > 0 ? '+' : ''}${formatNumber(event.share_delta)} ${escapeHtml(event.share_class || 'shares')}`;
        }

        const focusY = event.details && typeof event.details.preview_focus_y === 'number' ? event.details.preview_focus_y : null;
        const previewStyle = focusY !== null ? `object-position: 50% ${focusY * 100}%;` : '';
        const previewSrc = sanitizeImageSrc(event.preview_image);

        card.innerHTML = `
            <div class="event-card-header">
                <span class="event-type">${escapeHtml(typeDisplay)}</span>
                <span class="event-date">${dateStr}</span>
            </div>
            ${event.summary ? `<div class="event-summary">${escapeHtml(event.summary)}</div>` : (details ? `<div class="event-details" style="${color ? `border-left: 5px solid ${color}; padding-left: 8px;` : ''}">${details}</div>` : '')}
            ${previewSrc ? `<div class="event-preview" data-doc-id="${escapeAttr(event.source_doc_id || '')}" title="Click to view full document"><img src="${escapeAttr(previewSrc)}" alt="Document preview" class="event-preview-image" loading="lazy" style="${previewStyle}" /></div>` : ''}
            ${event.share_delta !== undefined && event.share_delta !== 0 ? `<div class="event-metadata"><div class="event-amount"><span class="label">Shares:</span><span class="value">${event.share_delta > 0 ? '+' : ''}${formatNumber(event.share_delta)}</span></div>${event.details && event.details.price_per_share ? `<div class="event-price"><span class="label">Price:</span><span class="value">$${parseFloat(event.details.price_per_share).toFixed(4)}</span></div>` : ''}</div>` : ''}
            ${!event.summary && event.source_snippet ? `<div class="source-quote">"${escapeHtml(event.source_snippet)}"</div>` : ''}
            ${event.compliance_note ? `<div class="compliance-note">${escapeHtml(event.compliance_note)}</div>` : ''}
            <div class="event-links">
                ${event.source_doc_id ? `<a href="#" class="event-link" data-doc-id="${escapeAttr(event.source_doc_id)}" data-snippet="${escapeAttr((event.source_snippet || '').replace(/"/g, ''))}" title="View source document">Source Document</a>` : ''}
                ${event.approval_doc_id ? `<a href="#" class="event-link" data-doc-id="${escapeAttr(event.approval_doc_id)}" data-snippet="${escapeAttr((event.approval_snippet || '').replace(/"/g, ''))}" title="View approval document">Board Approval</a>` : ''}
            </div>`;

        if (event.shareholder_name) {
            card.addEventListener('mouseenter', () => highlightShareholder(event.shareholder_name, true));
            card.addEventListener('mouseleave', () => highlightShareholder(event.shareholder_name, false));
        }

        fragment.appendChild(card);

        card.querySelectorAll('.event-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault(); e.stopPropagation();
                const docId = link.getAttribute('data-doc-id');
                if (docId) showDocumentModal(AuditViewState.auditId, docId, link.getAttribute('data-snippet') || null, previewSrc || null);
            });
        });

        const preview = card.querySelector('.event-preview');
        if (preview) {
            preview.addEventListener('click', (e) => {
                e.stopPropagation();
                const docId = preview.getAttribute('data-doc-id');
                if (docId) showDocumentModal(AuditViewState.auditId, docId, null, previewSrc || null);
            });
        }
    });

    container.appendChild(fragment);
    if (container.lastChild) container.lastChild.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function highlightShareholder(name, active) {
    if (!name) return;
    const safe = window.CSS && typeof window.CSS.escape === 'function' ? window.CSS.escape(name) : name.replace(/["\\]/g, '\\$&');
    const cls = active ? 'add' : 'remove';
    document.querySelectorAll(`.cap-table-row[data-shareholder="${safe}"]`).forEach(r => r.classList[cls]('highlight'));
    document.querySelectorAll(`.event-card[data-shareholder="${safe}"]`).forEach(c => c.classList[cls]('highlight'));
}

// Demo data converters
function convertDemoTimelineToEvents(timeline) {
    if (!timeline || !Array.isArray(timeline)) return [];
    return timeline.map((event, i) => {
        let shareholderName = null, shareClass = null, shareDelta = 0;
        const descMatch = event.description.match(/([\w\s]+)\s+(purchased|granted|received|repurchased)/i);
        if (descMatch) shareholderName = descMatch[1].trim();

        let eventType = 'formation';
        if (event.description.includes('purchased') || event.description.includes('Financing')) {
            eventType = 'issuance';
            const m = event.description.match(/([\d,]+)\s+(common|preferred|shares)/i);
            if (m) { shareDelta = parseInt(m[1].replace(/,/g, '')); shareClass = m[2]; }
        } else if (event.description.includes('granted')) {
            eventType = 'option_grant';
            const m = event.description.match(/([\d,]+)\s+/);
            if (m) { shareDelta = parseInt(m[1].replace(/,/g, '')); shareClass = 'Option'; }
        } else if (event.description.includes('repurchased')) {
            eventType = 'repurchase';
            const m = event.description.match(/([\d,]+)\s+shares/i);
            if (m) shareDelta = -parseInt(m[1].replace(/,/g, ''));
        }
        return {
            id: `demo-event-${i}`, audit_id: 999, event_date: event.date, event_type: eventType,
            shareholder_name: shareholderName, share_class: shareClass || 'Common', share_delta: shareDelta,
            source_snippet: event.description, approval_snippet: null, compliance_status: 'VERIFIED',
            compliance_note: null, source_doc_id: event.source_documents?.[0] || null, approval_doc_id: null, details: {},
        };
    });
}

function convertDemoCapTable(capTable, asOfDate) {
    if (!capTable || typeof capTable !== 'object') return { shareholders: [], total_shares: 0, as_of_date: asOfDate };
    const shareholders = Object.entries(capTable).map(([name, data]) => ({
        shareholder: name, share_class: data.share_type || 'Common',
        shares: data.shares || 0, ownership_pct: data.ownership_percent || 0, compliance_issues: [],
    }));
    return { shareholders, total_shares: shareholders.reduce((s, x) => s + x.shares, 0), as_of_date: asOfDate };
}
