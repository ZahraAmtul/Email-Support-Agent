"""
Celery tasks for email processing
"""
import logging
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from datetime import timedelta

from apps.emails.models import Email, EmailReply, EmailCategory, KnowledgeBase, EmailProcessingLog
from apps.emails.services.email_fetcher import EmailFetcherService
from apps.emails.services.claude_service import ClaudeEmailAgent
from apps.emails.services.email_sender import EmailSenderService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def fetch_emails_task(self):
    """
    Periodic task to fetch new emails from IMAP
    """
    try:
        logger.info("Starting email fetch task...")
        
        fetcher = EmailFetcherService()
        new_emails = fetcher.fetch_new_emails(limit=50)
        
        logger.info(f"Fetched {len(new_emails)} new emails")
        
        # Queue processing for each email
        for email_obj in new_emails:
            process_email_task.delay(email_obj.id)
        
        return {
            'success': True,
            'emails_fetched': len(new_emails),
            'message': f'Successfully fetched {len(new_emails)} emails'
        }
        
    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def process_email_task(self, email_id):
    """
    Process a single email: classify and generate reply
    """
    start_time = timezone.now()
    
    try:
        email = Email.objects.get(id=email_id)
        logger.info(f"Processing email: {email.subject[:50]}")
        
        # Update status
        email.status = 'processing'
        email.save()
        
        # Log: Started classification
        EmailProcessingLog.objects.create(
            email=email,
            step='classification',
            status='started',
            details={'started_at': start_time.isoformat()}
        )
        
        # Step 1: Classify email
        agent = ClaudeEmailAgent()
        classification = agent.classify_email(email.subject, email.body)
        
        # Update email with classification
        category = EmailCategory.objects.filter(name=classification['category']).first()
        email.category = category
        email.priority = classification['priority']
        email.ai_sentiment = classification['sentiment']
        email.ai_classification_confidence = classification['confidence']
        email.requires_escalation = classification['requires_escalation']
        email.escalation_reason = classification.get('escalation_reason', '')
        email.ai_extracted_info = classification.get('extracted_info', {})
        email.processed_at = timezone.now()
        email.save()
        
        # Log: Classification completed
        EmailProcessingLog.objects.create(
            email=email,
            step='classification',
            status='completed',
            details=classification,
            processing_time=(timezone.now() - start_time).total_seconds()
        )
        
        logger.info(f"Email classified as: {classification['category']} (confidence: {classification['confidence']})")
        
        # Step 2: Generate reply (if not escalated)
        if not email.requires_escalation:
            reply_start = timezone.now()
            
            # Log: Started reply generation
            EmailProcessingLog.objects.create(
                email=email,
                step='reply_generation',
                status='started',
                details={'started_at': reply_start.isoformat()}
            )
            
            # Get relevant knowledge base articles
            kb_articles = []
            if category:
                kb_articles = list(
                    KnowledgeBase.objects.filter(
                        category=category,
                        is_active=True
                    ).order_by('-use_count')[:3]
                )
            
            # Extract customer name
            customer_name = email.ai_extracted_info.get('customer_name', email.from_name)
            
            # Generate reply
            reply_data = agent.generate_reply(
                email.subject,
                email.body,
                classification['category'],
                customer_name,
                kb_articles
            )
            
            # Create EmailReply object
            reply = EmailReply.objects.create(
                email=email,
                body=reply_data['reply'],
                source='ai',
                ai_confidence=reply_data['confidence'],
                status='pending_approval' if reply_data['requires_review'] else 'draft'
            )
            
            # Link knowledge base articles
            if kb_articles:
                reply.knowledge_base_articles.set(kb_articles)
                # Increment use count
                for article in kb_articles:
                    article.use_count += 1
                    article.save()
                    # Log: Reply generation completed
            EmailProcessingLog.objects.create(
                email=email,
                step='reply_generation',
                status='completed',
                details={
                    'confidence': reply_data['confidence'],
                    'requires_review': reply_data['requires_review'],
                    'used_articles': reply_data.get('used_articles', [])
                },
                processing_time=(timezone.now() - reply_start).total_seconds()
            )
            
            logger.info(f"Reply generated with confidence: {reply_data['confidence']}")
            
            # Auto-approve and send if confidence is high enough
            if (reply_data['confidence'] >= settings.EMAIL_AUTO_REPLY_THRESHOLD and 
                not reply_data['requires_review']):
                
                reply.status = 'approved'
                reply.save()
                
                # Send email automatically
                try:
                    sender = EmailSenderService()
                    sender.send_reply(email, reply)
                    
                    logger.info(f"Reply auto-sent for email: {email.subject[:50]}")
                    
                    # Log: Auto-send completed
                    EmailProcessingLog.objects.create(
                        email=email,
                        step='auto_send',
                        status='completed',
                        details={'reply_id': reply.id}
                    )
                except Exception as send_error:
                    logger.error(f"Error auto-sending reply: {send_error}")
                    EmailProcessingLog.objects.create(
                        email=email,
                        step='auto_send',
                        status='failed',
                        error_message=str(send_error)
                    )
            else:
                # Mark email for review
                email.status = 'pending_review'
                email.save()
                logger.info(f"Email marked for review: {email.subject[:50]}")
        
        else:
            # Email requires escalation
            email.status = 'escalated'
            email.save()
            logger.info(f"Email escalated: {email.subject[:50]}")
            
            # Send notification to admins
            send_escalation_notification_task.delay(email_id)
        
        return {
            'success': True,
            'email_id': email_id,
            'category': classification['category'],
            'requires_escalation': email.requires_escalation
        }
        
    except Email.DoesNotExist:
        logger.error(f"Email not found: {email_id}")
        return {'success': False, 'error': 'Email not found'}
    
    except Exception as e:
        logger.error(f"Error processing email {email_id}: {e}")
        
        # Log error
        try:
            email = Email.objects.get(id=email_id)
            EmailProcessingLog.objects.create(
                email=email,
                step='processing',
                status='failed',
                error_message=str(e)
            )
            email.status = 'new'  # Reset to new for retry
            email.save()
        except:
            pass
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@shared_task
def send_escalation_notification_task(email_id):
    """
    Send notification to admins about escalated email
    """
    try:
        email = Email.objects.get(id=email_id)
        
        # Get admin emails
        from django.contrib.auth.models import User
        admin_emails = User.objects.filter(
            is_staff=True, 
            is_active=True
        ).values_list('email', flat=True)
        
        if not admin_emails:
            logger.warning("No admin emails found for escalation notification")
            return
        
        sender = EmailSenderService()
        
        subject = f"[ESCALATION] {email.subject}"
        body = f"""
An email has been escalated and requires immediate attention.

From: {email.from_name} ({email.from_email})
Subject: {email.subject}
Priority: {email.get_priority_display()}
Category: {email.category.get_name_display() if email.category else 'Unknown'}
Reason: {email.escalation_reason}

Sentiment: {email.get_ai_sentiment_display() if email.ai_sentiment else 'Unknown'}
Received: {email.received_at.strftime('%Y-%m-%d %H:%M:%S')}

View email: {settings.ALLOWED_HOSTS[0]}/dashboard/email/{email.id}/

---
Email Body:
{email.body[:500]}...
"""
        
        for admin_email in admin_emails:
            sender.send_notification(admin_email, subject, body)
        
        logger.info(f"Escalation notification sent for email {email_id}")
        
    except Exception as e:
        logger.error(f"Error sending escalation notification: {e}")


@shared_task
def cleanup_old_logs_task():
    """
    Clean up old processing logs (older than 90 days)
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=90)
        
        deleted_count = EmailProcessingLog.objects.filter(
            created_at__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} old processing logs")
        
        return {
            'success': True,
            'deleted_count': deleted_count
        }
    
    except Exception as e:
        logger.error(f"Error cleaning up logs: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def bulk_process_emails_task(email_ids):
    """
    Process multiple emails in bulk
    """
    results = []
    for email_id in email_ids:
        result = process_email_task.delay(email_id)
        results.append(result.id)
    
    return {
        'success': True,
        'task_ids': results,
        'count': len(results)
    }