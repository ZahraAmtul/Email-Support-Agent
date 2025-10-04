"""
Email sender service using SMTP
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
from django.conf import settings
from django.utils import timezone
from apps.emails.models import Email, EmailReply

logger = logging.getLogger(__name__)


class EmailSenderService:
    """
    Service for sending emails via SMTP
    """
    
    def __init__(self):
        self.smtp_host = settings.EMAIL_SMTP_HOST
        self.smtp_port = settings.EMAIL_SMTP_PORT
        self.from_email = settings.EMAIL_FROM
        self.username = settings.EMAIL_ACCOUNT
        self.password = settings.EMAIL_PASSWORD
        self.use_tls = settings.EMAIL_USE_TLS
    
    def send_reply(self, 
                   email_obj: Email, 
                   reply_obj: EmailReply,
                   cc: Optional[List[str]] = None,
                   bcc: Optional[List[str]] = None) -> bool:
        """
        Send reply email to customer
        
        Args:
            email_obj: Original email object
            reply_obj: Reply object with content
            cc: List of CC email addresses
            bcc: List of BCC email addresses
        
        Returns:
            bool: True if sent successfully
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = email_obj.from_email
            msg['Subject'] = f"Re: {email_obj.subject}"
            
            # Add CC and BCC
            if cc:
                msg['Cc'] = ', '.join(cc)
            if bcc:
                msg['Bcc'] = ', '.join(bcc)
            
            # Add In-Reply-To and References headers for threading
            if email_obj.message_id:
                msg['In-Reply-To'] = email_obj.message_id
                msg['References'] = email_obj.message_id
            
            # Add reply content
            # Create plain text version
            text_part = MIMEText(reply_obj.body, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # Create HTML version
            html_body = self._create_html_email(reply_obj.body, email_obj)
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Connect to SMTP server
            logger.info(f"Connecting to SMTP server: {self.smtp_host}:{self.smtp_port}")
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                
                # Login
                server.login(self.username, self.password)
                
                # Send email
                recipients = [email_obj.from_email]
                if cc:
                    recipients.extend(cc)
                if bcc:
                    recipients.extend(bcc)
                
                server.send_message(msg, self.from_email, recipients)
                
                logger.info(f"Email sent successfully to {email_obj.from_email}")
            
            # Update reply status
            reply_obj.status = 'sent'
            reply_obj.sent_at = timezone.now()
            reply_obj.save()
            
            # Update email status
            email_obj.status = 'replied'
            email_obj.replied_at = timezone.now()
            email_obj.save()
            
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP Authentication failed: {e}")
            raise Exception("Email authentication failed. Please check credentials.")
        
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error occurred: {e}")
            raise Exception(f"Failed to send email: {str(e)}")
        
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            raise
    
    def _create_html_email(self, body: str, original_email: Email) -> str:
        """
        Create HTML version of email with professional styling
        """
        # Convert line breaks to HTML
        html_body = body.replace('\n', '<br>')
        
        html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .email-container {{
            background-color: #ffffff;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .email-body {{
            margin: 20px 0;
            font-size: 14px;
        }}
        .signature {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            font-size: 13px;
            color: #666;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            font-size: 12px;
            color: #999;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="email-body">
            {html_body}
        </div>
        
        <div class="signature">
            <strong>Support Team</strong><br>
            {self.from_email}<br>
        </div>
        
        <div class="footer">
            <p>This is an automated response from our support system.</p>
            <p>If you need further assistance, please reply to this email.</p>
        </div>
    </div>
</body>
</html>
"""
        return html_template
    
    def send_notification(self, 
                         to_email: str, 
                         subject: str, 
                         body: str,
                         html_body: Optional[str] = None) -> bool:
        """
        Send a notification email (e.g., to agents about escalations)
        """
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Add plain text
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # Add HTML if provided
            if html_body:
                html_part = MIMEText(html_body, 'html', 'utf-8')
                msg.attach(html_part)
            
            # Send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            logger.info(f"Notification sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False
    
    def test_connection(self) -> dict:
        """
        Test SMTP connection and credentials
        
        Returns:
            dict with status and message
        """
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
            
            return {
                'success': True,
                'message': 'SMTP connection successful'
            }
        except smtplib.SMTPAuthenticationError:
            return {
                'success': False,
                'message': 'Authentication failed. Check credentials.'
            }
        except smtplib.SMTPException as e:
            return {
                'success': False,
                'message': f'SMTP error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Connection error: {str(e)}'
            }