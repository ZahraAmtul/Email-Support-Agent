"""
Email models for the support system
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


class EmailCategory(models.Model):
    """Categories for email classification"""
    
    CATEGORY_CHOICES = [
        ('billing', 'Billing'),
        ('technical', 'Technical Issue'),
        ('sales', 'Sales Inquiry'),
        ('general', 'General Inquiry'),
        ('complaint', 'Complaint'),
        ('feature_request', 'Feature Request'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=50, choices=CATEGORY_CHOICES, unique=True)
    description = models.TextField(blank=True)
    keywords = models.JSONField(default=list, help_text="Keywords for classification")
    auto_reply_enabled = models.BooleanField(default=False)
    escalation_required = models.BooleanField(default=False)
    sla_hours = models.IntegerField(default=24, help_text="SLA response time in hours")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Email Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.get_name_display()


class KnowledgeBase(models.Model):
    """Knowledge base for generating responses"""
    
    category = models.ForeignKey(
        EmailCategory, 
        on_delete=models.CASCADE, 
        related_name='knowledge_articles'
    )
    title = models.CharField(max_length=255)
    content = models.TextField(help_text="Response template or information")
    keywords = models.JSONField(default=list)
    use_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "Knowledge Base"
        ordering = ['-use_count', '-created_at']
    
    def __str__(self):
        return self.title


class Email(models.Model):
    """Main email model"""
    
    STATUS_CHOICES = [
        ('new', 'New'),
        ('processing', 'Processing'),
        ('pending_review', 'Pending Review'),
        ('replied', 'Replied'),
        ('escalated', 'Escalated'),
        ('closed', 'Closed'),
        ('spam', 'Spam'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    # Email metadata
    message_id = models.CharField(max_length=255, unique=True)
    from_email = models.EmailField()
    from_name = models.CharField(max_length=255, blank=True)
    to_email = models.EmailField()
    subject = models.CharField(max_length=500)
    body = models.TextField()
    body_html = models.TextField(blank=True)
    
    # Processing
    category = models.ForeignKey(
        EmailCategory, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    
    # AI Analysis
    ai_classification_confidence = models.FloatField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    ai_sentiment = models.CharField(
        max_length=20, 
        choices=[('positive', 'Positive'), ('neutral', 'Neutral'), ('negative', 'Negative')],
        null=True,
        blank=True
    )
    ai_extracted_info = models.JSONField(default=dict, blank=True)
    requires_escalation = models.BooleanField(default=False)
    escalation_reason = models.TextField(blank=True)
    
    # Assignment
    assigned_to = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_emails'
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    received_at = models.DateTimeField()
    processed_at = models.DateTimeField(null=True, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Attachments
    has_attachments = models.BooleanField(default=False)
    attachments_data = models.JSONField(default=list, blank=True)
    
    # Thread tracking
    thread_id = models.CharField(max_length=255, blank=True)
    in_reply_to = models.CharField(max_length=255, blank=True)
    
    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['-received_at']),
            models.Index(fields=['status']),
            models.Index(fields=['from_email']),
            models.Index(fields=['category']),
        ]
    
    def __str__(self):
        return f"{self.from_email} - {self.subject[:50]}"
    
    def get_response_time(self):
        """Calculate response time in hours"""
        if self.replied_at and self.received_at:
            delta = self.replied_at - self.received_at
            return delta.total_seconds() / 3600
        return None
    
    def is_overdue(self):
        """Check if email is overdue based on SLA"""
        if self.status in ['replied', 'closed']:
            return False
        
        if self.category and self.category.sla_hours:
            sla_deadline = self.received_at + timezone.timedelta(hours=self.category.sla_hours)
            return timezone.now() > sla_deadline
        return False


class EmailReply(models.Model):
    """AI-generated or human replies to emails"""
    
    SOURCE_CHOICES = [
        ('ai', 'AI Generated'),
        ('human', 'Human Written'),
        ('ai_modified', 'AI Modified by Human'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('sent', 'Sent'),
        ('rejected', 'Rejected'),
    ]
    
    email = models.ForeignKey(Email, on_delete=models.CASCADE, related_name='replies')
    
    # Reply content
    body = models.TextField()
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='ai')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # AI metrics
    ai_confidence = models.FloatField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    knowledge_base_articles = models.ManyToManyField(
        KnowledgeBase, 
        blank=True,
        related_name='used_in_replies'
    )
    
    # Review & approval
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='created_replies'
    )
    reviewed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reviewed_replies'
    )
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Sending
    sent_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Email Replies"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Reply to: {self.email.subject[:50]}"


class EmailProcessingLog(models.Model):
    """Log of email processing steps"""
    
    email = models.ForeignKey(Email, on_delete=models.CASCADE, related_name='processing_logs')
    step = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20, 
        choices=[('started', 'Started'), ('completed', 'Completed'), ('failed', 'Failed')]
    )
    details = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    processing_time = models.FloatField(null=True, blank=True, help_text="Time in seconds")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.email.message_id} - {self.step} - {self.status}"