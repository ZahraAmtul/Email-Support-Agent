"""
Dashboard views for web interface
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta

from apps.emails.models import Email, EmailReply, EmailCategory
from apps.emails.services.email_sender import EmailSenderService
from apps.analytics.models import DailyMetrics


@login_required
def dashboard_home(request):
    """Main dashboard view"""
    # Get date range
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    
    # Statistics
    total_emails = Email.objects.count()
    new_emails = Email.objects.filter(status='new').count()
    pending_review = Email.objects.filter(status='pending_review').count()
    escalated = Email.objects.filter(status='escalated').count()
    
    # Recent metrics
    recent_metrics = DailyMetrics.objects.filter(date__gte=week_ago).order_by('-date')[:7]
    
    # Calculate totals
    week_totals = {
        'emails_received': sum(m.total_emails_received for m in recent_metrics),
        'emails_replied': sum(m.total_emails_replied for m in recent_metrics),
        'ai_approved': sum(m.ai_approved_replies for m in recent_metrics),
        'time_saved': sum(m.estimated_time_saved_hours for m in recent_metrics),
    }
    
    # Automation rate
    if week_totals['emails_received'] > 0:
        automation_rate = (week_totals['ai_approved'] / week_totals['emails_received']) * 100
    else:
        automation_rate = 0
    
    context = {
        'total_emails': total_emails,
        'new_emails': new_emails,
        'pending_review': pending_review,
        'escalated': escalated,
        'week_totals': week_totals,
        'automation_rate': round(automation_rate, 1),
        'recent_metrics': recent_metrics,
    }
    
    return render(request, 'dashboard/home.html', context)


@login_required
def inbox(request):
    """Email inbox view"""
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('q', '')
    
    # Base queryset
    emails = Email.objects.select_related('category', 'assigned_to').order_by('-received_at')
    
    # Apply filters
    if status_filter:
        emails = emails.filter(status=status_filter)
    if category_filter:
        emails = emails.filter(category__name=category_filter)
    if search_query:
        emails = emails.filter(
            Q(from_email__icontains=search_query) |
            Q(subject__icontains=search_query) |
            Q(body__icontains=search_query)
        )
    
    # Get categories for filter dropdown
    categories = EmailCategory.objects.all()
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(emails, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'categories': categories,
        'status_filter': status_filter,
        'category_filter': category_filter,
        'search_query': search_query,
        'status_choices': Email.STATUS_CHOICES,
    }
    
    return render(request, 'dashboard/inbox.html', context)


@login_required
def email_detail(request, email_id):
    """Email detail view"""
    email = get_object_or_404(
        Email.objects.select_related('category', 'assigned_to')
        .prefetch_related('replies', 'processing_logs'),
        id=email_id
    )
    
    # Get replies
    replies = email.replies.select_related('created_by', 'reviewed_by').order_by('-created_at')
    
    # Get processing logs
    logs = email.processing_logs.order_by('created_at')
    
    context = {
        'email': email,
        'replies': replies,
        'logs': logs,
    }
    
    return render(request, 'dashboard/email_detail.html', context)


@login_required
def approve_reply(request, reply_id):
    """Approve and optionally send a reply"""
    if request.method != 'POST':
        return redirect('dashboard:inbox')
    
    reply = get_object_or_404(EmailReply, id=reply_id)
    
    # Update reply status
    reply.status = 'approved'
    reply.reviewed_by = request.user
    reply.reviewed_at = timezone.now()
    reply.save()
    
    # Send email if requested
    if request.POST.get('send_now') == 'true':
        try:
            sender = EmailSenderService()
            sender.send_reply(reply.email, reply)
            messages.success(request, 'Reply approved and sent successfully!')
        except Exception as e:
            messages.error(request, f'Reply approved but failed to send: {str(e)}')
    else:
        messages.success(request, 'Reply approved successfully!')
    
    return redirect('dashboard:email_detail', email_id=reply.email.id)


@login_required
def reject_reply(request, reply_id):
    """Reject a reply"""
    if request.method != 'POST':
        return redirect('dashboard:inbox')
    
    reply = get_object_or_404(EmailReply, id=reply_id)
    
    reply.status = 'rejected'
    reply.reviewed_by = request.user
    reply.reviewed_at = timezone.now()
    reply.review_notes = request.POST.get('notes', '')
    reply.save()
    
    messages.success(request, 'Reply rejected.')
    return redirect('dashboard:email_detail', email_id=reply.email.id)


@login_required
def analytics(request):
    """Analytics dashboard"""
    # Date range
    days = int(request.GET.get('days', 30))
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)
    
    # Get metrics
    daily_metrics = DailyMetrics.objects.filter(
        date__gte=start_date
    ).order_by('date')
    
    # Calculate totals
    totals = {
        'emails_received': sum(m.total_emails_received for m in daily_metrics),
        'emails_replied': sum(m.total_emails_replied for m in daily_metrics),
        'ai_suggestions': sum(m.ai_suggested_replies for m in daily_metrics),
        'ai_approved': sum(m.ai_approved_replies for m in daily_metrics),
        'time_saved': sum(m.estimated_time_saved_hours for m in daily_metrics),
        'cost_saved': sum(float(m.estimated_cost_saved) for m in daily_metrics),
    }
    
    # Calculate rates
    if totals['ai_suggestions'] > 0:
        approval_rate = (totals['ai_approved'] / totals['ai_suggestions']) * 100
    else:
        approval_rate = 0
    
    if totals['emails_received'] > 0:
        automation_rate = (totals['ai_approved'] / totals['emails_received']) * 100
    else:
        automation_rate = 0
    
    context = {
        'days': days,
        'daily_metrics': daily_metrics,
        'totals': totals,
        'approval_rate': round(approval_rate, 1),
        'automation_rate': round(automation_rate, 1),
    }
    
    return render(request, 'dashboard/analytics.html', context)