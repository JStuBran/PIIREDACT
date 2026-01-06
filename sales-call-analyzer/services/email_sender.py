"""Email Sender service - SMTP and Resend support."""

import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

logger = logging.getLogger(__name__)


class EmailSenderService:
    """Send emails via SMTP or Resend API."""

    def __init__(self):
        """Initialize email sender based on available configuration."""
        # Check for Resend first (easier to set up)
        self.resend_api_key = os.environ.get("RESEND_API_KEY")
        self.resend_from = os.environ.get("RESEND_FROM", "noreply@yourdomain.com")
        
        # SMTP configuration
        self.smtp_host = os.environ.get("SMTP_HOST")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user = os.environ.get("SMTP_USER")
        self.smtp_pass = os.environ.get("SMTP_PASS")
        self.smtp_from = os.environ.get("SMTP_FROM", self.smtp_user)
        
        # Determine which method to use
        if self.resend_api_key:
            self.method = "resend"
            logger.info("EmailSenderService using Resend API")
        elif self.smtp_host and self.smtp_user:
            self.method = "smtp"
            logger.info(f"EmailSenderService using SMTP ({self.smtp_host})")
        else:
            self.method = "none"
            logger.warning("EmailSenderService: No email configuration found")

    def send_magic_link(self, to_email: str, magic_link: str) -> bool:
        """
        Send magic link login email.

        Args:
            to_email: Recipient email
            magic_link: The magic link URL

        Returns:
            True if sent successfully
        """
        subject = "Your Login Link - Sales Call Analyzer"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 480px; margin: 0 auto; padding: 20px; }}
                .button {{ display: inline-block; background: #0f62fe; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Login to Sales Call Analyzer</h2>
                <p>Click the button below to log in. This link expires in 15 minutes.</p>
                <p style="margin: 24px 0;">
                    <a href="{magic_link}" class="button">Log In</a>
                </p>
                <p class="footer">
                    If you didn't request this link, you can safely ignore this email.<br>
                    Link: {magic_link}
                </p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        Login to Sales Call Analyzer
        
        Click the link below to log in (expires in 15 minutes):
        {magic_link}
        
        If you didn't request this link, you can safely ignore this email.
        """
        
        return self._send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

    def send_report(
        self,
        to_email: str,
        subject: str,
        coaching_pdf_path: str,
        stats_pdf_path: str,
    ) -> bool:
        """
        Send analysis report with PDF attachments.

        Args:
            to_email: Recipient email
            subject: Email subject
            coaching_pdf_path: Path to coaching report PDF
            stats_pdf_path: Path to stats report PDF

        Returns:
            True if sent successfully
        """
        html_body = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 480px; margin: 0 auto; padding: 20px; }
                .footer { margin-top: 30px; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Your Call Analysis is Ready</h2>
                <p>Great news! Your sales call has been analyzed. Please find attached:</p>
                <ul>
                    <li><strong>Coaching Report</strong> - Personalized feedback and improvement suggestions</li>
                    <li><strong>Call Stats</strong> - Detailed metrics about the conversation</li>
                </ul>
                <p>Review the reports and focus on the "Focus for Next Call" recommendation.</p>
                <p class="footer">
                    Sales Call Analyzer<br>
                    Questions? Reply to this email.
                </p>
            </div>
        </body>
        </html>
        """
        
        text_body = """
        Your Call Analysis is Ready
        
        Great news! Your sales call has been analyzed. Please find attached:
        
        - Coaching Report - Personalized feedback and improvement suggestions
        - Call Stats - Detailed metrics about the conversation
        
        Review the reports and focus on the "Focus for Next Call" recommendation.
        
        ---
        Sales Call Analyzer
        """
        
        attachments = []
        if coaching_pdf_path and os.path.exists(coaching_pdf_path):
            attachments.append(("Coaching_Report.pdf", coaching_pdf_path))
        if stats_pdf_path and os.path.exists(stats_pdf_path):
            attachments.append(("Call_Stats.pdf", stats_pdf_path))
        
        return self._send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            attachments=attachments,
        )

    def _send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        attachments: Optional[List[tuple]] = None,
    ) -> bool:
        """
        Send email using configured method.

        Args:
            to_email: Recipient
            subject: Subject line
            html_body: HTML content
            text_body: Plain text content
            attachments: List of (filename, filepath) tuples

        Returns:
            True if sent
        """
        if self.method == "resend":
            return self._send_via_resend(to_email, subject, html_body, attachments)
        elif self.method == "smtp":
            return self._send_via_smtp(to_email, subject, html_body, text_body, attachments)
        else:
            logger.warning(f"No email method configured. Would send to: {to_email}")
            return False

    def _send_via_resend(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        attachments: Optional[List[tuple]] = None,
    ) -> bool:
        """Send email via Resend API."""
        try:
            import resend
            resend.api_key = self.resend_api_key
            
            params = {
                "from": self.resend_from,
                "to": [to_email],
                "subject": subject,
                "html": html_body,
            }
            
            # Add attachments
            if attachments:
                params["attachments"] = []
                for filename, filepath in attachments:
                    with open(filepath, "rb") as f:
                        import base64
                        content = base64.b64encode(f.read()).decode("utf-8")
                        params["attachments"].append({
                            "filename": filename,
                            "content": content,
                        })
            
            resend.Emails.send(params)
            logger.info(f"Email sent via Resend to: {to_email}")
            return True
            
        except Exception as e:
            logger.exception(f"Resend email failed: {e}")
            return False

    def _send_via_smtp(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        attachments: Optional[List[tuple]] = None,
    ) -> bool:
        """Send email via SMTP."""
        try:
            msg = MIMEMultipart("mixed")
            msg["From"] = self.smtp_from
            msg["To"] = to_email
            msg["Subject"] = subject
            
            # Create alternative part for text/html
            alt_part = MIMEMultipart("alternative")
            alt_part.attach(MIMEText(text_body, "plain"))
            alt_part.attach(MIMEText(html_body, "html"))
            msg.attach(alt_part)
            
            # Add attachments
            if attachments:
                for filename, filepath in attachments:
                    with open(filepath, "rb") as f:
                        part = MIMEApplication(f.read(), Name=filename)
                        part["Content-Disposition"] = f'attachment; filename="{filename}"'
                        msg.attach(part)
            
            # Send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
            
            logger.info(f"Email sent via SMTP to: {to_email}")
            return True
            
        except Exception as e:
            logger.exception(f"SMTP email failed: {e}")
            return False

