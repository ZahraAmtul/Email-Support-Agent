"""
Analytics tasks for generating metrics
"""
import logging
from celery import shared_task
from django.utils import timezone
from django.db.models import Avg, Count, Sum, F
from datetime import timedelta
from decimal import Decimal

from apps.analytics.models import DailyMetrics, CategoryMetrics, AgentPerformance
from apps.emails.models import Email, EmailReply, EmailCategory

logger = logging.getLogger(__name__)


@shared_task
def generate_daily_metrics_task(date=None):
    """
    Generate daily metrics for analytics
    """
    try:
        target_date = date or timezone.now().date() - timedelta(days=1)
        
        logger.info(f"Generating metrics for {target_date}")
        
        # Get emails for the date
        emails = Email.objects.filter(received_at__date=target_date)
        
        # Count emails by status
        total_received = emails.count()
        total_processed = emails.exclude(processed_at__isnull=True).count()
        total_replied = emails.filter(status='replied').count()
        total_escalations = emails.filter(requires_escalation=True).count()
        
        # Get reply statistics
        replies = EmailReply.objects.filter(created_at__date=target_date)
        
        ai_suggested = replies.filter(source='ai').count()
        ai_approved = replies.filter(source='ai', status='approved').count()
        ai_modified = replies.filter(source='ai_modified').count()
        ai_rejected = replies.filter(source='ai', status='rejected').count()
        
        # Calculate average response time
        replied_emails = emails.filter(
            replied_at__isnull=False
        ).annotate(
            response_time_seconds=(
                F('replied_at') - F('received_at')
            ).total_seconds()
        )
        
        avg_response_time = None
        if replied_emails.exists():
            avg_seconds = replied_emails.aggregate(
                avg=Avg('response_time_seconds')
            )['avg']
            if avg_seconds:
                avg_response_time = avg_seconds / 3600  # Convert to hours
        
        # Estimate time saved (assume 10 minutes per manual email)
        minutes_per_email = 10
        time_saved_hours = (ai_approved * minutes_per_email) / 60
        
        # Estimate cost saved (assume $30/hour for support agent)
        hourly_rate = 30
        cost_saved = Decimal(time_saved_hours * hourly_rate)
        
        # Create or update daily metrics
        metrics, created = DailyMetrics.objects.update_or_create(
            date=target_date,
            defaults={
                'total_emails_received': total_received,
                'total_emails_processed': total_processed,
                'total_emails_replied': total_replied,
                'ai_suggested_replies': ai_suggested,
                'ai_approved_replies': ai_approved,
                'ai_modified_replies': ai_modified,
                'ai_rejected_replies': ai_rejected,
                'total_escalations': total_escalations,
                'avg_response_time': avg_response_time,
                'estimated_time_saved_hours': time_saved_hours,
                'estimated_cost_saved': cost_saved,
            }
        )
        
        logger.info(f"{'Created' if created else 'Updated'} metrics for {target_date}")
        
        # Generate category metrics
        generate_category_metrics_task.delay(str(target_date))
        
        # Generate agent performance metrics
        generate_agent_performance_task.delay(str(target_date))
        
        return {
            'success': True,
            'date': str(target_date),
            'metrics': {
                'total_received': total_received,
                'ai_approved': ai_approved,
                'time_saved_hours': round(time_saved_hours, 2),
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating daily metrics: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def generate_category_metrics_task(date_str):
    """
    Generate metrics by category
    """
    try:
        target_date = timezone.datetime.fromisoformat(date_str).date()
        
        categories = EmailCategory.objects.all()
        
        for category in categories:
            emails = Email.objects.filter(
                received_at__date=target_date,
                category=category
            )
            
            email_count = emails.count()
            
            if email_count == 0:
                continue
            
            # Calculate average response time
            replied = emails.filter(replied_at__isnull=False)
            avg_response = None
            if replied.exists():
                avg_seconds = sum(
                    (e.replied_at - e.received_at).total_seconds() 
                    for e in replied
                ) / replied.count()
                avg_response = avg_seconds / 3600
            
            # Calculate AI success rate
            total_replies = EmailReply.objects.filter(
                email__in=emails,
                source='ai'
            ).count()
            
            approved_replies = EmailReply.objects.filter(
                email__in=emails,
                source='ai',
                status='approved'
            ).count()
            
            ai_success_rate = 0
            if total_replies > 0:
                ai_success_rate = (approved_replies / total_replies) * 100
            
            # Escalation rate
            escalations = emails.filter(requires_escalation=True).count()
            escalation_rate = (escalations / email_count) * 100
            
            # Create or update
            CategoryMetrics.objects.update_or_create(
                date=target_date,
                category=category,
                defaults={
                    'email_count': email_count,
                    'avg_response_time': avg_response,
                    'ai_success_rate': ai_success_rate,
                    'escalation_rate': escalation_rate,
                }
            )
        
        logger.info(f"Generated category metrics for {target_date}")
        return {'success': True}
        
    except Exception as e:
        logger.error(f"Error generating category metrics: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def generate_agent_performance_task(date_str):
    """
    Generate agent performance metrics
    """
    try:
        from django.contrib.auth.models import User
        
        target_date = timezone.datetime.fromisoformat(date_str).date()
        
        agents = User.objects.filter(is_staff=True, is_active=True)
        
        for agent in agents:
            # Get emails handled by agent
            emails_handled = Email.objects.filter(
                assigned_to=agent,
                assigned_at__date=target_date
            ).count()
            
            # Get replies reviewed by agent
            replies = EmailReply.objects.filter(
                reviewed_by=agent,
                reviewed_at__date=target_date
            )
            
            ai_approved = replies.filter(
                source='ai',
                status='approved'
            ).count()
            
            ai_modified = replies.filter(
                source='ai_modified'
            ).count()
            
            ai_rejected = replies.filter(
                source='ai',
                status='rejected'
            ).count()
            
            manual_replies = EmailReply.objects.filter(
                created_by=agent,
                created_at__date=target_date,
                source='human'
            ).count()
            
            # Calculate average review time
            reviewed_replies = replies.exclude(reviewed_at__isnull=True)
            avg_review_time = None
            
            if reviewed_replies.exists():
                total_seconds = sum(
                    (r.reviewed_at - r.created_at).total_seconds()
                    for r in reviewed_replies
                )
                avg_review_time = (total_seconds / reviewed_replies.count()) / 60  # Minutes
            
            # Create or update
            AgentPerformance.objects.update_or_create(
                agent=agent,
                date=target_date,
                defaults={
                    'emails_handled': emails_handled,
                    'ai_replies_approved': ai_approved,
                    'ai_replies_modified': ai_modified,
                    'ai_replies_rejected': ai_rejected,
                    'manual_replies': manual_replies,
                    'avg_review_time': avg_review_time,
                }
            )
        
        logger.info(f"Generated agent performance metrics for {target_date}")
        return {'success': True}
        
    except Exception as e:
        logger.error(f"Error generating agent performance: {e}")
        return {'success': False, 'error': str(e)}