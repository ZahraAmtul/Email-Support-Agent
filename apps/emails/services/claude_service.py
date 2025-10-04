"""
Claude AI service for email classification and reply generation
"""
import os
import json
import re
import logging
import anthropic
from typing import Dict, List, Tuple, Optional
from django.conf import settings
from apps.emails.models import EmailCategory, KnowledgeBase

logger = logging.getLogger(__name__)


class ClaudeEmailAgent:
    """
    AI agent for processing support emails using Claude
    """
    
    def __init__(self):
        self.client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY
        )
        self.model = "claude-sonnet-4-5-20250929"
    
    def mask_sensitive_data(self, text: str) -> Tuple[str, Dict]:
        """
        Mask sensitive information in email text
        Returns: (masked_text, mapping_dict)
        """
        mapping = {}
        masked_text = text
        
        # Mask credit card numbers
        cc_pattern = r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'
        for match in re.finditer(cc_pattern, text):
            masked = f"[CARD_{len(mapping)}]"
            mapping[masked] = match.group()
            masked_text = masked_text.replace(match.group(), masked)
        
        # Mask SSN
        ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
        for match in re.finditer(ssn_pattern, text):
            masked = f"[SSN_{len(mapping)}]"
            mapping[masked] = match.group()
            masked_text = masked_text.replace(match.group(), masked)
        
        # Mask passwords (common patterns)
        password_patterns = [
            r'password[:\s]+(\S+)',
            r'pwd[:\s]+(\S+)',
            r'pass[:\s]+(\S+)',
        ]
        for pattern in password_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                if len(match.groups()) > 0:
                    password = match.group(1)
                    masked = f"[PASSWORD_{len(mapping)}]"
                    mapping[masked] = password
                    masked_text = masked_text.replace(password, masked)
        
        return masked_text, mapping
    
    def unmask_sensitive_data(self, text: str, mapping: Dict) -> str:
        """Restore masked data"""
        result = text
        for masked, original in mapping.items():
            result = result.replace(masked, original)
        return result
    
    def classify_email(self, subject: str, body: str) -> Dict:
        """
        Classify email into categories and extract key information
        
        Returns: {
            'category': str,
            'confidence': float,
            'priority': str,
            'sentiment': str,
            'requires_escalation': bool,
            'escalation_reason': str,
            'extracted_info': dict
        }
        """
        # Mask sensitive data
        masked_body, _ = self.mask_sensitive_data(body)
        
        # Get categories
        categories = list(EmailCategory.objects.values_list('name', flat=True))
        categories_str = ", ".join([cat for cat in categories])
        
        system_prompt = f"""You are an expert email classification system for customer support.

Your task is to analyze incoming support emails and provide structured classification.

Available categories: {categories_str}

You must respond with ONLY valid JSON in this exact format:
{{
    "category": "one of the available categories",
    "confidence": 0.0 to 1.0,
    "priority": "low/medium/high/urgent",
    "sentiment": "positive/neutral/negative",
    "requires_escalation": true/false,
    "escalation_reason": "reason if escalation needed, empty string otherwise",
    "extracted_info": {{
        "customer_name": "extracted or empty",
        "order_id": "extracted or empty",
        "account_id": "extracted or empty",
        "issue_summary": "brief summary",
        "key_points": ["point1", "point2"]
    }}
}}

Classification Guidelines:
- billing: Payment issues, invoices, refunds, pricing questions
- technical: Product not working, bugs, errors, technical problems
- sales: Product inquiries, pricing, demos, purchase questions
- general: FAQs, general questions, information requests
- complaint: Dissatisfaction, complaints, negative feedback
- feature_request: Suggestions, feature requests, improvements

Priority Guidelines:
- urgent: System down, payment failed, security issue, angry customer
- high: Significant impact, time-sensitive, frustrated customer
- medium: Standard issues, normal concerns
- low: General questions, minor issues

Escalation Guidelines (requires_escalation = true):
- Legal threats or demands
- Requests for refunds over $500
- Security or privacy concerns
- Regulatory compliance issues
- Extremely negative sentiment with threat to leave
- Complex technical issues beyond standard troubleshooting

CRITICAL: Respond ONLY with the JSON object. No other text before or after."""

        user_prompt = f"""Subject: {subject}

Body:
{masked_body}

Analyze this email and provide classification."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            # Extract JSON from response
            response_text = response.content[0].text.strip()
            
            # Remove markdown code blocks if present
            response_text = response_text.replace('```json\n', '').replace('\n```', '').strip()
            
            # Parse JSON
            result = json.loads(response_text)
            
            logger.info(f"Email classified: {result['category']} (confidence: {result['confidence']})")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude JSON response: {e}")
            logger.error(f"Response text: {response_text}")
            # Return default classification
            return {
                'category': 'general',
                'confidence': 0.5,
                'priority': 'medium',
                'sentiment': 'neutral',
                'requires_escalation': False,
                'escalation_reason': '',
                'extracted_info': {'issue_summary': 'Classification failed'}
            }
        except Exception as e:
            logger.error(f"Error classifying email: {e}")
            raise
    
    def generate_reply(self, 
                      subject: str, 
                      body: str, 
                      category: str,
                      customer_name: Optional[str] = None,
                      knowledge_articles: Optional[List[KnowledgeBase]] = None) -> Dict:
        """
        Generate reply to email
        
        Returns: {
            'reply': str,
            'confidence': float,
            'requires_review': bool,
            'used_articles': list
        }
        """
        # Mask sensitive data
        masked_body, mapping = self.mask_sensitive_data(body)
        
        # Prepare knowledge base context
        kb_context = ""
        if knowledge_articles:
            kb_context = "\n\nKnowledge Base Articles:\n"
            for article in knowledge_articles[:5]:  # Limit to top 5
                kb_context += f"\n--- Article: {article.title} ---\n{article.content}\n"
        
        system_prompt = f"""You are a professional customer support agent responding to customer emails.

Category: {category}

Guidelines:
- Be professional, empathetic, and helpful
- Use the customer's name if provided
- Address all points raised in the email
- Provide clear, actionable solutions
- Be concise but thorough
- Use knowledge base articles when available
- Maintain a friendly but professional tone
- If you cannot fully resolve the issue, explain next steps clearly

{kb_context}

IMPORTANT: 
- Do not make promises you cannot keep
- Do not provide refunds or discounts without proper authority
- For complex issues, suggest escalation to specialized team
- Do not include any sensitive information in the response

Respond with ONLY valid JSON:
{{
    "reply": "the email reply text",
    "confidence": 0.0 to 1.0,
    "requires_review": true/false,
    "reasoning": "brief explanation of confidence level",
    "used_articles": ["article title 1", "article title 2"]
}}

Confidence Guidelines:
- 0.9-1.0: Standard FAQ or simple question with clear KB article
- 0.7-0.89: Common issue with good KB coverage
- 0.5-0.69: Moderate complexity, some uncertainty
- Below 0.5: Complex issue, requires human review (set requires_review: true)

Requires Review (true) if:
- Confidence below 0.7
- Involves refunds, discounts, or compensation
- Legal or compliance issues
- Technical issue without clear solution
- Negative sentiment with potential churn risk"""

        customer_greeting = f"Dear {customer_name}," if customer_name else "Hello,"
        
        user_prompt = f"""Customer Email:
Subject: {subject}
Body: {masked_body}

Generate a professional reply to this customer email."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            # Extract JSON
            response_text = response.content[0].text.strip()
            response_text = response_text.replace('```json\n', '').replace('\n```', '').strip()
            
            result = json.loads(response_text)
            
            # Unmask any sensitive data (though there shouldn't be any in reply)
            result['reply'] = self.unmask_sensitive_data(result['reply'], mapping)
            
            # Add greeting
            result['reply'] = f"{customer_greeting}\n\n{result['reply']}"
            
            logger.info(f"Reply generated with confidence: {result['confidence']}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude JSON response: {e}")
            raise
        except Exception as e:
            logger.error(f"Error generating reply: {e}")
            raise
    
    def analyze_sentiment(self, text: str) -> Dict:
        """
        Perform detailed sentiment analysis
        
        Returns: {
            'sentiment': 'positive/neutral/negative',
            'confidence': float,
            'urgency_level': int (1-5),
            'emotion_tags': list
        }
        """
        system_prompt = """Analyze the sentiment and urgency of this customer email.

Respond with ONLY valid JSON:
{
    "sentiment": "positive/neutral/negative",
    "confidence": 0.0 to 1.0,
    "urgency_level": 1 to 5,
    "emotion_tags": ["frustrated", "angry", "confused", etc.],
    "reasoning": "brief explanation"
}

Urgency Levels:
1 - No urgency, general question
2 - Minor issue, can wait
3 - Moderate issue, needs response soon
4 - Important issue, time-sensitive
5 - Critical issue, immediate attention needed"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": text}
                ]
            )
            
            response_text = response.content[0].text.strip()
            response_text = response_text.replace('```json\n', '').replace('\n```', '').strip()
            
            return json.loads(response_text)
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return {
                'sentiment': 'neutral',
                'confidence': 0.5,
                'urgency_level': 3,
                'emotion_tags': []
            }