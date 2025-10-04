"""
Analytics API Views
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Avg, Count, Sum
from django.utils import timezone
from datetime import timedelta

from apps.analytics.models import DailyMetrics, CategoryMetrics, AgentPerformance
from apps.analytics.serializers import (
    DailyMetricsSerializer, CategoryMetricsSerializer, AgentPerformanceSerializer
)
from apps.emails.models import Email, EmailReply


class AnalyticsViewSet(viewsets.ViewSet):
    """
    ViewSet for analytics and reporting
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Get dashboard overview statistics"""
        # Date range
        days = int(request.query_params.get('days', 7))
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Email stats
        emails = Email.objects.filter(received_at__date__gte=start_date)
        
        stats = {
            'overview': {
                'total_emails': emails.count(),
                'new': emails.filter(status='new').count(),
                'processing': emails.filter(status='processing').count(),
                'replied': emails.filter(status='replied').count(),
                'escalated': emails.filter(status='escalated').count(),
            },
            'ai_performance': {
                'total_suggestions': EmailReply.objects.filter(
                    created_at__date__gte=start_date,
                    source='ai'
                ).count(),
                'approved': EmailReply.objects.filter(
                    created_at__date__gte=start_date,
                    source='ai',
                    status='approved'
                ).count(),
                'modified': EmailReply.objects.filter(
                    created_at__date__gte=start_date,
                    source='ai_modified'
                ).count(),
                'rejected': EmailReply.objects.filter(
                    created_at__date__gte=start_date,
                    source='ai',
                    status='rejected'
                ).count(),
            },
            'response_times': {
                'average_hours': emails.exclude(
                    replied_at__isnull=True
                ).aggregate(
                    avg_time=Avg('replied_at') - Avg('received_at')
                )
            },
            'categories': list(
                emails.values('category__name').annotate(
                    count=Count('id')
                ).order_by('-count')
            ),
            'daily_trend': list(
                DailyMetrics.objects.filter(
                    date__gte=start_date
                ).order_by('date').values(
                    'date', 'total_emails_received', 'total_emails_replied',
                    'ai_approved_replies', 'automation_rate'
                )
            )
        }
        
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def cost_savings(self, request):
        """Calculate estimated cost savings"""
        days = int(request.query_params.get('days', 30))
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        metrics = DailyMetrics.objects.filter(date__gte=start_date)
        
        total_savings = metrics.aggregate(
            total_hours=Sum('estimated_time_saved_hours'),
            total_cost=Sum('estimated_cost_saved')
        )
        
        return Response({
            'period_days': days,
            'total_hours_saved': total_savings['total_hours'] or 0,
            'total_cost_saved': total_savings['total_cost'] or 0,
            'average_per_day': (total_savings['total_hours'] or 0) / days,
        })


class DailyMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for daily metrics"""
    permission_classes = [IsAuthenticated]
    queryset = DailyMetrics.objects.all()
    serializer_class = DailyMetricsSerializer
    ordering = ['-date']


class CategoryMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for category metrics"""
    permission_classes = [IsAuthenticated]
    queryset = CategoryMetrics.objects.all()
    serializer_class = CategoryMetricsSerializer
    ordering = ['-date']


class AgentPerformanceViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for agent performance"""
    permission_classes = [IsAuthenticated]
    queryset = AgentPerformance.objects.all()
    serializer_class = AgentPerformanceSerializer
    ordering = ['-date']