"""
Email fetcher service using IMAP
"""
import email
import logging
from email.header import decode_header
from datetime import datetime
from typing import List, Dict, Optional
import imapclient
from django.conf import settings
from django.utils import timezone
from apps.emails.models import Email

logger = logging.getLogger(__name__)


class EmailFetcherService:
    """
    Service for fetching emails via IMAP
    """
    
    def __init__(self):
        self.imap_host = settings.EMAIL_IMAP_HOST
        self.imap_port = settings.EMAIL_IMAP_PORT
        self.username = settings.EMAIL_ACCOUNT
        self.password = settings.EMAIL_PASSWORD
    
    def fetch_new_emails(self, mailbox: str = 'INBOX', limit: int = 50) -> List[Email]:
        """
        Fetch new unread emails from mailbox
        
        Args:
            mailbox: IMAP mailbox name (default: INBOX)
            limit: Maximum number of emails to fetch
        
        Returns:
            List of created Email objects
        """
        created_emails = []
        
        try:
            # Connect to IMAP server
            logger.info(f"Connecting to IMAP: {self.imap_host}:{self.imap_port}")
            
            with imapclient.IMAPClient(self.imap_host, port=self.imap_port, ssl=True) as client:
                # Login
                client.login(self.username, self.password)
                logger.info("IMAP login successful")
                
                # Select mailbox
                client.select_folder(mailbox)
                
                # Search for unseen messages
                messages = client.search(['UNSEEN'])
                logger.info(f"Found {len(messages)} unread messages")
                
                # Limit messages
                if len(messages) > limit:
                    messages = messages[-limit:]
                
                if not messages:
                    return created_emails
                
                # Fetch messages
                response = client.fetch(messages, ['RFC822', 'FLAGS', 'INTERNALDATE'])
                
                for msg_id, data in response.items():
                    try:
                        # Parse email
                        email_obj = self._parse_email(data)
                        
                        if email_obj:
                            created_emails.append(email_obj)
                            logger.info(f"Created email: {email_obj.subject[:50]}")
                        
                        # Mark as seen (optional - comment out if you want to keep as unread)
                        # client.add_flags(msg_id, [imapclient.SEEN])
                        
                    except Exception as e:
                        logger.error(f"Error parsing message {msg_id}: {e}")
                        continue
            
            logger.info(f"Successfully fetched {len(created_emails)} emails")
            return created_emails
            
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            raise
    
    def _parse_email(self, data: Dict) -> Optional[Email]:
        """
        Parse raw email data into Email model
        """
        try:
            raw_email = data[b'RFC822']
            email_message = email.message_from_bytes(raw_email)
            
            # Extract message ID
            message_id = email_message.get('Message-ID', '')
            
            # Check if email already exists
            if Email.objects.filter(message_id=message_id).exists():
                logger.info(f"Email already exists: {message_id}")
                return None
            
            # Extract headers
            subject = self._decode_header(email_message.get('Subject', ''))
            from_header = self._decode_header(email_message.get('From', ''))
            to_header = self._decode_header(email_message.get('To', ''))
            date_header = email_message.get('Date')
            
            # Parse from address
            from_email, from_name = self._parse_email_address(from_header)
            to_email, _ = self._parse_email_address(to_header)
            
            # Extract body
            body_text, body_html = self._extract_body(email_message)
            
            # Parse date
            received_at = self._parse_date(date_header)
            
            # Extract thread info
            in_reply_to = email_message.get('In-Reply-To', '')
            thread_id = email_message.get('Thread-Index', '')
            
            # Check for attachments
            has_attachments = False
            attachments_data = []
            
            for part in email_message.walk():
                if part.get_content_disposition() == 'attachment':
                    has_attachments = True
                    filename = part.get_filename()
                    if filename:
                        attachments_data.append({
                            'filename': filename,
                            'content_type': part.get_content_type(),
                            'size': len(part.get_payload(decode=True) or b'')
                        })
            
            # Create Email object
            email_obj = Email.objects.create(
                message_id=message_id,
                from_email=from_email,
                from_name=from_name,
                to_email=to_email or self.username,
                subject=subject,
                body=body_text,
                body_html=body_html,
                received_at=received_at,
                status='new',
                has_attachments=has_attachments,
                attachments_data=attachments_data,
                in_reply_to=in_reply_to,
                thread_id=thread_id,
            )
            
            return email_obj
            
        except Exception as e:
            logger.error(f"Error parsing email: {e}")
            raise
    
    def _decode_header(self, header: str) -> str:
        """Decode email header"""
        if not header:
            return ''
        
        decoded_parts = []
        for part, encoding in decode_header(header):
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(encoding or 'utf-8', errors='ignore'))
            else:
                decoded_parts.append(str(part))
        
        return ''.join(decoded_parts)
    
    def _parse_email_address(self, address_header: str) -> tuple:
        """
        Parse email address from header
        Returns: (email, name)
        """
        if not address_header:
            return '', ''
        
        # Use email.utils to parse
        from email.utils import parseaddr
        name, email_addr = parseaddr(address_header)
        
        return email_addr, name
    
    def _extract_body(self, email_message) -> tuple:
        """
        Extract plain text and HTML body
        Returns: (text_body, html_body)
        """
        text_body = ''
        html_body = ''
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = part.get_content_disposition()
                
                # Skip attachments
                if content_disposition == 'attachment':
                    continue
                
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        decoded_payload = payload.decode(charset, errors='ignore')
                        
                        if content_type == 'text/plain' and not text_body:
                            text_body = decoded_payload
                        elif content_type == 'text/html' and not html_body:
                            html_body = decoded_payload
                except Exception as e:
                    logger.warning(f"Error extracting body part: {e}")
        else:
            # Not multipart
            payload = email_message.get_payload(decode=True)
            if payload:
                charset = email_message.get_content_charset() or 'utf-8'
                text_body = payload.decode(charset, errors='ignore')
        
        # If no text body but has HTML, extract text from HTML
        if not text_body and html_body:
            import re
            # Simple HTML to text conversion
            text_body = re.sub('<[^<]+?>', '', html_body)
            text_body = text_body.replace('&nbsp;', ' ')
        
        return text_body.strip(), html_body.strip()
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse email date header"""
        if not date_str:
            return timezone.now()
        
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception:
            return timezone.now()
    
    def test_connection(self) -> dict:
        """
        Test IMAP connection
        
        Returns:
            dict with status and message
        """
        try:
            with imapclient.IMAPClient(self.imap_host, port=self.imap_port, ssl=True) as client:
                client.login(self.username, self.password)
                folders = client.list_folders()
            
            return {
                'success': True,
                'message': 'IMAP connection successful',
                'folders': [folder[2] for folder in folders]
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Connection error: {str(e)}'
            }