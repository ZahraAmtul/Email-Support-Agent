"""
Analytics models for tracking metrics
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from apps.emails.models import EmailCategory


class DailyMetrics(models.Model):
    """Daily aggregated metrics"""
    
    date = models.DateField(unique=True)
    
    # Email volume
    total_emails_received = models.IntegerField(default=0)
    total_emails_processed = models.IntegerField(default=0)
    total_emails_replied = models.IntegerField(default=0)
    
    # AI performance
    ai_suggested_replies = models.IntegerField(default=0)
    ai_approved_replies = models.IntegerField(default=0)
    ai_modified_replies = models.IntegerField(default=0)
    ai_rejected_replies = models.IntegerField(default=0)
    
    # Response times (in hours)
    avg_response_time = models.FloatField(null=True, blank=True)
    median_response_time = models.FloatField(null=True, blank=True)
    
    # Escalations
    total_escalations = models.IntegerField(default=0)
    
    # Cost savings (estimated)
    estimated_time_saved_hours = models.FloatField(default=0)
    estimated_cost_saved = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Daily Metrics"
        ordering = ['-date']
    
    def __str__(self):
        return f"Metrics for {self.date}"
    
    @property
    def ai_approval_rate(self):
        """Calculate AI approval rate"""
        if self.ai_suggested_replies == 0:
            return 0
        return (self.ai_approved_replies / self.ai_suggested_replies) * 100
    
    @property
    def automation_rate(self):
        """Calculate automation rate"""
        if self.total_emails_processed == 0:
            return 0
        return (self.ai_approved_replies / self.total_emails_processed) * 100


class CategoryMetrics(models.Model):
    """Metrics by category"""
    
    date = models.DateField()
    category = models.ForeignKey(EmailCategory, on_delete=models.CASCADE)
    
    email_count = models.IntegerField(default=0)
    avg_response_time = models.FloatField(null=True, blank=True)
    ai_success_rate = models.FloatField(default=0)
    escalation_rate = models.FloatField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Category Metrics"
        unique_together = ['date', 'category']
        ordering = ['-date', 'category']
    
    def __str__(self):
        return f"{self.category} - {self.date}"


class AgentPerformance(models.Model):
    """Track individual agent performance"""
    
    agent = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    
    emails_handled = models.IntegerField(default=0)
    ai_replies_approved = models.IntegerField(default=0)
    ai_replies_modified = models.IntegerField(default=0)
    ai_replies_rejected = models.IntegerField(default=0)
    manual_replies = models.IntegerField(default=0)
    
    avg_review_time = models.FloatField(null=True, blank=True, help_text="Minutes")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Agent Performance"
        unique_together = ['agent', 'date']
        ordering = ['-date', 'agent']
    
    def __str__(self):
        return f"{self.agent.username} - {self.date}"