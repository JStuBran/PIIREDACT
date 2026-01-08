"""PDF Generator service - Professional WeasyPrint HTML to PDF."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from weasyprint import HTML, CSS

logger = logging.getLogger(__name__)

# Professional CSS for all reports
BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --bg: #ffffff;
    --bg-subtle: #f8fafc;
    --text: #0f172a;
    --text-secondary: #475569;
    --text-muted: #94a3b8;
    --border: #e2e8f0;
    --border-strong: #cbd5e1;
    --primary: #3b82f6;
    --primary-dark: #1d4ed8;
    --success: #10b981;
    --success-bg: #ecfdf5;
    --warning: #f59e0b;
    --warning-bg: #fffbeb;
    --danger: #ef4444;
    --danger-bg: #fef2f2;
    --info: #06b6d4;
    --info-bg: #ecfeff;
    --accent-gradient: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: var(--text);
    background: var(--bg);
}

/* Page Setup */
@page {
    size: letter;
    margin: 0.6in 0.7in;
    @top-right {
        content: "Page " counter(page) " of " counter(pages);
        font-size: 9pt;
        color: var(--text-muted);
    }
}

@page:first {
    @top-right { content: none; }
}

/* Container */
.report {
    max-width: 100%;
}

/* Header */
.report-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding-bottom: 20px;
    margin-bottom: 24px;
    border-bottom: 2px solid var(--border);
}

.report-header .brand {
    display: flex;
    align-items: center;
    gap: 10px;
}

.report-header .logo {
    width: 40px;
    height: 40px;
    background: var(--accent-gradient);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 20px;
    font-weight: 700;
}

.report-header h1 {
    font-size: 22pt;
    font-weight: 800;
    color: var(--text);
    letter-spacing: -0.5px;
}

.report-header .subtitle {
    font-size: 10pt;
    color: var(--text-secondary);
    margin-top: 2px;
}

.report-header .meta {
    text-align: right;
    font-size: 9pt;
    color: var(--text-muted);
}

.report-header .meta .date {
    font-weight: 600;
    color: var(--text-secondary);
}

/* Score Badge (Top Right) */
.score-badge {
    background: var(--accent-gradient);
    color: white;
    padding: 12px 20px;
    border-radius: 12px;
    text-align: center;
    min-width: 100px;
}

.score-badge .label {
    font-size: 9pt;
    opacity: 0.9;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.score-badge .value {
    font-size: 28pt;
    font-weight: 800;
    line-height: 1.1;
}

.score-badge .max {
    font-size: 10pt;
    opacity: 0.8;
}

/* Sections */
.section {
    margin-bottom: 20px;
    page-break-inside: avoid;
}

.section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
}

.section-icon {
    font-size: 16pt;
}

.section-title {
    font-size: 13pt;
    font-weight: 700;
    color: var(--text);
}

/* Cards */
.card {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 12px;
}

.card-header {
    font-size: 10pt;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Grid Layouts */
.grid { display: grid; gap: 12px; }
.grid-2 { grid-template-columns: 1fr 1fr; }
.grid-3 { grid-template-columns: 1fr 1fr 1fr; }
.grid-4 { grid-template-columns: 1fr 1fr 1fr 1fr; }

/* KPI Cards */
.kpi {
    background: var(--bg-subtle);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
    text-align: center;
}

.kpi-icon {
    font-size: 18pt;
    margin-bottom: 4px;
}

.kpi-value {
    font-size: 24pt;
    font-weight: 800;
    color: var(--text);
    line-height: 1.1;
}

.kpi-label {
    font-size: 9pt;
    color: var(--text-muted);
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.kpi-change {
    font-size: 9pt;
    margin-top: 6px;
    padding: 2px 8px;
    border-radius: 10px;
    display: inline-block;
}

.kpi-change.positive {
    background: var(--success-bg);
    color: var(--success);
}

.kpi-change.negative {
    background: var(--danger-bg);
    color: var(--danger);
}

/* Progress Bars */
.progress-row {
    display: grid;
    grid-template-columns: 120px 1fr 50px;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
}

.progress-label {
    font-size: 10pt;
    color: var(--text-secondary);
    font-weight: 500;
}

.progress-track {
    height: 10px;
    background: var(--bg-subtle);
    border-radius: 5px;
    overflow: hidden;
    border: 1px solid var(--border);
}

.progress-fill {
    height: 100%;
    border-radius: 5px;
    transition: width 0.3s ease;
}

.progress-fill.blue { background: var(--primary); }
.progress-fill.green { background: var(--success); }
.progress-fill.yellow { background: var(--warning); }
.progress-fill.red { background: var(--danger); }

.progress-value {
    font-size: 10pt;
    font-weight: 600;
    text-align: right;
    color: var(--text);
}

/* Score Breakdown */
.score-breakdown {
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
}

.score-row {
    display: grid;
    grid-template-columns: 1fr 80px 60px;
    align-items: center;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    gap: 12px;
}

.score-row:last-child {
    border-bottom: none;
}

.score-row:nth-child(even) {
    background: var(--bg-subtle);
}

.score-criterion {
    font-size: 10pt;
    font-weight: 500;
}

.score-bar {
    height: 8px;
    background: var(--bg-subtle);
    border-radius: 4px;
    overflow: hidden;
    border: 1px solid var(--border);
}

.score-bar-fill {
    height: 100%;
    border-radius: 4px;
}

.score-bar-fill.excellent { background: var(--success); }
.score-bar-fill.good { background: var(--primary); }
.score-bar-fill.average { background: var(--warning); }
.score-bar-fill.poor { background: var(--danger); }

.score-value {
    font-size: 10pt;
    font-weight: 700;
    text-align: right;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 10pt;
}

th, td {
    padding: 10px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}

th {
    background: var(--bg-subtle);
    font-weight: 600;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-secondary);
}

tr:last-child td {
    border-bottom: none;
}

/* Lists */
ul, ol {
    margin: 8px 0;
    padding-left: 20px;
}

li {
    margin-bottom: 6px;
    line-height: 1.5;
}

li::marker {
    color: var(--primary);
}

/* Coaching Items */
.coaching-item {
    display: flex;
    gap: 10px;
    padding: 10px 12px;
    background: var(--bg-subtle);
    border-radius: 8px;
    margin-bottom: 8px;
    border-left: 3px solid var(--primary);
}

.coaching-item.positive {
    border-left-color: var(--success);
    background: var(--success-bg);
}

.coaching-item.negative {
    border-left-color: var(--warning);
    background: var(--warning-bg);
}

.coaching-item .icon {
    font-size: 14pt;
}

.coaching-item .content {
    flex: 1;
    font-size: 10pt;
    line-height: 1.5;
}

/* Focus Box */
.focus-box {
    background: var(--info-bg);
    border: 1px solid var(--info);
    border-radius: 10px;
    padding: 14px 16px;
    margin-top: 16px;
}

.focus-box .label {
    font-size: 9pt;
    font-weight: 600;
    color: var(--info);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}

.focus-box .content {
    font-size: 11pt;
    color: var(--text);
    font-weight: 500;
}

/* Talk Distribution Visual */
.talk-distribution {
    display: flex;
    height: 24px;
    border-radius: 12px;
    overflow: hidden;
    margin: 12px 0;
    border: 1px solid var(--border);
}

.talk-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 9pt;
    font-weight: 600;
}

.talk-bar.rep {
    background: var(--primary);
}

.talk-bar.prospect {
    background: var(--text-secondary);
}

/* Keywords */
.keyword-tag {
    display: inline-block;
    padding: 4px 10px;
    background: var(--bg-subtle);
    border: 1px solid var(--border);
    border-radius: 20px;
    font-size: 9pt;
    margin: 2px;
}

.keyword-tag.competitor {
    background: var(--danger-bg);
    border-color: var(--danger);
    color: var(--danger);
}

.keyword-tag.product {
    background: var(--success-bg);
    border-color: var(--success);
    color: var(--success);
}

.keyword-tag.objection {
    background: var(--warning-bg);
    border-color: var(--warning);
    color: var(--warning);
}

/* Transcript */
.transcript-segment {
    margin-bottom: 14px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
    page-break-inside: avoid;
}

.transcript-segment:last-child {
    border-bottom: none;
}

.segment-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
}

.segment-time {
    font-size: 9pt;
    font-weight: 600;
    color: var(--primary);
    background: var(--bg-subtle);
    padding: 2px 8px;
    border-radius: 4px;
}

.segment-speaker {
    font-size: 9pt;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-secondary);
}

.segment-text {
    font-size: 10pt;
    line-height: 1.7;
    color: var(--text);
}

/* Footer */
.report-footer {
    margin-top: 30px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 9pt;
    color: var(--text-muted);
}

.report-footer .logo-small {
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 600;
    color: var(--text-secondary);
}

/* Utilities */
.text-center { text-align: center; }
.text-right { text-align: right; }
.text-muted { color: var(--text-muted); }
.text-success { color: var(--success); }
.text-warning { color: var(--warning); }
.text-danger { color: var(--danger); }
.font-bold { font-weight: 700; }
.mt-2 { margin-top: 8px; }
.mt-4 { margin-top: 16px; }
.mb-2 { margin-bottom: 8px; }
.mb-4 { margin-bottom: 16px; }

/* Print optimizations */
@media print {
    * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
    body { background: white !important; }
    .section { page-break-inside: avoid; }
    h2, h3 { page-break-after: avoid; }
}
"""


class PDFGeneratorService:
    """Generate professional PDF reports using WeasyPrint."""

    def __init__(self):
        """Initialize the PDF generator."""
        logger.info("PDFGeneratorService initialized")

    def generate_coaching_report(
        self,
        analysis: Dict[str, Any],
        output_path: str,
        score_data: Optional[Dict[str, Any]] = None,
        conv_intel: Optional[Dict[str, Any]] = None,
        keywords_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate professional coaching report PDF.

        Args:
            analysis: Analysis data from AnalyzerService
            output_path: Path to save PDF
            score_data: Optional scoring data
            conv_intel: Optional conversation intelligence data
            keywords_data: Optional keyword tracking data

        Returns:
            Path to generated PDF
        """
        html_content = self._build_coaching_html(
            analysis, score_data, conv_intel, keywords_data
        )
        
        HTML(string=html_content).write_pdf(
            output_path,
            stylesheets=[CSS(string=BASE_CSS)],
        )
        
        logger.info(f"Generated coaching report: {output_path}")
        return output_path

    def generate_stats_report(
        self,
        stats: Dict[str, Any],
        output_path: str,
        conv_intel: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate professional call stats PDF.

        Args:
            stats: Stats data from AnalyzerService
            output_path: Path to save PDF
            conv_intel: Optional conversation intelligence data

        Returns:
            Path to generated PDF
        """
        html_content = self._build_stats_html(stats, conv_intel)
        
        HTML(string=html_content).write_pdf(
            output_path,
            stylesheets=[CSS(string=BASE_CSS)],
        )
        
        logger.info(f"Generated stats report: {output_path}")
        return output_path

    def _build_coaching_html(
        self,
        analysis: Dict[str, Any],
        score_data: Optional[Dict[str, Any]] = None,
        conv_intel: Optional[Dict[str, Any]] = None,
        keywords_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build HTML for professional coaching report."""
        now = datetime.now().strftime("%B %d, %Y")
        time_now = datetime.now().strftime("%I:%M %p")
        
        # Score badge HTML
        score_badge = ""
        if score_data and score_data.get("overall_score"):
            score = score_data["overall_score"]
            score_badge = f"""
            <div class="score-badge">
                <div class="label">Score</div>
                <div class="value">{score}</div>
                <div class="max">/ 100</div>
            </div>
            """
        
        # Score breakdown section
        score_section = ""
        # scores is a dict keyed by criterion ID: {criterion_id: {score: X, reasoning: Y, ...}}
        scores_dict = score_data.get("scores", {}) if score_data else {}
        if scores_dict:
            criteria_html = ""
            for criterion_id, criterion_data in scores_dict.items():
                # Handle both dict and raw score value
                if isinstance(criterion_data, dict):
                    name = criterion_data.get("name", criterion_id)
                    score = criterion_data.get("score", 0)
                    max_score = criterion_data.get("max_score", 5)
                else:
                    name = criterion_id
                    score = criterion_data
                    max_score = 5
                
                pct = int((score / max_score) * 100) if max_score > 0 else 0
                
                # Determine color class
                if pct >= 80:
                    color_class = "excellent"
                elif pct >= 60:
                    color_class = "good"
                elif pct >= 40:
                    color_class = "average"
                else:
                    color_class = "poor"
                
                criteria_html += f"""
                <div class="score-row">
                    <div class="score-criterion">{self._esc(str(name))}</div>
                    <div class="score-bar"><div class="score-bar-fill {color_class}" style="width:{pct}%"></div></div>
                    <div class="score-value">{score}/{max_score}</div>
                </div>
                """
            
            score_section = f"""
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">📊</span>
                    <span class="section-title">Score Breakdown</span>
                </div>
                <div class="score-breakdown">
                    {criteria_html}
                </div>
            </div>
            """
        
        # Conversation intelligence section
        conv_section = ""
        if conv_intel:
            # Access nested talk_patterns structure
            talk_patterns = conv_intel.get("talk_patterns", {})
            agent_ratio = talk_patterns.get("agent_talk_ratio", 50)
            customer_ratio = talk_patterns.get("customer_talk_ratio", 50)
            # Calculate talk:listen as agent:customer ratio
            talk_ratio = round(agent_ratio / customer_ratio, 1) if customer_ratio > 0 else 1.0
            
            # Access nested questions structure
            questions_data = conv_intel.get("questions", {})
            questions_asked = questions_data.get("total_questions", 0)
            
            # Access nested objections structure
            objections_data = conv_intel.get("objections", {})
            objections = objections_data.get("count", 0)
            
            conv_section = f"""
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">🧠</span>
                    <span class="section-title">Conversation Intelligence</span>
                </div>
                <div class="grid grid-3">
                    <div class="kpi">
                        <div class="kpi-value">{talk_ratio:.1f}:1</div>
                        <div class="kpi-label">Talk:Listen Ratio</div>
                    </div>
                    <div class="kpi">
                        <div class="kpi-value">{questions_asked}</div>
                        <div class="kpi-label">Questions Asked</div>
                    </div>
                    <div class="kpi">
                        <div class="kpi-value">{objections}</div>
                        <div class="kpi-label">Objections Detected</div>
                    </div>
                </div>
            </div>
            """
        
        # Keywords section
        keywords_section = ""
        if keywords_data and keywords_data.get("summary"):
            summary = keywords_data.get("summary", {})
            tags_html = ""
            
            for keyword, count in list(summary.get("top_keywords", {}).items())[:10]:
                tags_html += f'<span class="keyword-tag">{self._esc(keyword)} ({count})</span>'
            
            if tags_html:
                keywords_section = f"""
                <div class="section">
                    <div class="section-header">
                        <span class="section-icon">🏷️</span>
                        <span class="section-title">Keywords Detected</span>
                    </div>
                    <div class="card">
                        {tags_html}
                    </div>
                </div>
                """
        
        # Build highlights
        highlights = analysis.get("highlights", [])
        highlights_html = ""
        if highlights:
            items = "".join(f"""
                <div class="coaching-item positive">
                    <span class="icon">✓</span>
                    <span class="content">{self._esc(h)}</span>
                </div>
            """ for h in highlights[:5])
            
            highlights_html = f"""
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">⭐</span>
                    <span class="section-title">Highlights</span>
                </div>
                {items}
            </div>
            """
        
        # Build coaching commentary
        coaching = analysis.get("coaching", {})
        coaching_html = ""
        if coaching:
            done_well = coaching.get("done_well", [])
            improve = coaching.get("improve", [])
            focus = coaching.get("focus_next", "")
            
            done_html = ""
            if done_well:
                done_items = "".join(f"""
                    <div class="coaching-item positive">
                        <span class="icon">👍</span>
                        <span class="content">{self._esc(d)}</span>
                    </div>
                """ for d in done_well[:4])
                done_html = f"""
                <div class="mb-4">
                    <div class="card-header">Done Well</div>
                    {done_items}
                </div>
                """
            
            improve_html = ""
            if improve:
                improve_items = "".join(f"""
                    <div class="coaching-item negative">
                        <span class="icon">💡</span>
                        <span class="content">{self._esc(i)}</span>
                    </div>
                """ for i in improve[:4])
                improve_html = f"""
                <div class="mb-4">
                    <div class="card-header">Areas to Improve</div>
                    {improve_items}
                </div>
                """
            
            focus_html = ""
            if focus:
                focus_html = f"""
                <div class="focus-box">
                    <div class="label">🎯 Focus for Next Call</div>
                    <div class="content">{self._esc(focus)}</div>
                </div>
                """
            
            coaching_html = f"""
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">🎓</span>
                    <span class="section-title">Coaching Feedback</span>
                </div>
                {done_html}
                {improve_html}
                {focus_html}
            </div>
            """
        
        # Objection handling
        obj = analysis.get("objection_handling", {})
        objection_html = ""
        if obj.get("objection") or obj.get("improvement"):
            objection_html = f"""
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">🛡️</span>
                    <span class="section-title">Objection Handling</span>
                </div>
                <div class="card">
                    <table>
                        <tr>
                            <td style="width:120px;font-weight:600">Objection</td>
                            <td>{self._esc(obj.get("objection", "None identified"))}</td>
                        </tr>
                        <tr>
                            <td style="font-weight:600">Suggestion</td>
                            <td>{self._esc(obj.get("improvement", ""))}</td>
                        </tr>
                    </table>
                </div>
            </div>
            """
        
        # Timestamp highlights
        ts_highlights = analysis.get("timestamp_highlights", [])
        ts_html = ""
        if ts_highlights:
            ts_items = "".join(f"<li>{self._esc(t)}</li>" for t in ts_highlights[:6])
            ts_html = f"""
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">⏱️</span>
                    <span class="section-title">Key Moments</span>
                </div>
                <div class="card">
                    <ol>{ts_items}</ol>
                </div>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Sales Call Coaching Report</title>
        </head>
        <body>
            <div class="report">
                <div class="report-header">
                    <div>
                        <div class="brand">
                            <div class="logo">📞</div>
                            <div>
                                <h1>Coaching Report</h1>
                                <div class="subtitle">Sales Call Analysis</div>
                            </div>
                        </div>
                    </div>
                    <div style="display:flex;gap:20px;align-items:flex-start">
                        <div class="meta">
                            <div class="date">{now}</div>
                            <div>{time_now}</div>
                        </div>
                        {score_badge}
                    </div>
                </div>

                <div class="section">
                    <div class="section-header">
                        <span class="section-icon">📋</span>
                        <span class="section-title">Executive Summary</span>
                    </div>
                    <div class="card">
                        <p>{self._esc(analysis.get("overall_summary", ""))}</p>
                    </div>
                </div>

                {score_section}
                {conv_section}
                {highlights_html}
                {coaching_html}
                {objection_html}
                {keywords_section}
                {ts_html}

                <div class="report-footer">
                    <div class="logo-small">
                        <span>📞</span>
                        <span>Sales Call Analyzer</span>
                    </div>
                    <div>Confidential • Generated {now} at {time_now}</div>
                </div>
            </div>
        </body>
        </html>
        """

    def _build_stats_html(
        self,
        stats: Dict[str, Any],
        conv_intel: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build HTML for professional stats report."""
        now = datetime.now().strftime("%B %d, %Y")
        time_now = datetime.now().strftime("%I:%M %p")
        
        agent = stats.get("agent_label", "Rep")
        customer = stats.get("customer_label", "Prospect")
        
        agent_share = stats.get("talk_share_pct", {}).get(agent, 0)
        customer_share = stats.get("talk_share_pct", {}).get(customer, 0)
        
        agent_talk = stats.get("talk_time_sec", {}).get(agent, 0)
        customer_talk = stats.get("talk_time_sec", {}).get(customer, 0)
        
        agent_wpm = stats.get("wpm", {}).get(agent, 0)
        customer_wpm = stats.get("wpm", {}).get(customer, 0)
        
        agent_utt = stats.get("utterances", {}).get(agent, 0)
        customer_utt = stats.get("utterances", {}).get(customer, 0)
        
        questions = stats.get("questions", {})
        filler = stats.get("filler", {})
        duration = stats.get("duration_min", 0)
        
        # Conversation intelligence metrics
        conv_metrics = ""
        if conv_intel:
            # Access nested talk_patterns structure
            talk_patterns = conv_intel.get("talk_patterns", {})
            agent_ratio = talk_patterns.get("agent_talk_ratio", 50)
            customer_ratio = talk_patterns.get("customer_talk_ratio", 50)
            talk_ratio = round(agent_ratio / customer_ratio, 1) if customer_ratio > 0 else 1.0
            
            # Access nested monologues structure
            monologues_data = conv_intel.get("monologues", {})
            monologue_instances = monologues_data.get("instances", [])
            monologue_count = monologues_data.get("count", 0)
            longest_monologue = max([m.get("duration_sec", 0) for m in monologue_instances]) if monologue_instances else 0
            
            # Access nested engagement structure for interruptions
            engagement_data = conv_intel.get("engagement", {})
            interruptions = engagement_data.get("interruptions", 0)
            
            conv_metrics = f"""
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">🧠</span>
                    <span class="section-title">Conversation Intelligence</span>
                </div>
                <div class="grid grid-4">
                    <div class="kpi">
                        <div class="kpi-value">{talk_ratio:.1f}:1</div>
                        <div class="kpi-label">Talk:Listen</div>
                    </div>
                    <div class="kpi">
                        <div class="kpi-value">{monologue_count}</div>
                        <div class="kpi-label">Monologues</div>
                    </div>
                    <div class="kpi">
                        <div class="kpi-value">{int(longest_monologue)}s</div>
                        <div class="kpi-label">Longest Monologue</div>
                    </div>
                    <div class="kpi">
                        <div class="kpi-value">{interruptions}</div>
                        <div class="kpi-label">Interruptions</div>
                    </div>
                </div>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Call Statistics Report</title>
        </head>
        <body>
            <div class="report">
                <div class="report-header">
                    <div>
                        <div class="brand">
                            <div class="logo">📊</div>
                            <div>
                                <h1>Call Statistics</h1>
                                <div class="subtitle">Performance Metrics & Analysis</div>
                            </div>
                        </div>
                    </div>
                    <div class="meta">
                        <div class="date">{now}</div>
                        <div>Duration: {duration:.1f} min</div>
                    </div>
                </div>

                <div class="section">
                    <div class="section-header">
                        <span class="section-icon">⏱️</span>
                        <span class="section-title">Talk Time Distribution</span>
                    </div>
                    <div class="talk-distribution">
                        <div class="talk-bar rep" style="width:{agent_share}%">{self._esc(agent)} {agent_share}%</div>
                        <div class="talk-bar prospect" style="width:{customer_share}%">{self._esc(customer)} {customer_share}%</div>
                    </div>
                    <div class="grid grid-2">
                        <div class="kpi">
                            <div class="kpi-icon">🎤</div>
                            <div class="kpi-value">{self._format_time(agent_talk)}</div>
                            <div class="kpi-label">{self._esc(agent)} Talk Time</div>
                        </div>
                        <div class="kpi">
                            <div class="kpi-icon">👤</div>
                            <div class="kpi-value">{self._format_time(customer_talk)}</div>
                            <div class="kpi-label">{self._esc(customer)} Talk Time</div>
                        </div>
                    </div>
                </div>

                <div class="section">
                    <div class="section-header">
                        <span class="section-icon">🗣️</span>
                        <span class="section-title">Speaking Metrics</span>
                    </div>
                    <div class="grid grid-4">
                        <div class="kpi">
                            <div class="kpi-value">{agent_wpm}</div>
                            <div class="kpi-label">{self._esc(agent)} WPM</div>
                        </div>
                        <div class="kpi">
                            <div class="kpi-value">{customer_wpm}</div>
                            <div class="kpi-label">{self._esc(customer)} WPM</div>
                        </div>
                        <div class="kpi">
                            <div class="kpi-value">{agent_utt}</div>
                            <div class="kpi-label">{self._esc(agent)} Turns</div>
                        </div>
                        <div class="kpi">
                            <div class="kpi-value">{customer_utt}</div>
                            <div class="kpi-label">{self._esc(customer)} Turns</div>
                        </div>
                    </div>
                </div>

                {conv_metrics}

                <div class="section">
                    <div class="section-header">
                        <span class="section-icon">❓</span>
                        <span class="section-title">Questions & Engagement</span>
                    </div>
                    <div class="grid grid-2">
                        <div class="card">
                            <div class="card-header">Questions Asked</div>
                            <table>
                                <tr><td>Total Questions</td><td class="text-right font-bold">{questions.get("agent_total", 0)}</td></tr>
                                <tr><td>Questions per Minute</td><td class="text-right font-bold">{questions.get("rate_per_min", 0)}</td></tr>
                            </table>
                        </div>
                        <div class="card">
                            <div class="card-header">Filler Words</div>
                            <table>
                                <tr><td>Total Fillers</td><td class="text-right font-bold">{filler.get("agent_count", 0)}</td></tr>
                                <tr><td>Per 100 Words</td><td class="text-right font-bold">{filler.get("agent_per_100_words", 0)}</td></tr>
                            </table>
                        </div>
                    </div>
                </div>

                <div class="section">
                    <div class="section-header">
                        <span class="section-icon">📈</span>
                        <span class="section-title">Call Overview</span>
                    </div>
                    <div class="card">
                        <table>
                            <tr><td>Total Duration</td><td class="text-right">{stats.get("total_duration_sec", 0)}s ({duration:.1f} min)</td></tr>
                            <tr><td>Speaker Turns</td><td class="text-right">{stats.get("turns", 0)}</td></tr>
                            <tr><td>Words Spoken</td><td class="text-right">{stats.get("total_words", 0)}</td></tr>
                        </table>
                    </div>
                </div>

                <div class="report-footer">
                    <div class="logo-small">
                        <span>📞</span>
                        <span>Sales Call Analyzer</span>
                    </div>
                    <div>Confidential • Generated {now} at {time_now}</div>
                </div>
            </div>
        </body>
        </html>
        """

    def generate_transcript_pdf(
        self,
        job: Dict[str, Any],
        transcription: Dict[str, Any],
        output_path: str,
    ) -> str:
        """
        Generate professional transcript PDF.

        Args:
            job: Call job record
            transcription: Transcription data
            output_path: Path to save PDF

        Returns:
            Path to generated PDF
        """
        html_content = self._build_transcript_html(job, transcription)
        
        HTML(string=html_content).write_pdf(
            output_path,
            stylesheets=[CSS(string=BASE_CSS)],
        )
        
        logger.info(f"Generated transcript PDF: {output_path}")
        return output_path

    def _build_transcript_html(
        self,
        job: Dict[str, Any],
        transcription: Dict[str, Any],
    ) -> str:
        """Build HTML for professional transcript PDF."""
        now = datetime.now().strftime("%B %d, %Y")
        time_now = datetime.now().strftime("%I:%M %p")
        segments = transcription.get("segments", [])
        redacted_text = transcription.get("redacted_text", "")
        duration = transcription.get("duration_min", 0)
        
        # Build segments HTML
        segments_html = ""
        if segments:
            for seg in segments:
                start_time = self._format_timestamp(seg.get("start", 0))
                text = self._esc(seg.get("text", ""))
                speaker = seg.get("speaker", "Speaker")
                
                # Format speaker name
                if speaker.startswith("spk_"):
                    speaker_num = speaker.replace("spk_", "")
                    speaker = f"Speaker {int(speaker_num) + 1}"
                
                segments_html += f"""
                <div class="transcript-segment">
                    <div class="segment-header">
                        <span class="segment-time">{start_time}</span>
                        <span class="segment-speaker">{self._esc(speaker)}</span>
                    </div>
                    <div class="segment-text">{text}</div>
                </div>
                """
        else:
            # Fallback to full text if no segments
            segments_html = f'<div class="card"><p style="white-space:pre-wrap;line-height:1.8">{self._esc(redacted_text)}</p></div>'

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Transcript - {self._esc(job.get('filename', 'Call'))}</title>
        </head>
        <body>
            <div class="report">
                <div class="report-header">
                    <div>
                        <div class="brand">
                            <div class="logo">📝</div>
                            <div>
                                <h1>Call Transcript</h1>
                                <div class="subtitle">{self._esc(job.get('filename', 'Recording'))}</div>
                            </div>
                        </div>
                    </div>
                    <div class="meta">
                        <div class="date">{now}</div>
                        <div>Duration: {duration:.1f} min</div>
                    </div>
                </div>

                <div class="section">
                    <div class="section-header">
                        <span class="section-icon">💬</span>
                        <span class="section-title">Transcript</span>
                    </div>
                    {segments_html}
                </div>

                <div class="report-footer">
                    <div class="logo-small">
                        <span>📞</span>
                        <span>Sales Call Analyzer</span>
                    </div>
                    <div>Confidential • PII Redacted • Generated {now}</div>
                </div>
            </div>
        </body>
        </html>
        """

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds as MM:SS."""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def _format_time(self, seconds: float) -> str:
        """Format seconds as M:SS or H:MM:SS."""
        if seconds >= 3600:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}:{secs:02d}"

    def _esc(self, text: Any) -> str:
        """Escape HTML special characters."""
        if text is None:
            return ""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
