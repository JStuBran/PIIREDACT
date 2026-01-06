"""PDF Generator service - WeasyPrint HTML to PDF."""

import logging
from datetime import datetime
from typing import Any, Dict, List

from weasyprint import HTML, CSS

logger = logging.getLogger(__name__)

# Base CSS for all reports
BASE_CSS = """
:root {
    --bg: #ffffff;
    --text: #111317;
    --muted: #667085;
    --line: #e9eaeb;
    --chip: #f6f7f8;
    --primary: #111317;
    --card: #fff;
    --accent-a: #0f62fe;
    --accent-b: #111317;
}

* { box-sizing: border-box; }

body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font: 14px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, Inter, Arial, sans-serif;
}

.container {
    max-width: 960px;
    margin: 0 auto;
    padding: 28px;
}

header {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: flex-start;
    margin-bottom: 18px;
}

h1 { font-size: 26px; margin: 0; }
h2 { font-size: 18px; margin: 0 0 10px; }

.subtitle { color: var(--muted); margin-top: 2px; }

.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.chip {
    background: var(--chip);
    border: 1px solid var(--line);
    padding: 6px 10px;
    border-radius: 999px;
    font-size: 12px;
}

section {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 18px;
    margin-bottom: 14px;
}

.grid { display: grid; gap: 14px; }
.grid-2 { grid-template-columns: 1fr 1fr; }

table { width: 100%; border-collapse: collapse; }
td, th {
    padding: 6px 8px;
    border-bottom: 1px solid var(--line);
    vertical-align: top;
    text-align: left;
}
tr:last-child td { border-bottom: none; }

ul { margin: 8px 0; padding-left: 20px; }
li { margin-bottom: 4px; }

.muted { color: var(--muted); }
.score { text-align: right; }
.score .value { font-size: 30px; font-weight: 800; }

.bar {
    height: 10px;
    background: var(--line);
    border-radius: 8px;
    overflow: hidden;
}
.bar-fill {
    height: 10px;
    background: var(--primary);
    border-radius: 8px;
}

.kpi {
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 12px;
    background: #fff;
}
.kpi-label { font-size: 12px; color: var(--muted); }
.kpi-value { font-size: 22px; font-weight: 800; }
.kpi-sub { font-size: 12px; color: var(--muted); margin-top: 4px; }

.bar-row {
    display: grid;
    grid-template-columns: 140px 1fr 50px;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
}
.bar-label { color: var(--muted); font-size: 12px; }
.bar-track {
    height: 12px;
    background: var(--line);
    border-radius: 8px;
    overflow: hidden;
}
.bar-fill-blue {
    height: 12px;
    background: var(--accent-a);
    border-radius: 8px;
}
.bar-val { text-align: right; font-size: 12px; }

footer {
    text-align: center;
    color: var(--muted);
    font-size: 12px;
    margin-top: 16px;
}

@page { margin: 0.5in; }
@media print {
    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    body { background: #fff !important; }
    h2, h3 { page-break-after: avoid; }
    li, tr, section { page-break-inside: avoid; }
}
"""


class PDFGeneratorService:
    """Generate PDF reports using WeasyPrint."""

    def __init__(self):
        """Initialize the PDF generator."""
        logger.info("PDFGeneratorService initialized")

    def generate_coaching_report(
        self,
        analysis: Dict[str, Any],
        output_path: str,
    ) -> str:
        """
        Generate coaching report PDF.

        Args:
            analysis: Analysis data from AnalyzerService
            output_path: Path to save PDF

        Returns:
            Path to generated PDF
        """
        html_content = self._build_coaching_html(analysis)
        
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
    ) -> str:
        """
        Generate call stats PDF.

        Args:
            stats: Stats data from AnalyzerService
            output_path: Path to save PDF

        Returns:
            Path to generated PDF
        """
        html_content = self._build_stats_html(stats)
        
        HTML(string=html_content).write_pdf(
            output_path,
            stylesheets=[CSS(string=BASE_CSS)],
        )
        
        logger.info(f"Generated stats report: {output_path}")
        return output_path

    def _build_coaching_html(self, analysis: Dict[str, Any]) -> str:
        """Build HTML for coaching report."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Build highlights list
        highlights = analysis.get("highlights", [])
        highlights_html = ""
        if highlights:
            highlights_html = f"""
            <section>
                <h2>📈 Highlights</h2>
                <ul>
                    {"".join(f"<li>{self._esc(h)}</li>" for h in highlights)}
                </ul>
            </section>
            """

        # Build objection handling
        obj = analysis.get("objection_handling", {})
        objection_html = ""
        if obj.get("objection") or obj.get("improvement"):
            objection_html = f"""
            <section>
                <h2>🧱 Objection Handling</h2>
                <table>
                    <tr><td style="width:140px"><strong>Objection</strong></td><td>{self._esc(obj.get("objection", "None"))}</td></tr>
                    <tr><td><strong>Suggestion</strong></td><td>{self._esc(obj.get("improvement", ""))}</td></tr>
                </table>
            </section>
            """

        # Build coaching commentary
        coaching = analysis.get("coaching", {})
        coaching_html = ""
        if coaching:
            done_well = coaching.get("done_well", [])
            improve = coaching.get("improve", [])
            focus = coaching.get("focus_next", "")
            
            coaching_html = f"""
            <section>
                <h2>🧠 Coaching Commentary</h2>
                {"<div><strong>Done Well:</strong><ul>" + "".join(f"<li>{self._esc(d)}</li>" for d in done_well) + "</ul></div>" if done_well else ""}
                {"<div style='margin-top:12px'><strong>Areas to Improve:</strong><ul>" + "".join(f"<li>{self._esc(i)}</li>" for i in improve) + "</ul></div>" if improve else ""}
                {f'<div class="chip" style="display:inline-block;margin-top:12px">🎯 Focus for Next Call: {self._esc(focus)}</div>' if focus else ""}
            </section>
            """

        # Build timestamp highlights
        ts_highlights = analysis.get("timestamp_highlights", [])
        ts_html = ""
        if ts_highlights:
            ts_html = f"""
            <section>
                <h2>⏱️ Timestamp Highlights</h2>
                <ol>
                    {"".join(f"<li>{self._esc(t)}</li>" for t in ts_highlights)}
                </ol>
            </section>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Sales Call Coaching Report</title>
        </head>
        <body>
            <div class="container">
                <header>
                    <div>
                        <h1>Sales Call Coaching Report</h1>
                        <div class="subtitle">{now}</div>
                    </div>
                </header>

                <section>
                    <h2>🔍 Overall Summary</h2>
                    <p>{self._esc(analysis.get("overall_summary", ""))}</p>
                </section>

                {highlights_html}
                {objection_html}
                {coaching_html}
                {ts_html}

                <footer>
                    Sales Call Analyzer · Generated {now}
                </footer>
            </div>
        </body>
        </html>
        """

    def _build_stats_html(self, stats: Dict[str, Any]) -> str:
        """Build HTML for stats report."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        
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
        max_utt = max(agent_utt, customer_utt, 1)
        
        questions = stats.get("questions", {})
        filler = stats.get("filler", {})

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Call Stats</title>
        </head>
        <body>
            <div class="container">
                <header>
                    <div>
                        <h1>Call Stats</h1>
                        <div class="subtitle">{now} · Duration: {stats.get("duration_min", 0)} min</div>
                    </div>
                    <div class="muted">{self._esc(agent)} vs. {self._esc(customer)}</div>
                </header>

                <section>
                    <h2>Talk Time Distribution</h2>
                    <div class="grid grid-2">
                        <div class="kpi">
                            <div class="kpi-label">{self._esc(agent)} Talk Share</div>
                            <div class="kpi-value">{agent_share}%</div>
                            <div class="kpi-sub">{agent_talk}s</div>
                        </div>
                        <div class="kpi">
                            <div class="kpi-label">{self._esc(customer)} Talk Share</div>
                            <div class="kpi-value">{customer_share}%</div>
                            <div class="kpi-sub">{customer_talk}s</div>
                        </div>
                    </div>
                </section>

                <section>
                    <h2>Speaking Pace (WPM)</h2>
                    <div class="grid grid-2">
                        <div class="kpi">
                            <div class="kpi-label">{self._esc(agent)}</div>
                            <div class="kpi-value">{agent_wpm}</div>
                            <div class="kpi-sub">words per minute</div>
                        </div>
                        <div class="kpi">
                            <div class="kpi-label">{self._esc(customer)}</div>
                            <div class="kpi-value">{customer_wpm}</div>
                            <div class="kpi-sub">words per minute</div>
                        </div>
                    </div>
                </section>

                <section>
                    <h2>Times Spoken</h2>
                    <div class="bar-row">
                        <div class="bar-label">{self._esc(agent)}</div>
                        <div class="bar-track"><div class="bar-fill-blue" style="width:{int(agent_utt/max_utt*100)}%"></div></div>
                        <div class="bar-val">{agent_utt}</div>
                    </div>
                    <div class="bar-row">
                        <div class="bar-label">{self._esc(customer)}</div>
                        <div class="bar-track"><div class="bar-fill-blue" style="width:{int(customer_utt/max_utt*100)}%"></div></div>
                        <div class="bar-val">{customer_utt}</div>
                    </div>
                </section>

                <div class="grid grid-2">
                    <section>
                        <h2>Questions (Rep)</h2>
                        <table>
                            <tr><td>Total Questions</td><td>{questions.get("agent_total", 0)}</td></tr>
                            <tr><td>Rate</td><td>{questions.get("rate_per_min", 0)}/min</td></tr>
                        </table>
                    </section>

                    <section>
                        <h2>Filler Words (Rep)</h2>
                        <table>
                            <tr><td>Total</td><td>{filler.get("agent_count", 0)}</td></tr>
                            <tr><td>Per 100 Words</td><td>{filler.get("agent_per_100_words", 0)}</td></tr>
                        </table>
                    </section>
                </div>

                <section>
                    <h2>Conversation Flow</h2>
                    <table>
                        <tr><td>Speaker Turns</td><td>{stats.get("turns", 0)}</td></tr>
                        <tr><td>Total Duration</td><td>{stats.get("total_duration_sec", 0)}s</td></tr>
                    </table>
                </section>

                <footer>
                    Sales Call Analyzer · Generated {now}
                </footer>
            </div>
        </body>
        </html>
        """

    def _esc(self, text: Any) -> str:
        """Escape HTML special characters."""
        if text is None:
            return ""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

