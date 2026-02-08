"""
PDF Minute Document Generator for Corporate Governance Audits.

Generates a comprehensive PDF summary document with:
- Cap table with source document references
- Chronological equity events with tieouts
- Compliance issues
- Missing documents
- Document index
"""

import io
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

logger = logging.getLogger(__name__)


def create_styles():
    """Create custom paragraph styles for the document."""
    styles = getSampleStyleSheet()

    # Title style
    styles.add(ParagraphStyle(
        name='DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=6,
        textColor=colors.HexColor('#1a1a1a'),
        fontName='Helvetica-Bold'
    ))

    # Subtitle style
    styles.add(ParagraphStyle(
        name='DocSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=20,
        textColor=colors.HexColor('#525252'),
        fontName='Helvetica'
    ))

    # Section header style
    styles.add(ParagraphStyle(
        name='SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=16,
        spaceAfter=8,
        textColor=colors.HexColor('#334C6A'),
        fontName='Helvetica-Bold'
    ))

    # Subsection header
    styles.add(ParagraphStyle(
        name='SubsectionHeader',
        parent=styles['Heading3'],
        fontSize=11,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor('#525252'),
        fontName='Helvetica-Bold'
    ))

    # Body text
    styles.add(ParagraphStyle(
        name='BodyText',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=6,
        textColor=colors.HexColor('#1a1a1a'),
        fontName='Helvetica',
        leading=12
    ))

    # Quote/citation style
    styles.add(ParagraphStyle(
        name='Citation',
        parent=styles['Normal'],
        fontSize=8,
        leftIndent=20,
        textColor=colors.HexColor('#525252'),
        fontName='Helvetica-Oblique',
        leading=10
    ))

    # Issue styles
    styles.add(ParagraphStyle(
        name='IssueCritical',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=4,
        textColor=colors.HexColor('#DC2626'),
        fontName='Helvetica-Bold',
        leftIndent=10
    ))

    styles.add(ParagraphStyle(
        name='IssueWarning',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=4,
        textColor=colors.HexColor('#D97706'),
        fontName='Helvetica-Bold',
        leftIndent=10
    ))

    styles.add(ParagraphStyle(
        name='IssueNote',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=4,
        textColor=colors.HexColor('#334C6A'),
        fontName='Helvetica',
        leftIndent=10
    ))

    return styles


def format_number(value: Any) -> str:
    """Format a number with commas."""
    if value is None:
        return 'N/A'
    try:
        return f"{int(float(value)):,}"
    except (ValueError, TypeError):
        return str(value)


def format_currency(value: Any) -> str:
    """Format a value as currency."""
    if value is None:
        return 'N/A'
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return str(value)


def format_percentage(value: Any) -> str:
    """Format a value as percentage."""
    if value is None:
        return 'N/A'
    try:
        return f"{float(value):.2f}%"
    except (ValueError, TypeError):
        return str(value)


def generate_minute_document(
    audit_data: Dict[str, Any],
    equity_events: List[Dict[str, Any]],
    documents: List[Dict[str, Any]]
) -> bytes:
    """
    Generate a PDF minute document for a corporate governance audit.

    Args:
        audit_data: Audit record with company_name, cap_table, timeline, issues
        equity_events: List of equity events with source/approval references
        documents: List of documents with filenames and classifications

    Returns:
        PDF file as bytes
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )

    styles = create_styles()
    story = []

    # Extract data
    company_name = audit_data.get('company_name', 'Unknown Company')
    cap_table = audit_data.get('cap_table', [])
    timeline = audit_data.get('timeline', [])
    issues = audit_data.get('issues', [])
    created_at = audit_data.get('created_at', datetime.now())

    # Format date range
    if timeline:
        dates = [e.get('date', '') for e in timeline if e.get('date')]
        if dates:
            dates.sort()
            date_range = f"{dates[0]} to {dates[-1]}"
        else:
            date_range = "N/A"
    else:
        date_range = "N/A"

    # ========================================================================
    # HEADER SECTION
    # ========================================================================

    story.append(Paragraph("CORPORATE AUDIT SUMMARY", styles['DocTitle']))
    story.append(Paragraph(company_name, styles['DocSubtitle']))
    story.append(Spacer(1, 6))

    # Summary stats
    summary_data = [
        ['Date Range:', date_range],
        ['Documents Analyzed:', str(len(documents))],
        ['Equity Events:', str(len(equity_events))],
        ['Issues Found:', str(len(issues))],
        ['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M')],
    ]

    summary_table = Table(summary_data, colWidths=[1.5*inch, 4*inch])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#525252')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#1a1a1a')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    # ========================================================================
    # SECTION 1: CAP TABLE
    # ========================================================================

    story.append(Paragraph("SECTION 1: CAP TABLE", styles['SectionHeader']))

    if cap_table:
        # Build cap table data
        cap_headers = ['Shareholder', 'Shares', 'Class', 'Ownership %']
        cap_rows = [cap_headers]

        for entry in cap_table:
            cap_rows.append([
                entry.get('shareholder', 'Unknown'),
                format_number(entry.get('shares')),
                entry.get('share_class', 'Common Stock'),
                format_percentage(entry.get('ownership_pct'))
            ])

        # Add total row
        total_shares = sum(float(e.get('shares', 0)) for e in cap_table if e.get('shares'))
        cap_rows.append([
            'TOTAL',
            format_number(total_shares),
            '',
            '100.00%'
        ])

        cap_table_elem = Table(cap_rows, colWidths=[2.5*inch, 1.5*inch, 1.5*inch, 1*inch])
        cap_table_elem.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334C6A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),

            # Data rows
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -2), 9),
            ('BOTTOMPADDING', (0, 1), (-1, -2), 6),
            ('TOPPADDING', (0, 1), (-1, -2), 6),

            # Total row
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F5F5F5')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
            ('TOPPADDING', (0, -1), (-1, -1), 8),

            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E5E5')),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#334C6A')),

            # Alignment
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ]))
        story.append(cap_table_elem)
    else:
        story.append(Paragraph("No cap table data available.", styles['BodyText']))

    story.append(Spacer(1, 20))

    # ========================================================================
    # SECTION 2: EQUITY EVENTS
    # ========================================================================

    story.append(Paragraph("SECTION 2: EQUITY EVENTS (Chronological)", styles['SectionHeader']))

    if equity_events:
        # Sort by date
        sorted_events = sorted(equity_events, key=lambda x: x.get('event_date', '') or '')

        for event in sorted_events:
            event_date = event.get('event_date', 'Unknown date')
            event_type = event.get('event_type', 'unknown').upper()
            shareholder = event.get('shareholder_name', '')
            share_delta = event.get('share_delta', 0)
            share_class = event.get('share_class', '')
            source_snippet = event.get('source_snippet', '')
            approval_snippet = event.get('approval_snippet', '')
            compliance_status = event.get('compliance_status', 'VERIFIED')
            compliance_note = event.get('compliance_note', '')
            summary = event.get('summary', '')

            # Event header
            event_elements = []

            # Format event description
            if shareholder and share_delta:
                delta_str = f"+{format_number(share_delta)}" if share_delta > 0 else format_number(share_delta)
                event_header = f"<b>{event_date}</b> - {event_type}: {shareholder} ({delta_str} {share_class})"
            else:
                event_header = f"<b>{event_date}</b> - {event_type}"

            event_elements.append(Paragraph(event_header, styles['BodyText']))

            # Summary
            if summary:
                event_elements.append(Paragraph(summary, styles['Citation']))

            # Source reference
            if source_snippet:
                source_text = f"<i>Source:</i> \"{source_snippet[:200]}...\""
                event_elements.append(Paragraph(source_text, styles['Citation']))

            # Approval reference
            if approval_snippet:
                approval_text = f"<i>Approval:</i> \"{approval_snippet[:200]}...\""
                event_elements.append(Paragraph(approval_text, styles['Citation']))

            # Compliance status
            if compliance_status != 'VERIFIED':
                status_style = styles['IssueWarning'] if compliance_status == 'WARNING' else styles['IssueCritical']
                event_elements.append(Paragraph(f"Status: {compliance_status} - {compliance_note}", status_style))

            event_elements.append(Spacer(1, 8))

            # Keep event together on same page
            story.append(KeepTogether(event_elements))
    else:
        story.append(Paragraph("No equity events recorded.", styles['BodyText']))

    story.append(Spacer(1, 20))

    # ========================================================================
    # SECTION 3: COMPLIANCE ISSUES
    # ========================================================================

    story.append(Paragraph("SECTION 3: COMPLIANCE ISSUES", styles['SectionHeader']))

    if issues:
        # Group by severity
        critical_issues = [i for i in issues if i.get('severity') == 'critical']
        warning_issues = [i for i in issues if i.get('severity') == 'warning']
        note_issues = [i for i in issues if i.get('severity') not in ('critical', 'warning')]

        if critical_issues:
            story.append(Paragraph("Critical Issues", styles['SubsectionHeader']))
            for issue in critical_issues:
                category = issue.get('category', '')
                description = issue.get('description', '')
                story.append(Paragraph(f"[{category}] {description}", styles['IssueCritical']))

        if warning_issues:
            story.append(Paragraph("Warnings", styles['SubsectionHeader']))
            for issue in warning_issues:
                category = issue.get('category', '')
                description = issue.get('description', '')
                story.append(Paragraph(f"[{category}] {description}", styles['IssueWarning']))

        if note_issues:
            story.append(Paragraph("Notes", styles['SubsectionHeader']))
            for issue in note_issues:
                category = issue.get('category', '')
                description = issue.get('description', '')
                story.append(Paragraph(f"[{category}] {description}", styles['IssueNote']))
    else:
        story.append(Paragraph("No compliance issues detected.", styles['BodyText']))

    story.append(Spacer(1, 20))

    # ========================================================================
    # SECTION 4: MISSING DOCUMENTS
    # ========================================================================

    story.append(Paragraph("SECTION 4: MISSING DOCUMENTS", styles['SectionHeader']))

    # Extract missing document issues
    missing_docs = [i for i in issues if 'Missing' in i.get('category', '')]

    if missing_docs:
        for issue in missing_docs:
            story.append(Paragraph(f"• {issue.get('description', '')}", styles['BodyText']))
    else:
        story.append(Paragraph("No missing documents detected.", styles['BodyText']))

    story.append(PageBreak())

    # ========================================================================
    # SECTION 5: DOCUMENT INDEX
    # ========================================================================

    story.append(Paragraph("SECTION 5: DOCUMENT INDEX", styles['SectionHeader']))

    if documents:
        # Group by category
        by_category = {}
        for doc in documents:
            category = doc.get('classification', 'Other')
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(doc.get('filename', 'Unknown'))

        for category in sorted(by_category.keys()):
            story.append(Paragraph(category, styles['SubsectionHeader']))
            for filename in sorted(by_category[category]):
                story.append(Paragraph(f"• {filename}", styles['BodyText']))
    else:
        story.append(Paragraph("No documents in index.", styles['BodyText']))

    # ========================================================================
    # FOOTER
    # ========================================================================

    story.append(Spacer(1, 30))
    story.append(Paragraph(
        "Generated by Tieout - Corporate Governance Auditing Platform",
        ParagraphStyle(
            name='Footer',
            fontSize=8,
            textColor=colors.HexColor('#A3A3A3'),
            alignment=TA_CENTER
        )
    ))

    # Build the document
    doc.build(story)
    buffer.seek(0)
    return buffer.read()
