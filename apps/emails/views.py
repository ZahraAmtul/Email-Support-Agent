"""
API Views for Email Management
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q, Count
import logging

from apps.emails.models import (
    Email, EmailReply, EmailCategory, 
    KnowledgeBase
)
from apps.emails.serializers import (
    EmailListSerializer, EmailDetailSerializer,
    EmailReplySerializer, EmailCategorySerializer,
    KnowledgeBaseSerializer, ReplyApprovalSerializer
)
from apps.emails.services.email_sender import EmailSenderService
from apps.emails.tasks import process_email_task

logger = logging.getLogger(__name__)


class EmailViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing emails
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'category', 'priority', 'assigned_to', 'requires_escalation']
    search_fields = ['from_email', 'subject', 'body']
    ordering_fields = ['received_at', 'created_at', 'priority']
    ordering = ['-received_at']
    
    def get_queryset(self):
        queryset = Email.objects.select_related(
            'category', 'assigned_to'
        ).prefetch_related('replies')
        
        # Filter by status if provided
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'list':
            return EmailListSerializer
        return EmailDetailSerializer
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign email to an agent"""
        email_obj = self.get_object()
        user_id = request.data.get('user_id')
        
        try:
            from django.contrib.auth.models import User
            user = User.objects.get(id=user_id)
            
            email_obj.assigned_to = user
            email_obj.assigned_at = timezone.now()
            email_obj.status = 'processing'
            email_obj.save()
            
            return Response({
                'message': f'Email assigned to {user.get_full_name()}',
                'email': EmailDetailSerializer(email_obj).data
            })
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def reprocess(self, request, pk=None):
        """Reprocess email with AI"""
        email_obj = self.get_object()
        
        # Queue for processing
        process_email_task.delay(email_obj.id)
        
        return Response({
            'message': 'Email queued for reprocessing',
            'email_id': email_obj.id
        })
    
    @action(detail=True, methods=['post'])
    def escalate(self, request, pk=None):
        """Manually escalate email"""
        email_obj = self.get_object()
        reason = request.data.get('reason', 'Manual escalation')
        
        email_obj.requires_escalation = True
        email_obj.escalation_reason = reason
        email_obj.status = 'escalated'
        email_obj.save()
        
        return Response({
            'message': 'Email escalated successfully',
            'email': EmailDetailSerializer(email_obj).data
        })
    
    @action(detail=True, methods=['post'])
    def mark_spam(self, request, pk=None):
        """Mark email as spam"""
        email_obj = self.get_object()
        
        email_obj.status = 'spam'
        email_obj.save()
        
        return Response({
            'message': 'Email marked as spam'
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get email statistics"""
        queryset = self.get_queryset()
        
        stats = {
            'total': queryset.count(),
            'new': queryset.filter(status='new').count(),
            'processing': queryset.filter(status='processing').count(),
            'pending_review': queryset.filter(status='pending_review').count(),
            'replied': queryset.filter(status='replied').count(),
            'escalated': queryset.filter(status='escalated').count(),
            'closed': queryset.filter(status='closed').count(),
            'by_category': list(
                queryset.values('category__name').annotate(count=Count('id'))
            ),
            'by_priority': list(
                queryset.values('priority').annotate(count=Count('id'))
            ),
        }
        
        return Response(stats)


class EmailReplyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing email replies
    """
    permission_classes = [IsAuthenticated]
    serializer_class = EmailReplySerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['email', 'status', 'source']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return EmailReply.objects.select_related(
            'email', 'created_by', 'reviewed_by'
        ).prefetch_related('knowledge_base_articles')
    
    def perform_create(self, serializer):
        """Set created_by when creating reply"""
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Approve, reject, or modify a reply"""
        reply_obj = self.get_object()
        serializer = ReplyApprovalSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        action_type = data['action']
        
        try:
            if action_type == 'approve':
                reply_obj.status = 'approved'
                reply_obj.reviewed_by = request.user
                reply_obj.reviewed_at = timezone.now()
                reply_obj.review_notes = data.get('review_notes', '')
                reply_obj.save()
                
                # Send if requested
                if data.get('send_immediately'):
                    sender = EmailSenderService()
                    sender.send_reply(reply_obj.email, reply_obj)
                
                return Response({
                    'message': 'Reply approved' + (' and sent' if data.get('send_immediately') else ''),
                    'reply': EmailReplySerializer(reply_obj).data
                })
            
            elif action_type == 'reject':
                reply_obj.status = 'rejected'
                reply_obj.reviewed_by = request.user
                reply_obj.reviewed_at = timezone.now()
                reply_obj.review_notes = data.get('review_notes', '')
                reply_obj.save()
                
                return Response({
                    'message': 'Reply rejected',
                    'reply': EmailReplySerializer(reply_obj).data
                })
            
            elif action_type == 'modify':
                # Create new reply with modifications
                new_reply = EmailReply.objects.create(
                    email=reply_obj.email,
                    body=data['modified_body'],
                    source='ai_modified',
                    status='approved',
                    created_by=request.user,
                    reviewed_by=request.user,
                    reviewed_at=timezone.now(),
                    review_notes=data.get('review_notes', 'Modified from AI suggestion')
                )
                
                # Mark old reply as rejected
                reply_obj.status = 'rejected'
                reply_obj.review_notes = 'Modified version created'
                reply_obj.save()
                
                # Send if requested
                if data.get('send_immediately'):
                    sender = EmailSenderService()
                    sender.send_reply(new_reply.email, new_reply)
                
                return Response({
                    'message': 'Reply modified and saved',
                    'reply': EmailReplySerializer(new_reply).data
                })
        
        except Exception as e:
            logger.error(f"Error reviewing reply: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Send an approved reply"""
        reply_obj = self.get_object()
        
        if reply_obj.status != 'approved':
            return Response(
                {'error': 'Reply must be approved before sending'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            sender = EmailSenderService()
            sender.send_reply(reply_obj.email, reply_obj)
            
            return Response({
                'message': 'Reply sent successfully',
                'reply': EmailReplySerializer(reply_obj).data
            })
        
        except Exception as e:
            logger.error(f"Error sending reply: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EmailCategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing email categories
    """
    permission_classes = [IsAuthenticated]
    queryset = EmailCategory.objects.all()
    serializer_class = EmailCategorySerializer
    ordering = ['name']


class KnowledgeBaseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing knowledge base articles
    """
    permission_classes = [IsAuthenticated]
    serializer_class = KnowledgeBaseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_active']
    search_fields = ['title', 'content', 'keywords']
    ordering = ['-use_count', '-created_at']
    
    def get_queryset(self):
        return KnowledgeBase.objects.select_related('category', 'created_by')
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def search_by_keywords(self, request):
        """Search knowledge base by keywords"""
        keywords = request.query_params.get('keywords', '').split(',')
        
        queryset = self.get_queryset().filter(
            is_active=True,
            keywords__overlap=keywords
        )
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)