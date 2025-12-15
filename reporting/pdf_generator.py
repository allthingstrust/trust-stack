"""
PDF report generator for Trust Stack Rating tool
Creates professional PDF reports with charts and analysis
"""

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.platypus import Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from typing import Dict, Any, List
import logging
from datetime import datetime
import io
import re
import requests
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import os

from config.settings import SETTINGS

# ============================================================================
# EMOJI HANDLING FOR PDF
# ============================================================================
# ReportLab's default fonts (Helvetica) don't support emoji Unicode characters.
# We convert emojis to readable text labels for PDF compatibility.

# Comprehensive emoji-to-text mapping for PDF rendering
EMOJI_TO_TEXT = {
    # Trust Stack icons
    '🧠': '(BRAIN)',
    '🗝️': '(KEY)',
    '🗝': '(KEY)',
    '🔑': '(KEY)',
    '✨': '(STAR)',
    '🧮': '(CALC)',
    '📊': '(CHART)',
    '🛠️': '(TOOLS)',
    '📄': '(DOC)',
    '🔐': '(LOCK)',
    '📣': '(ANNOUNCE)',
    '🔍': '(SEARCH)',
    '📌': '(PIN)',
    '⭐': '(STAR)',
    # Status indicators
    '✅': '[OK]',
    '⚠️': '[WARN]',
    '❌': '[X]',
    '🟢': '[GREEN]',
    '🟡': '[YELLOW]',
    '🟠': '[ORANGE]',
    '🔴': '[RED]',
    '🚫': '[BLOCKED]',
    # Platform icons
    '🏢': '(OFFICE)',
    '👥': '(PEOPLE)',
    '🛒': '(CART)',
    '📧': '(EMAIL)',
    '🌐': '(WEB)',
    '❓': '(?)',
    # Misc
    '●': '*',
    '•': '*',
}

# Global flag to track if emoji font is loaded
HAS_EMOJI_FONT = False


def clean_emoji_for_pdf(text: str) -> str:
    """
    Process emojis for PDF rendering.
    
    If Noto Emoji font is available, wraps emojis in font tags.
    Otherwise, replaces them with text equivalents or strips them.
    """
    if not text:
        return text
        
    if HAS_EMOJI_FONT:
        # If font is loaded, wrap emojis in font tag instead of replacing them
        # We still need to help ReportLab by explicitly switching fonts for emoji characters
        
        # Regex for emoji characters
        # Matches: Emoticons, Symbols & Pictographs, Transport, specific ranges
        emoji_pattern = re.compile(
            r'('
            r'[\U0001F600-\U0001F64F]|'  # Emoticons
            r'[\U0001F300-\U0001F5FF]|'  # Symbols & Pictographs
            r'[\U0001F680-\U0001F6FF]|'  # Transport & Map
            r'[\U0001F1E0-\U0001F1FF]|'  # Flags
            r'[\U0001F900-\U0001F9FF]|'  # Supplemental Symbols
            r'[\U0001FA00-\U0001FA6F]|'  # Chess Symbols
            r'[\U0001FA70-\U0001FAFF]|'  # Symbols Extended-A
            r'[\U00002702-\U000027B0]|'  # Dingbats
            r'[\U000024C2-\U0001F251]'   # Enclosed Ideographic Supplement
            r')+'
        )
        
        def wrap_emoji(match):
            # Strip variation selectors from the match before wrapping
            # This helps NotoEmoji (monochrome) render correctly
            content = match.group(0).replace('\ufe0f', '').replace('\ufe0e', '')
            return f'<font face="NotoEmoji">{content}</font>'
            
        return emoji_pattern.sub(wrap_emoji, text)
    
    # Fallback to text replacement
    # Apply known emoji replacements
    for emoji, replacement in EMOJI_TO_TEXT.items():
        text = text.replace(emoji, replacement)
    
    # Remove any remaining emoji Unicode characters that we don't have mappings for
    text = re.sub(r'[\U0001F600-\U0001F64F]', '', text)
    text = re.sub(r'[\U0001F300-\U0001F5FF]', '', text)
    text = re.sub(r'[\U0001F680-\U0001F6FF]', '', text)
    text = re.sub(r'[\U0001F1E0-\U0001F1FF]', '', text)
    text = re.sub(r'[\U0001F900-\U0001F9FF]', '', text)
    text = re.sub(r'[\U0001FA00-\U0001FA6F]', '', text)
    text = re.sub(r'[\U0001FA70-\U0001FAFF]', '', text)
    text = re.sub(r'[\U00002702-\U000027B0]', '', text)
    text = re.sub(r'[\U0000FE00-\U0000FE0F]', '', text)
    
    return text

logger = logging.getLogger(__name__)

# Helper function for generating data-driven recommendations
def generate_rating_recommendation_pdf(avg_rating: float, dimension_breakdown: Dict[str, Any]) -> str:
    """
    Generate data-driven recommendation for PDF based on dimension analysis.

    Args:
        avg_rating: Average rating score (0-100)
        dimension_breakdown: Dictionary with dimension averages

    Returns:
        Comprehensive recommendation string
    """
    # Define dimension details
    dimension_info = {
        'provenance': {
            'name': 'Provenance',
            'recommendation': 'implement structured metadata (schema.org markup), add clear author attribution, and include publication timestamps on all content',
            'description': 'origin tracking and metadata'
        },
        'verification': {
            'name': 'Verification',
            'recommendation': 'fact-check claims against authoritative sources, add citations and references, and link to verifiable external data',
            'description': 'factual accuracy'
        },
        'transparency': {
            'name': 'Transparency',
            'recommendation': 'add disclosure statements, clearly identify sponsored content, and provide detailed attribution for all sources',
            'description': 'disclosure and clarity'
        },
        'coherence': {
            'name': 'Coherence',
            'recommendation': 'audit messaging consistency across all channels, align visual branding, and ensure unified voice in customer communications',
            'description': 'cross-channel consistency'
        },
        'resonance': {
            'name': 'Resonance',
            'recommendation': 'increase authentic engagement with your audience, reduce promotional language, and ensure cultural relevance in messaging',
            'description': 'audience engagement'
        }
    }

    # Find lowest-performing dimension
    dimension_keys = ['provenance', 'verification', 'transparency', 'coherence', 'resonance']
    dimension_scores = {
        key: dimension_breakdown.get(key, {}).get('average', 0.5) * 100  # Convert to 0-100 scale
        for key in dimension_keys
    }

    # Find the dimension with the lowest score
    if dimension_scores:
        lowest_dim_key = min(dimension_scores, key=dimension_scores.get)
        lowest_dim_score = dimension_scores[lowest_dim_key]
        lowest_dim_info = dimension_info[lowest_dim_key]

        # Generate comprehensive summary based on rating band
        if avg_rating >= 80:
            # Excellent - maintain standards with minor optimization
            return f"To reach even greater heights, consider optimizing {lowest_dim_info['name']} (currently at {lowest_dim_score:.1f}/100) by continuing to {lowest_dim_info['recommendation']}."

        elif avg_rating >= 60:
            # Good - focus on improvement area
            return f"To improve from Good to Excellent, focus on enhancing {lowest_dim_info['name']} (currently at {lowest_dim_score:.1f}/100) by taking action to {lowest_dim_info['recommendation']}."

        elif avg_rating >= 40:
            # Fair - requires focused attention
            return f"To mitigate weak {lowest_dim_info['description']}, you should {lowest_dim_info['recommendation']}. This will help move your rating from Fair to Good or Excellent."

        else:
            # Poor - immediate action needed
            return f"Critical issue detected in {lowest_dim_info['name']} (scoring only {lowest_dim_score:.1f}/100). You must {lowest_dim_info['recommendation']} to improve trust signals and content quality."

    else:
        # Fallback if no dimension data available
        return "Comprehensive dimension analysis is recommended to provide specific improvement actions."

# Helper to coerce item-like objects into dicts so callers can use .get()
def _coerce_item_to_dict(item):
    if isinstance(item, dict):
        return item
    try:
        d = {}
        for k in dir(item):
            if k.startswith('_'):
                continue
            try:
                v = getattr(item, k)
            except Exception:
                continue
            if callable(v):
                continue
            try:
                d[k] = v
            except Exception:
                continue
        return d
    except Exception:
        try:
            return dict(item)
        except Exception:
            return {}

# Optional: reuse markdown generator's LLM helper if available
try:
    from reporting.markdown_generator import _llm_summarize, clean_text_for_llm, add_llm_provenance
except Exception:
    _llm_summarize = None
    add_llm_provenance = None
    def clean_text_for_llm(meta):
        try:
            return '\n\n'.join([str(meta.get(k)) for k in ('title', 'description', 'snippet', 'body') if meta.get(k)])
        except Exception:
            return ''

# Import Trust Stack report generator for rich content
try:
    from reporting.trust_stack_report import generate_trust_stack_report
except Exception:
    generate_trust_stack_report = None

class PDFReportGenerator:
    """Generates PDF reports for Trust Stack Rating analysis"""
    
    def __init__(self):
        self._register_fonts()
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _register_fonts(self):
        """Register NotoEmoji font if available"""
        global HAS_EMOJI_FONT
        try:
            # Look for font in assets/fonts
            base_dir = os.path.dirname(os.path.dirname(__file__))
            font_path = os.path.join(base_dir, 'assets', 'fonts', 'NotoEmoji-Regular.ttf')
            
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('NotoEmoji', font_path))
                HAS_EMOJI_FONT = True
                logger.info(f"Successfully registered NotoEmoji font from {font_path}")
            else:
                logger.warning(f"NotoEmoji font not found at {font_path}. Emojis will be replaced with text.")
        except Exception as e:
            logger.error(f"Failed to register NotoEmoji font: {e}")
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.darkblue
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceAfter=12,
            textColor=colors.darkblue
        ))
        
        self.styles.add(ParagraphStyle(
            name='KPI',
            parent=self.styles['Heading2'],
            fontSize=18,
            spaceAfter=6,
            alignment=TA_CENTER,
            textColor=colors.darkgreen
        ))
        
        # Additional styles for Trust Stack content
        self.styles.add(ParagraphStyle(
            name='DimensionHeader',
            parent=self.styles['Heading3'],
            fontSize=14,
            spaceAfter=8,
            spaceBefore=12,
            textColor=colors.HexColor('#1a5276')
        ))
        
        self.styles.add(ParagraphStyle(
            name='TrustStackBody',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=4,
            leading=12
        ))
        
        self.styles.add(ParagraphStyle(
            name='TrustStackBullet',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=3,
            leftIndent=20,
            bulletIndent=10,
            leading=11
        ))
        
        self.styles.add(ParagraphStyle(
            name='TableText',
            parent=self.styles['Normal'],
            fontSize=8,
            leading=10
        ))
    
    def generate_report(self, report_data: Dict[str, Any], output_path: str, include_items_table: bool = False) -> str:
        """
        Generate PDF report from report data - simplified to match web app layout.

        Args:
            report_data: Dictionary containing report data
            output_path: Path to save the PDF file
            include_items_table: Whether to include detailed items table (ignored in simplified format)

        Returns:
            Path to generated PDF file
        """
        logger.info(f"Generating PDF report (web app format): {output_path}")

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=36
        )

        story = []

        # =========================================================================
        # HEADER SECTION (matches web app)
        # =========================================================================
        
        # Title: Trust Stack Results
        story.append(Paragraph(clean_emoji_for_pdf("⭐ Trust Stack Results"), self.styles['CustomTitle']))
        story.append(Spacer(1, 10))
        
        # Date
        from datetime import datetime
        current_date = report_data.get('generated_at', datetime.now().strftime("%B %d, %Y"))
        story.append(Paragraph(f"<b>Date:</b> {current_date}", self.styles['Normal']))
        story.append(Spacer(1, 15))
        
        # Brand name
        brand_id = report_data.get('brand_id', 'Unknown Brand')
        brand_name_display = brand_id.replace('_', ' ').replace('-', ' ').title()
        story.append(Paragraph(brand_name_display, self.styles['SectionHeader']))
        story.append(Spacer(1, 8))
        
        # NOTE: Data Sources section removed - URLs are surfaced throughout the report
        # and in the Content Items Detail table
        items = report_data.get('items', [])
        
        # Description
        total_items = len(items)
        description = f"This report evaluates <b>{total_items} content items</b> across five trust dimensions."
        story.append(Paragraph(description, self.styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Divider line
        from reportlab.platypus import HRFlowable
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 20))
        
        # =========================================================================
        # TRUST STACK REPORT SECTION (main content - matches web app)
        # =========================================================================
        
        story.extend(self._create_trust_stack_section(report_data))
        
        # =========================================================================
        # CONTENT ITEMS TABLE (simplified)
        # =========================================================================
        
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 15))
        story.append(Paragraph("Content Items Detail", self.styles['SectionHeader']))
        story.append(Spacer(1, 10))
        
        if items:
            # Create simplified items table with clickable Source column
            table_data = [['Source', 'Title', 'Score', 'Rating']]
            
            for item in items[:50]:  # Limit to 50 items for PDF
                meta = item.get('meta', {})
                if isinstance(meta, str):
                    try:
                        import json
                        meta = json.loads(meta) if meta else {}
                    except:
                        meta = {}
                
                source_text = str(item.get('source', '')).upper()[:10]
                title = (meta.get('title') or meta.get('name') or 'N/A')[:40]
                if len(title) == 40:
                    title += '...'
                    
                score = item.get('final_score', 0)
                
                if score >= 80:
                    rating = 'Excellent'
                elif score >= 60:
                    rating = 'Good'
                elif score >= 40:
                    rating = 'Fair'
                else:
                    rating = 'Poor'
                
                # Extract URL from metadata and make Source clickable
                url = meta.get('source_url') or meta.get('url') or meta.get('link') or ''
                
                if url and url.startswith('http'):
                    # Make Source text a clickable link
                    source_cell = Paragraph(
                        f'<a href="{url}" color="blue"><u>{source_text}</u></a>',
                        self.styles['TableText']
                    )
                else:
                    source_cell = Paragraph(source_text, self.styles['TableText'])
                
                table_data.append([source_cell, title, f"{score:.1f}", rating])
            
            table = Table(table_data, colWidths=[0.8*inch, 3*inch, 0.8*inch, 1*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(table)
        
        # Build PDF
        doc.build(story)

        logger.info(f"PDF report generated successfully: {output_path}")
        return output_path
    
    def _create_title_page(self, report_data: Dict[str, Any]) -> List:
        """Create title page"""
        story = []

        # Main title
        story.append(Paragraph("Trust Stack Rating Report", self.styles['CustomTitle']))
        story.append(Spacer(1, 20))

        # Brand information
        brand_id = report_data.get('brand_id', 'Unknown Brand')
        story.append(Paragraph(f"Brand: {brand_id}", self.styles['Heading2']))
        story.append(Spacer(1, 10))

        # Report metadata
        run_id = report_data.get('run_id', 'Unknown')
        generated_at = report_data.get('generated_at', datetime.now().isoformat())

        sources = report_data.get('sources', [])
        sources_display = ', '.join(sources) if sources else 'Unknown'

        metadata = [
            ['Report ID:', run_id],
            ['Generated:', generated_at],
            ['Analysis Period:', 'Current Run'],
            ['Data Sources:', sources_display],
            ['Rubric Version:', report_data.get('rubric_version', 'v2.0-trust-stack')]
        ]

        metadata_table = Table(metadata, colWidths=[2*inch, 3*inch])
        metadata_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        story.append(metadata_table)
        story.append(Spacer(1, 30))

        # Key metrics preview - focus on Trust Stack Rating
        items = report_data.get('items', [])
        total_items = len(items)

        # Calculate average rating
        if items:
            avg_rating = sum(item.get('final_score', 0) for item in items) / len(items)
        else:
            avg_rating = 0

        # Calculate rating distribution
        excellent = sum(1 for item in items if item.get('final_score', 0) >= 80)
        good = sum(1 for item in items if 60 <= item.get('final_score', 0) < 80)
        fair = sum(1 for item in items if 40 <= item.get('final_score', 0) < 60)
        poor = sum(1 for item in items if item.get('final_score', 0) < 40)

        story.append(Paragraph("Summary", self.styles['SectionHeader']))
        story.append(Paragraph(f"Average Rating: {avg_rating:.1f}/100", self.styles['KPI']))
        story.append(Paragraph(f"Total Content Analyzed: {total_items:,}", self.styles['Normal']))
        story.append(Spacer(1, 10))

        # Rating band summary
        rating_summary = f"Rating Distribution: {excellent} Excellent | {good} Good | {fair} Fair | {poor} Poor"
        story.append(Paragraph(rating_summary, self.styles['Normal']))

        # Executive one-liner
        if avg_rating >= 80:
            quality = "excellent"
        elif avg_rating >= 60:
            quality = "good"
        elif avg_rating >= 40:
            quality = "fair"
        else:
            quality = "requires immediate attention"

        executive_one_liner = f"Executive Summary: Average content rating of {avg_rating:.1f}/100 indicates {quality} brand content quality across {total_items} analyzed items."
        story.append(Spacer(1, 6))
        story.append(Paragraph(executive_one_liner, self.styles['Normal']))

        # Add concrete example from the data with actionable guidance
        story.append(Spacer(1, 12))
        if items:
            items_coerced = [_coerce_item_to_dict(it) for it in items]
            dimension_breakdown = report_data.get('dimension_breakdown', {})

            # Find a content item that needs improvement (score < 60)
            items_needing_improvement = [it for it in items_coerced if it.get('final_score', 0) < 60]

            if items_needing_improvement:
                # Get the first item needing improvement
                example_item = items_needing_improvement[0]
                meta = example_item.get('meta', {})
                title = meta.get('title') or meta.get('url') or 'content item'
                if len(title) > 60:
                    title = title[:57] + '...'

                item_score = example_item.get('final_score', 0)
                dim_scores = example_item.get('dimension_scores', {})

                # Find the weakest dimension for this item
                if dim_scores:
                    weakest_dim = min(dim_scores.items(), key=lambda x: x[1] if x[1] is not None else 1.0)
                    weakest_dim_name = weakest_dim[0].replace('_', ' ').title()
                    weakest_dim_score = weakest_dim[1] * 100 if weakest_dim[1] is not None else 0

                    # Map dimension to specific action
                    dim_actions = {
                        'provenance': 'add clear author attribution, publication date, and schema.org markup',
                        'verification': 'add citations to authoritative sources and fact-check all claims',
                        'transparency': 'add disclosure statements and clear attribution for all sourced information',
                        'coherence': 'ensure messaging aligns with your brand voice across all channels',
                        'resonance': 'reduce promotional language and increase culturally relevant messaging; add structured data markup and improve semantic HTML for better machine discoverability'
                    }

                    action = dim_actions.get(weakest_dim[0], 'improve trust signals')

                    example_text = (
                        f"<i>For example, your content \"{title}\" scored {item_score:.1f}/100, with particularly weak "
                        f"{weakest_dim_name} ({weakest_dim_score:.1f}/100). To improve this, you should {action}. "
                        f"Addressing these issues could move this content from its current rating to Good or Excellent.</i>"
                    )
                    story.append(Paragraph(example_text, self.styles['Normal']))

        return story

    def _create_trust_stack_section(self, report_data: Dict[str, Any]) -> List:
        """
        Create Trust Stack Report section matching the web app content.
        
        This section generates the same detailed analysis displayed in the web app,
        including per-dimension rationale, key signal evaluations, diagnostics, 
        and recommendations.
        """
        import re
        story = []
        
        story.append(Paragraph("Trust Stack Report", self.styles['SectionHeader']))
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            "This section provides detailed dimension-by-dimension analysis of your brand's trust posture, "
            "matching the content displayed in the web application.",
            self.styles['Normal']
        ))
        story.append(Spacer(1, 15))
        
        # Check if generate_trust_stack_report is available
        if generate_trust_stack_report is None:
            story.append(Paragraph(
                "<i>Trust Stack Report generation is not available. Please check the reporting module.</i>",
                self.styles['Normal']
            ))
            return story
        
        # Get model configuration
        summary_model = report_data.get('llm_model', 'gpt-4o-mini')
        
        try:
            # Generate the Trust Stack report markdown content
            trust_stack_text = generate_trust_stack_report(report_data, model=summary_model)
            
            if not trust_stack_text:
                story.append(Paragraph(
                    "<i>No Trust Stack content was generated.</i>",
                    self.styles['Normal']
                ))
                return story
            
            # Convert markdown to PDF elements
            story.extend(self._markdown_to_pdf_elements(trust_stack_text))
            
        except Exception as e:
            logger.error(f"Failed to generate Trust Stack section: {e}")
            story.append(Paragraph(
                f"<i>Error generating Trust Stack Report: {str(e)}</i>",
                self.styles['Normal']
            ))
        
        return story

    def _create_image_flowable(self, path: str, max_width: float = 6*inch, max_height: float = 4*inch):
        """
        Create a ReportLab Image flowable from a path or URL.
        Handles local files (file://) and remote URLs (http://, https://).
        S3 paths should be converted to http/file paths before calling this.
        """
        try:
            img_data = None
            
            # Handle local file paths
            if path.startswith('file://'):
                local_path = path.replace('file://', '')
                if os.path.exists(local_path):
                    img_data = local_path
            
            # Handle remote URLs
            elif path.startswith('http://') or path.startswith('https://'):
                try:
                    response = requests.get(path, timeout=10, stream=True)
                    if response.status_code == 200:
                        img_data = io.BytesIO(response.content)
                except Exception as e:
                    logger.warning(f"Failed to fetch remote image {path}: {e}")
            
            # Handle standard paths (assume local) as fallback
            elif os.path.exists(path):
                img_data = path
                
            if img_data:
                img = Image(img_data)
                
                # Calculate aspect ratio
                img_width = img.drawWidth
                img_height = img.drawHeight
                aspect = img_height / float(img_width)
                
                # Resize if needed
                if img_width > max_width:
                    img_width = max_width
                    img_height = img_width * aspect
                
                if img_height > max_height:
                    img_height = max_height
                    img_width = img_height / aspect # Recalculate width to maintain aspect
                
                img.drawWidth = img_width
                img.drawHeight = img_height
                return img
                
        except Exception as e:
            logger.warning(f"Error creating image flowable for {path}: {e}")
            
        return None
    
    def _markdown_to_pdf_elements(self, markdown_text: str) -> List:
        """
        Convert markdown text to ReportLab PDF elements.
        
        Handles:
        - Bold (**text**)
        - Italic (*text*)
        - Headers (##, ###)
        - Bullet points (- or *)
        - Tables (| col | col |)
        - Emojis (converted to text via clean_emoji_for_pdf)
        """
        story = []
        
        def md_to_html(text):
            """Convert markdown formatting to HTML tags for ReportLab"""
            # Bold: **text** -> <b>text</b>
            text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
            # Italic: *text* -> <i>text</i> (but not ** which is bold)
            text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', text)
            # Clean emojis using global function
            text = clean_emoji_for_pdf(text)
            return text
        
        # Split into lines
        lines = markdown_text.split('\n')
        
        # Track if we're in a table
        in_table = False
        table_rows = []
        current_paragraph_lines = []
        
        def flush_paragraph():
            """Flush accumulated paragraph lines"""
            if current_paragraph_lines:
                text = ' '.join(current_paragraph_lines)
                text = md_to_html(text)
                if text.strip():
                    story.append(Paragraph(text, self.styles['TrustStackBody']))
                    story.append(Spacer(1, 3))
                current_paragraph_lines.clear()
        
        def render_table():
            """Render accumulated table rows"""
            if not table_rows:
                return
            
            # Parse table rows
            parsed_rows = []
            for row in table_rows:
                # Skip separator rows (|---|---|)
                if re.match(r'^\|[\s\-:]+\|$', row.replace(' ', '')):
                    continue
                # Split by | and clean
                cells = [cell.strip() for cell in row.split('|') if cell.strip()]
                if cells:
                    parsed_rows.append(cells)
            
            if not parsed_rows:
                return
            
            # Create table
            try:
                # Limit cell content length, process emojis, and wrap in Paragraph for markup rendering
                for i, row in enumerate(parsed_rows):
                    parsed_rows[i] = [Paragraph(clean_emoji_for_pdf(cell[:60]), self.styles['TableText']) for cell in row]
                
                # Calculate column widths
                num_cols = max(len(row) for row in parsed_rows)
                col_width = 5.5 * inch / num_cols
                
                table = Table(parsed_rows, colWidths=[col_width] * num_cols)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                ]))
                story.append(table)
                story.append(Spacer(1, 8))
            except Exception as e:
                logger.warning(f"Failed to render table: {e}")
            
            table_rows.clear()
        
        for line in lines:
            stripped = line.strip()
            
            # Empty line - flush paragraph
            if not stripped:
                flush_paragraph()
                if in_table:
                    render_table()
                    in_table = False
                continue
            
            # Table row
            if stripped.startswith('|') and stripped.endswith('|'):
                flush_paragraph()
                in_table = True
                table_rows.append(stripped)
                continue
            elif in_table:
                render_table()
                in_table = False
            
            # Horizontal rule
            if stripped == '---' or stripped == '***':
                flush_paragraph()
                story.append(Spacer(1, 10))
                continue
            
            # Images: ![Alt text](url)
            img_match = re.search(r'!\[(.*?)\]\((.*?)\)', stripped)
            if img_match:
                flush_paragraph()
                # support both entire line being image or inline (though we treat as block for PDF)
                # For now assuming block image behavior as typically used in our reports
                alt_text = img_match.group(1)
                img_path = img_match.group(2)
                
                # Check for title/tooltip in path "url 'title'"
                if ' "' in img_path:
                    img_path = img_path.split(' "')[0]
                elif " '" in img_path:
                    img_path = img_path.split(" '")[0]
                
                img_flowable = self._create_image_flowable(img_path)
                if img_flowable:
                    story.append(img_flowable)
                    story.append(Spacer(1, 10))
                    # If there's a caption/alt text, maybe show it?
                    # story.append(Paragraph(f"<i>{alt_text}</i>", self.styles['TableText']))
                else:
                    # Fallback if image loading fails
                    story.append(Paragraph(f"[Image: {alt_text}]", self.styles['TrustStackBody']))
                continue

            # Headers
            if stripped.startswith('###'):
                flush_paragraph()
                header_text = md_to_html(stripped[3:].strip())
                story.append(Paragraph(header_text, self.styles['Heading3']))
                story.append(Spacer(1, 5))
                continue
            elif stripped.startswith('##'):
                flush_paragraph()
                header_text = md_to_html(stripped[2:].strip())
                story.append(Paragraph(header_text, self.styles['SectionHeader']))
                story.append(Spacer(1, 8))
                continue
            elif stripped.startswith('#'):
                flush_paragraph()
                header_text = md_to_html(stripped[1:].strip())
                story.append(Paragraph(header_text, self.styles['DimensionHeader']))
                story.append(Spacer(1, 8))
                continue
            
            # Bullet points
            if re.match(r'^[\*\-]\s+', stripped):
                flush_paragraph()
                bullet_text = md_to_html(stripped[2:].strip())
                story.append(Paragraph(f"• {bullet_text}", self.styles['TrustStackBullet']))
                continue
            
            # Numbered lists
            if re.match(r'^\d+\.\s+', stripped):
                flush_paragraph()
                list_text = md_to_html(stripped)
                story.append(Paragraph(list_text, self.styles['TrustStackBullet']))
                continue
            
            # Regular text - accumulate for paragraph
            current_paragraph_lines.append(stripped)
        
        # Flush remaining content
        flush_paragraph()
        if in_table:
            render_table()
        
        return story
    
    def _create_executive_summary_enhanced(self, report_data: Dict[str, Any]) -> List:
        """Create enhanced executive summary with robust analysis and recommendations"""
        story = []
        story.append(Paragraph("Executive Summary", self.styles['SectionHeader']))
        story.append(Spacer(1, 10))

        items = report_data.get('items', [])
        total_items = len(items)

        # Calculate metrics
        if items:
            avg_rating = sum(item.get('final_score', 0) for item in items) / len(items)
        else:
            avg_rating = 0

        excellent = sum(1 for item in items if item.get('final_score', 0) >= 80)
        good = sum(1 for item in items if 60 <= item.get('final_score', 0) < 80)
        fair = sum(1 for item in items if 40 <= item.get('final_score', 0) < 60)
        poor = sum(1 for item in items if item.get('final_score', 0) < 40)

        # Generate LLM-powered executive summary
        from reporting.executive_summary import generate_executive_summary
        import re

        dimension_breakdown = report_data.get('dimension_breakdown', {})
        sources = report_data.get('sources', [])

        # Get model configuration from report data
        summary_model = report_data.get('llm_model', 'gpt-4o-mini')
        use_llm_summary = report_data.get('use_llm_summary', True)

        # Generate comprehensive executive summary
        try:
            executive_summary_text = generate_executive_summary(
                avg_rating=avg_rating * 100,  # Convert to 0-100 scale
                dimension_breakdown=dimension_breakdown,
                items=items,
                sources=sources,
                model=summary_model,
                use_llm=use_llm_summary
            )

            # Convert markdown to PDF-friendly HTML
            # Replace markdown bold (**text**) with HTML bold (<b>text</b>)
            executive_summary_text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', executive_summary_text)
            # Replace newlines with <br/> for proper PDF formatting
            executive_summary_text = executive_summary_text.replace('\n\n', '<br/><br/>')
            executive_summary_text = executive_summary_text.replace('\n', '<br/>')

            analysis = executive_summary_text

        except Exception as e:
            logger.warning(f"Executive summary generation failed for PDF, using fallback: {e}")
            # Fallback to template-based recommendation
            recommendation = generate_rating_recommendation_pdf(avg_rating, dimension_breakdown)

            # Use template-based analysis as fallback
            if avg_rating >= 80:
                analysis = (
                    f"<b>Overall Assessment: Excellent</b><br/><br/>"
                    f"Out of {total_items} content items analyzed, your brand achieved an average Trust Stack Rating "
                    f"of <b>{avg_rating:.1f}/100</b>, placing it in the Excellent category. This indicates high-quality, "
                    f"verified content with strong trust signals across all five dimensions. "
                    f"{excellent} items ({excellent/max(total_items, 1)*100:.1f}%) achieved excellent ratings (80+), "
                    f"demonstrating consistent quality standards.<br/><br/>"
                    f"<b>Key Recommendation:</b> {recommendation}"
                )
            elif avg_rating >= 60:
                analysis = (
                    f"<b>Overall Assessment: Good</b><br/><br/>"
                    f"Out of {total_items} content items analyzed, your brand achieved an average Trust Stack Rating "
                    f"of <b>{avg_rating:.1f}/100</b>, indicating good content quality with room for improvement. "
                    f"{excellent + good} items ({(excellent + good)/max(total_items, 1)*100:.1f}%) achieved good or "
                    f"excellent ratings, while {poor} items require attention to meet higher standards.<br/><br/>"
                    f"<b>Key Recommendation:</b> {recommendation}"
                )
            elif avg_rating >= 40:
                analysis = (
                    f"<b>Overall Assessment: Fair</b><br/><br/>"
                    f"Out of {total_items} content items analyzed, your brand achieved an average Trust Stack Rating "
                    f"of <b>{avg_rating:.1f}/100</b>, indicating fair content quality that requires attention. "
                    f"Only {excellent} items ({excellent/max(total_items, 1)*100:.1f}%) achieved excellent ratings, "
                    f"while {poor} items ({poor/max(total_items, 1)*100:.1f}%) demonstrate poor quality. Significant "
                    f"improvements are needed to enhance trust signals and content credibility.<br/><br/>"
                    f"<b>Key Recommendation:</b> {recommendation}"
                )
            else:
                analysis = (
                    f"<b>Overall Assessment: Poor (Immediate Action Required)</b><br/><br/>"
                    f"Out of {total_items} content items analyzed, your brand achieved an average Trust Stack Rating "
                    f"of <b>{avg_rating:.1f}/100</b>, indicating poor content quality requiring immediate action. "
                    f"{poor} items ({poor/max(total_items, 1)*100:.1f}%) demonstrate poor quality, suggesting widespread "
                    f"issues with trust signals, verification, or transparency. A comprehensive content audit and "
                    f"improvement plan is essential.<br/><br/>"
                    f"<b>Critical Recommendation:</b> {recommendation}"
                )

        story.append(Paragraph(analysis, self.styles['Normal']))
        story.append(Spacer(1, 15))

        # Rating scale reference
        story.append(Paragraph("<b>Trust Stack Rating Scale</b>", self.styles['Heading3']))
        scale_data = [
            ['Rating Band', 'Score Range', 'Description'],
            ['🟢 Excellent', '80-100', 'High-quality, verified content with strong trust signals'],
            ['🟡 Good', '60-79', 'Solid content with minor improvements needed'],
            ['🟠 Fair', '40-59', 'Moderate quality requiring attention and improvements'],
            ['🔴 Poor', '0-39', 'Low-quality content needing immediate review and action']
        ]

        scale_table = Table(scale_data, colWidths=[1.3*inch, 1.2*inch, 3.5*inch])
        scale_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))

        story.append(scale_table)
        story.append(Spacer(1, 15))

        # 5D Trust Framework overview
        story.append(Paragraph("<b>5D Trust Framework Overview</b>", self.styles['Heading3']))
        framework_text = (
            "Each content item is evaluated across five trust dimensions using a comprehensive 0-100 scoring rubric. "
            "The dimensions measure: <b>Provenance</b> (origin and traceability), <b>Verification</b> (factual accuracy), "
            "<b>Transparency</b> (disclosure and clarity), <b>Coherence</b> (cross-channel consistency), "
            "<b>Resonance</b> (audience engagement). "
            "The comprehensive rating is calculated as a weighted average across all five dimensions."
        )
        story.append(Paragraph(framework_text, self.styles['Normal']))

        return story

    def _create_visual_overview(self, report_data: Dict[str, Any]) -> List:
        """Create visual overview section with charts and graphs"""
        story = []
        story.append(Paragraph("Visual Overview", self.styles['SectionHeader']))
        story.append(Spacer(1, 10))

        items = report_data.get('items', [])

        # Calculate metrics
        if items:
            avg_rating = sum(item.get('final_score', 0) for item in items) / len(items)
        else:
            avg_rating = 0

        excellent = sum(1 for item in items if item.get('final_score', 0) >= 80)
        good = sum(1 for item in items if 60 <= item.get('final_score', 0) < 80)
        fair = sum(1 for item in items if 40 <= item.get('final_score', 0) < 60)
        poor = sum(1 for item in items if item.get('final_score', 0) < 40)

        # Rating distribution chart
        story.append(Paragraph("<b>Rating Distribution</b>", self.styles['Heading3']))
        story.append(Paragraph(
            f"The chart below shows how your {len(items)} content items are distributed across rating bands.",
            self.styles['Normal']
        ))
        story.append(Spacer(1, 10))

        chart_path = self._create_rating_chart(excellent, good, fair, poor)
        if chart_path:
            story.append(Image(chart_path, width=6*inch, height=4*inch))

        story.append(Spacer(1, 15))

        # Dimension scores chart
        story.append(Paragraph("<b>5D Trust Dimensions Scores</b>", self.styles['Heading3']))
        story.append(Paragraph(
            "The radar chart below visualizes your brand's performance across all six trust dimensions. "
            "Scores closer to the outer edge indicate stronger performance in that dimension.",
            self.styles['Normal']
        ))
        story.append(Spacer(1, 10))

        dimension_data = report_data.get('dimension_breakdown', {})
        if dimension_data:
            chart_path = self._create_dimension_chart(dimension_data)
            if chart_path:
                story.append(Image(chart_path, width=6*inch, height=4*inch))

        story.append(Spacer(1, 15))

        # Summary statistics table
        story.append(Paragraph("<b>Summary Statistics</b>", self.styles['Heading3']))

        stats_data = [
            ['Metric', 'Value'],
            ['Total Content Items', f"{len(items):,}"],
            ['Average Rating', f"{avg_rating:.1f}/100"],
            ['Excellent Items (80+)', f"{excellent:,} ({excellent/max(len(items), 1)*100:.1f}%)"],
            ['Good Items (60-79)', f"{good:,} ({good/max(len(items), 1)*100:.1f}%)"],
            ['Fair Items (40-59)', f"{fair:,} ({fair/max(len(items), 1)*100:.1f}%)"],
            ['Poor Items (0-39)', f"{poor:,} ({poor/max(len(items), 1)*100:.1f}%)"]
        ]

        stats_table = Table(stats_data, colWidths=[2.5*inch, 3.5*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))

        story.append(stats_table)

        return story

    def _create_notable_examples(self, report_data: Dict[str, Any]) -> List:
        """Create Notable Content Examples section highlighting successes and problem areas"""
        story = []

        items = report_data.get('items', [])
        if not items:
            return story

        story.append(Paragraph("Notable Content Examples", self.styles['SectionHeader']))
        story.append(Spacer(1, 10))

        # Sort items by score
        scored_items = []
        for item in items:
            score = item.get('final_score') or item.get('score')
            if score is not None:
                scored_items.append((float(score), item))

        if not scored_items:
            return story

        scored_items.sort(key=lambda x: x[0], reverse=True)

        # Get high trust items (top 3-5, score >= 70)
        high_trust = [item for score, item in scored_items if score >= 0.70][:5]

        # Get low trust items (bottom 2-3, score < 50)
        low_trust = [item for score, item in scored_items if score < 0.50][:3]

        # Success Highlights section with LLM insights
        if high_trust:
            story.append(Paragraph(clean_emoji_for_pdf("⭐ Success Highlights"), self.styles['Heading2']))
            story.append(Spacer(1, 10))

            # Generate LLM insights
            try:
                from reporting.executive_summary import generate_success_highlights

                avg_rating = report_data.get('avg_rating', 0.0)
                if avg_rating <= 1.0:  # Convert if on 0-1 scale
                    avg_rating = avg_rating * 100

                dimension_breakdown = report_data.get('dimension_breakdown', {})
                summary_model = report_data.get('llm_model', 'gpt-4o-mini')

                success_analysis = generate_success_highlights(
                    high_trust_items=high_trust,
                    avg_rating=avg_rating,
                    dimension_breakdown=dimension_breakdown,
                    model=summary_model
                )

                # Convert markdown formatting to PDF-friendly HTML
                import re
                success_analysis = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', success_analysis)
                success_analysis = success_analysis.replace('\n\n', '<br/><br/>')

                story.append(Paragraph(success_analysis, self.styles['Normal']))
                story.append(Spacer(1, 15))

            except Exception as e:
                logger.warning(f"Failed to generate success highlights for PDF: {e}")

            # List high trust examples
            story.append(Paragraph("High Trust Content Examples", self.styles['Heading3']))
            story.append(Spacer(1, 5))

            for i, item in enumerate(high_trust, 1):
                # Extract fields safely
                meta = item.get('meta', {})
                if isinstance(meta, str):
                    try:
                        import json
                        meta = json.loads(meta) if meta else {}
                    except:
                        meta = {}

                title = (
                    item.get('title') or
                    meta.get('title') or
                    meta.get('name') or
                    'Untitled'
                )[:80]
                score = float(item.get('final_score') or item.get('score', 0))

                # Get strongest dimensions
                dims = item.get('dimension_scores', {})
                if dims and isinstance(dims, dict):
                    try:
                        dims_parsed = {k: float(v) for k, v in dims.items() if v is not None}
                        if dims_parsed:
                            strongest = max(dims_parsed.items(), key=lambda x: x[1])

                            item_text = f"<b>{i}. {title}</b> (Score: {score:.2f})<br/>"
                            item_text += f"   Strongest: {strongest[0].title()} ({strongest[1]:.2f})"

                            story.append(Paragraph(item_text, self.styles['Normal']))
                            story.append(Spacer(1, 3))
                    except Exception:
                        pass

            story.append(Spacer(1, 15))

        # Low Trust Content section
        if low_trust:
            story.append(Paragraph("⚠️ Low Trust Content (Needs Attention)", self.styles['Heading2']))
            story.append(Spacer(1, 10))

            for i, item in enumerate(low_trust, 1):
                # Extract fields safely
                meta = item.get('meta', {})
                if isinstance(meta, str):
                    try:
                        import json
                        meta = json.loads(meta) if meta else {}
                    except:
                        meta = {}

                title = (
                    item.get('title') or
                    meta.get('title') or
                    meta.get('name') or
                    'Untitled'
                )[:80]
                score = float(item.get('final_score') or item.get('score', 0))

                # Get weakest dimensions
                dims = item.get('dimension_scores', {})
                if dims and isinstance(dims, dict):
                    try:
                        dims_parsed = {k: float(v) for k, v in dims.items() if v is not None}
                        if dims_parsed:
                            weakest_two = sorted(dims_parsed.items(), key=lambda x: x[1])[:2]
                            weak_str = ', '.join([f"{k.title()}({v:.2f})" for k, v in weakest_two])

                            item_text = f"<b>{i}. {title}</b> (Score: {score:.2f})<br/>"
                            item_text += f"   Weakest: {weak_str}"

                            story.append(Paragraph(item_text, self.styles['Normal']))
                            story.append(Spacer(1, 3))
                    except Exception:
                        pass

        return story

    def _create_dimension_deep_dive(self, report_data: Dict[str, Any]) -> List:
        """Create per-dimension breakdown with content examples and actionable analysis"""
        story = []
        story.append(Paragraph("Dimension Deep Dive", self.styles['SectionHeader']))
        story.append(Paragraph(
            "This section analyzes your brand's performance in each trust dimension with specific examples from your content "
            "and actionable recommendations for improvement.",
            self.styles['Normal']
        ))
        story.append(Spacer(1, 15))

        # Define dimensions with detailed descriptions and action recommendations
        dimensions_info = {
            'provenance': {
                'name': 'Provenance',
                'description': 'Measures the origin, traceability, and metadata integrity of content.',
                'icon': '🔗',
                'actions': {
                    'high': 'Continue maintaining clear authorship and structured metadata across all content.',
                    'medium': 'Add author attribution and publication timestamps to content that lacks them.',
                    'low': 'Implement schema.org markup, add clear author attribution, and include publication timestamps on all content immediately.'
                }
            },
            'verification': {
                'name': 'Verification',
                'description': 'Evaluates factual accuracy and verifiability against trusted databases.',
                'icon': '✓',
                'actions': {
                    'high': 'Maintain your strong fact-checking practices and continue citing authoritative sources.',
                    'medium': 'Add more citations and references to verifiable external sources.',
                    'low': 'Fact-check all claims against authoritative sources, add citations and references, and link to verifiable external data.'
                }
            },
            'transparency': {
                'name': 'Transparency',
                'description': 'Assesses disclosure practices, clarity, and attribution.',
                'icon': '👁',
                'actions': {
                    'high': 'Continue your excellent disclosure and attribution practices.',
                    'medium': 'Improve disclosure statements and add clearer attribution for sourced information.',
                    'low': 'Add disclosure statements, clearly identify sponsored content, and provide detailed attribution for all sources.'
                }
            },
            'coherence': {
                'name': 'Coherence',
                'description': 'Measures consistency across channels and over time.',
                'icon': '🔄',
                'actions': {
                    'high': 'Your messaging remains consistent - continue this unified approach.',
                    'medium': 'Review messaging consistency across channels and align visual branding.',
                    'low': 'Audit messaging consistency across all channels, align visual branding, and ensure unified voice in customer communications.'
                }
            },
            'resonance': {
                'name': 'Resonance',
                'description': 'Evaluates cultural fit and organic engagement.',
                'icon': '📢',
                'actions': {
                    'high': 'Your content resonates well with your audience - maintain this authentic engagement.',
                    'medium': 'Reduce overly promotional language and increase authentic engagement.',
                    'low': 'Increase authentic engagement with your audience, reduce promotional language significantly, and ensure cultural relevance in messaging.'
                }
            }
        }

        dimension_breakdown = report_data.get('dimension_breakdown', {})
        items = report_data.get('items', [])
        items = [_coerce_item_to_dict(it) for it in items]

        # Process each dimension
        for dim_key, dim_info in dimensions_info.items():
            dim_data = dimension_breakdown.get(dim_key, {})
            avg_score = dim_data.get('average', 0) * 100  # Convert to 0-100 scale
            min_score = dim_data.get('min', 0) * 100
            max_score = dim_data.get('max', 0) * 100

            # Dimension header
            story.append(Paragraph(f"{dim_info['icon']} <b>{dim_info['name']}</b>", self.styles['Heading3']))
            story.append(Paragraph(dim_info['description'], self.styles['Normal']))
            story.append(Spacer(1, 8))

            # Score summary with performance assessment
            if avg_score >= 70:
                performance = "Strong"
                perf_color = colors.darkgreen
                action_level = 'high'
            elif avg_score >= 50:
                performance = "Moderate"
                perf_color = colors.orange
                action_level = 'medium'
            else:
                performance = "Needs Improvement"
                perf_color = colors.red
                action_level = 'low'

            score_para = Paragraph(
                f"<b>Performance:</b> <font color='{perf_color.hexval()}'>{performance}</font> | "
                f"<b>Average Score:</b> {avg_score:.1f}/100 | <b>Range:</b> {min_score:.1f} - {max_score:.1f}",
                self.styles['Normal']
            )
            story.append(score_para)
            story.append(Spacer(1, 10))

            # Find best and worst examples for this dimension
            items_with_dim_scores = []
            for item in items:
                dim_scores = item.get('dimension_scores', {})
                if dim_key in dim_scores and dim_scores[dim_key] is not None:
                    items_with_dim_scores.append((item, dim_scores[dim_key] * 100))

            if items_with_dim_scores and len(items_with_dim_scores) > 0:
                # Sort by dimension score
                items_with_dim_scores.sort(key=lambda x: x[1], reverse=True)

                # Analysis paragraph
                num_high = len([s for _, s in items_with_dim_scores if s >= 70])
                num_low = len([s for _, s in items_with_dim_scores if s < 40])
                total_items = len(items_with_dim_scores)

                analysis_text = (
                    f"<b>Analysis:</b> Of your {total_items} content items, {num_high} ({num_high/total_items*100:.0f}%) scored 70+ in {dim_info['name']}, "
                    f"while {num_low} ({num_low/total_items*100:.0f}%) scored below 40. "
                )

                if avg_score >= 70:
                    analysis_text += f"Your brand shows strength in {dim_info['name'].lower()}, with most content meeting high standards."
                elif avg_score >= 50:
                    analysis_text += f"There is inconsistency in {dim_info['name'].lower()} - some content excels while other items need significant improvement."
                else:
                    analysis_text += f"Most content struggles with {dim_info['name'].lower()}, indicating a systemic issue that requires immediate attention."

                story.append(Paragraph(analysis_text, self.styles['Normal']))
                story.append(Spacer(1, 10))

                # Show best example
                best_item, best_score = items_with_dim_scores[0]
                story.append(Paragraph(f"<b>Highest-Scoring Example</b> ({best_score:.1f}/100):", self.styles['Normal']))

                meta = best_item.get('meta', {})
                title = meta.get('title') or meta.get('source_url') or meta.get('url') or 'Untitled'
                if len(title) > 70:
                    title = title[:67] + '...'

                source = best_item.get('source', 'Unknown').upper()
                url = meta.get('source_url') or meta.get('url') or ''
                if len(url) > 60:
                    url = url[:57] + '...'

                example_data = [
                    ['Title', title],
                    ['Source', source],
                    ['URL', url if url else 'N/A']
                ]

                example_table = Table(example_data, colWidths=[1.0*inch, 5.0*inch])
                example_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                    ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BACKGROUND', (1, 0), (1, -1), colors.Color(0.93, 0.97, 0.93)),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                ]))

                story.append(example_table)
                story.append(Spacer(1, 10))

                # Always show worst example for comparison
                if len(items_with_dim_scores) > 1:
                    worst_item, worst_score = items_with_dim_scores[-1]
                    story.append(Paragraph(f"<b>Lowest-Scoring Example</b> ({worst_score:.1f}/100):", self.styles['Normal']))

                    meta = worst_item.get('meta', {})
                    title = meta.get('title') or meta.get('source_url') or meta.get('url') or 'Untitled'
                    if len(title) > 70:
                        title = title[:67] + '...'

                    source = worst_item.get('source', 'Unknown').upper()
                    url = meta.get('source_url') or meta.get('url') or ''
                    if len(url) > 60:
                        url = url[:57] + '...'

                    example_data = [
                        ['Title', title],
                        ['Source', source],
                        ['URL', url if url else 'N/A']
                    ]

                    example_table = Table(example_data, colWidths=[1.0*inch, 5.0*inch])
                    example_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                        ('BACKGROUND', (1, 0), (1, -1), colors.Color(0.97, 0.93, 0.93)),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                    ]))

                    story.append(example_table)
                    story.append(Spacer(1, 8))

            # Call to action
            story.append(Paragraph("<b>Recommended Action:</b>", self.styles['Normal']))
            action_text = dim_info['actions'][action_level]
            story.append(Paragraph(f"→ {action_text}", self.styles['Normal']))

            story.append(Spacer(1, 18))

        return story

    def _create_item_diagnostic(self, report_data: Dict[str, Any]) -> List:
        """Create item-by-item diagnostic appendix"""
        story = []
        story.append(Paragraph("Appendix: Item-by-Item Diagnostic", self.styles['SectionHeader']))
        story.append(Paragraph(
            "This appendix provides a comprehensive listing of all analyzed content items with their scores across all dimensions. "
            "Use this detailed breakdown to identify specific content pieces that need improvement or that serve as good examples.",
            self.styles['Normal']
        ))
        story.append(Spacer(1, 15))

        items = report_data.get('items', [])
        items = [_coerce_item_to_dict(it) for it in items]

        if not items:
            story.append(Paragraph("No items available for diagnostic analysis.", self.styles['Normal']))
            return story

        # Create detailed items table
        # Headers
        table_data = [[
            'Title',
            'Source',
            'Overall\nRating',
            'Prov.',
            'Verif.',
            'Trans.',
            'Coher.',
            'Reson.',
            'AI'
        ]]

        # Process each item
        for item in items[:50]:  # Limit to 50 items to keep PDF manageable
            meta = item.get('meta', {})
            title = meta.get('title') or meta.get('url') or 'Untitled'
            if len(title) > 35:
                title = title[:32] + '...'

            source = item.get('source', 'N/A').upper()[:6]
            final_score = item.get('final_score', 0)

            dim_scores = item.get('dimension_scores', {})
            prov = dim_scores.get('provenance', 0) * 100 if dim_scores.get('provenance') is not None else 0
            verif = dim_scores.get('verification', 0) * 100 if dim_scores.get('verification') is not None else 0
            trans = dim_scores.get('transparency', 0) * 100 if dim_scores.get('transparency') is not None else 0
            coher = dim_scores.get('coherence', 0) * 100 if dim_scores.get('coherence') is not None else 0
            reson = dim_scores.get('resonance', 0) * 100 if dim_scores.get('resonance') is not None else 0
            # Safely get AI/automation related score from dimension scores.
            # Some items may store an 'ai' key or may not include this dimension at all.
            ai_val = None
            if isinstance(dim_scores, dict):
                # prefer explicit 'ai' key if present
                if 'ai' in dim_scores:
                    ai_val = dim_scores.get('ai')
                else:
                    # fallback: attempt numeric-key access if older code used integer keys
                    ai_val = dim_scores.get(0) if 0 in dim_scores else None

            ai = (ai_val * 100) if (ai_val is not None) else 0

            table_data.append([
                title,
                source,
                f"{final_score:.1f}",
                f"{prov:.0f}",
                f"{verif:.0f}",
                f"{trans:.0f}",
                f"{coher:.0f}",
                f"{reson:.0f}",
                f"{ai:.0f}"
            ])

        # Create table
        items_table = Table(table_data, colWidths=[2.2*inch, 0.6*inch, 0.6*inch, 0.5*inch, 0.5*inch, 0.5*inch, 0.5*inch, 0.5*inch, 0.4*inch])

        # Style the table
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Left align titles
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]

        # Color code rows based on overall rating
        for row_idx in range(1, len(table_data)):
            overall_score = float(table_data[row_idx][2])
            if overall_score >= 80:
                bg_color = colors.Color(0.83, 0.93, 0.85)  # Light green
            elif overall_score >= 60:
                bg_color = colors.Color(0.82, 0.93, 0.94)  # Light blue
            elif overall_score >= 40:
                bg_color = colors.Color(1.0, 0.95, 0.80)   # Light yellow
            else:
                bg_color = colors.Color(0.97, 0.84, 0.85)  # Light red

            table_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), bg_color))

        items_table.setStyle(TableStyle(table_style))
        story.append(items_table)

        if len(items) > 50:
            story.append(Spacer(1, 10))
            story.append(Paragraph(
                f"<i>Note: Showing first 50 of {len(items)} total items. For complete analysis, refer to the JSON export.</i>",
                self.styles['Normal']
            ))

        return story

    def _create_executive_summary(self, report_data: Dict[str, Any], include_items_table: bool = False) -> List:
        """Create executive summary section"""
        story = []
        story.append(Paragraph("Executive Summary", self.styles['SectionHeader']))

        items = report_data.get('items', [])
        total_items = len(items)

        # Calculate average rating and distribution
        if items:
            avg_rating = sum(item.get('final_score', 0) for item in items) / len(items)
        else:
            avg_rating = 0

        excellent = sum(1 for item in items if item.get('final_score', 0) >= 80)
        good = sum(1 for item in items if 60 <= item.get('final_score', 0) < 80)
        fair = sum(1 for item in items if 40 <= item.get('final_score', 0) < 60)
        poor = sum(1 for item in items if item.get('final_score', 0) < 40)

        # Get dimension breakdown for data-driven recommendations
        dimension_breakdown = report_data.get('dimension_breakdown', {})
        recommendation = generate_rating_recommendation_pdf(avg_rating, dimension_breakdown)

        # Interpretation based on average rating
        if avg_rating >= 80:
            interp = (
                f"Out of {total_items} items analyzed, the average Trust Stack Rating is {avg_rating:.1f}/100, "
                f"indicating excellent content quality. {excellent} items ({excellent/max(total_items, 1)*100:.1f}%) "
                f"achieved excellent ratings (80+), demonstrating strong trust signals across the 5D Trust Framework. "
                f"{recommendation}"
            )
        elif avg_rating >= 60:
            interp = (
                f"Out of {total_items} items analyzed, the average Trust Stack Rating is {avg_rating:.1f}/100, "
                f"indicating good content quality with room for improvement. {excellent + good} items "
                f"({(excellent + good)/max(total_items, 1)*100:.1f}%) achieved good or excellent ratings, "
                f"while {poor} items require attention. {recommendation}"
            )
        elif avg_rating >= 40:
            interp = (
                f"Out of {total_items} items analyzed, the average Trust Stack Rating is {avg_rating:.1f}/100, "
                f"indicating fair content quality requiring attention. Only {excellent} items ({excellent/max(total_items, 1)*100:.1f}%) "
                f"achieved excellent ratings, while {poor} items ({poor/max(total_items, 1)*100:.1f}%) have poor quality. "
                f"{recommendation}"
            )
        else:
            interp = (
                f"Out of {total_items} items analyzed, the average Trust Stack Rating is {avg_rating:.1f}/100, "
                f"indicating poor content quality requiring immediate action. {poor} items ({poor/max(total_items, 1)*100:.1f}%) "
                f"have poor ratings, suggesting widespread trust issues that need to be addressed urgently. "
                f"{recommendation}"
            )

        story.append(Paragraph(interp, self.styles['Normal']))

        # Rating scale reference
        story.append(Spacer(1, 8))
        story.append(Paragraph("Trust Stack Rating Scale:", self.styles['Heading3']))
        scale_lines = [
            "• 80-100 (Excellent): High-quality, verified content with strong trust signals",
            "• 60-79 (Good): Solid content with minor improvements needed",
            "• 40-59 (Fair): Moderate quality requiring attention",
            "• 0-39 (Poor): Low-quality content needing immediate review"
        ]
        for ln in scale_lines:
            story.append(Paragraph(ln, self.styles['Normal']))

        # Examples section (up to 5 items) for quick review
        items = report_data.get('items', []) or report_data.get('items', [])
        # Coerce any non-dict items into dicts so .get() accessors work uniformly
        items = [_coerce_item_to_dict(it) for it in items]
        if items:
            story.append(Spacer(1, 8))
            story.append(Paragraph("Examples from this run:", self.styles['Heading3']))
            example_rows = []
            max_examples = 5

            preferred_sources = report_data.get('sources') or sorted({it.get('source') for it in items if it.get('source')})
            selected = []
            for src in preferred_sources:
                if len(selected) >= max_examples:
                    break
                for it in items:
                    if it.get('source') == src and it not in selected:
                        selected.append(it)
                        break
            if len(selected) < max_examples:
                for it in items:
                    if len(selected) >= max_examples:
                        break
                    if it not in selected:
                        selected.append(it)

            # Render each example as a small block with Title, Label, Score, Description, URL
            for ex in selected[:max_examples]:
                meta = ex.get('meta') or {}
                title = meta.get('title') or meta.get('source_url') or ex.get('content_id')
                score = ex.get('final_score', 0.0)
                label = ex.get('label', '')
                desc = meta.get('description') or meta.get('snippet') or meta.get('summary') or ''
                # Optionally use LLM to produce a concise description for PDF examples
                use_llm = bool(report_data.get('use_llm_for_examples') or report_data.get('use_llm_for_descriptions'))
                if use_llm and _llm_summarize is not None:
                    try:
                        desc_llm = _llm_summarize(desc or clean_text_for_llm(meta), model=report_data.get('llm_model', 'gpt-4o'), max_words=120)
                        if desc_llm and add_llm_provenance is not None:
                            desc = add_llm_provenance(desc_llm, report_data.get('llm_model', 'gpt-4o'))
                        elif desc_llm:
                            # Fallback if helper not available
                            desc = desc_llm.strip()
                    except Exception:
                        # fall back to original desc
                        pass
                url = meta.get('source_url') or meta.get('url') or ''

                # Determine rating band
                if score >= 80:
                    rating_band = "Excellent"
                elif score >= 60:
                    rating_band = "Good"
                elif score >= 40:
                    rating_band = "Fair"
                else:
                    rating_band = "Poor"

                # Title row
                story.append(Paragraph(f"<b>{title}</b> — {rating_band} ({score:.1f}/100)", self.styles['Normal']))
                if desc:
                    if len(desc) > 300:
                        desc = desc[:297].rstrip() + '...'
                    story.append(Paragraph(desc, self.styles['Normal']))
                if url:
                    story.append(Paragraph(f"URL: {url}", self.styles['Normal']))
                story.append(Spacer(1, 6))

        # Optionally include the full per-item table when requested (programmatic runs)
        if include_items_table:
            all_items = report_data.get('items', [])
            # Coerce items for table rendering
            all_items = [_coerce_item_to_dict(it) for it in all_items]
            if all_items:
                story.append(PageBreak())
                story.append(Paragraph('Per-item Rating Table', self.styles['SectionHeader']))
                table_rows = [['Content ID', 'Source', 'Rating', 'Score', 'URL']]
                for it in all_items:
                    url = ''
                    try:
                        url = it.get('meta', {}).get('source_url') or ''
                    except Exception:
                        url = ''
                    # Determine rating band for table
                    score = it.get('final_score', 0.0)
                    if score >= 80:
                        rating_band = "Excellent"
                    elif score >= 60:
                        rating_band = "Good"
                    elif score >= 40:
                        rating_band = "Fair"
                    else:
                        rating_band = "Poor"
                    table_rows.append([it.get('content_id'), it.get('source'), rating_band, f"{score:.1f}", url])
                per_table = Table(table_rows, colWidths=[1.5*inch, 1*inch, 1*inch, 0.8*inch, 2.0*inch])
                per_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))
                story.append(per_table)
        
        return story

    def _create_rating_analysis(self, report_data: Dict[str, Any]) -> List:
        """Create Trust Stack Rating analysis section"""
        story = []
        story.append(Paragraph("Trust Stack Rating Analysis", self.styles['SectionHeader']))

        items = report_data.get('items', [])
        total_items = len(items)

        # Calculate rating distribution
        if items:
            avg_rating = sum(item.get('final_score', 0) for item in items) / len(items)
        else:
            avg_rating = 0

        excellent = sum(1 for item in items if item.get('final_score', 0) >= 80)
        good = sum(1 for item in items if 60 <= item.get('final_score', 0) < 80)
        fair = sum(1 for item in items if 40 <= item.get('final_score', 0) < 60)
        poor = sum(1 for item in items if item.get('final_score', 0) < 40)

        # Rating metrics table
        rating_metrics = [
            ['Rating Band', 'Count', 'Percentage', 'Description'],
            ['Excellent (80-100)', f"{excellent:,}", f"{excellent / max(total_items, 1) * 100:.1f}%", 'High-quality, verified content'],
            ['Good (60-79)', f"{good:,}", f"{good / max(total_items, 1) * 100:.1f}%", 'Solid content, minor improvements'],
            ['Fair (40-59)', f"{fair:,}", f"{fair / max(total_items, 1) * 100:.1f}%", 'Moderate quality, needs attention'],
            ['Poor (0-39)', f"{poor:,}", f"{poor / max(total_items, 1) * 100:.1f}%", 'Low quality, immediate action'],
            ['', '', '', ''],
            ['Total Items', f"{total_items:,}", '100.0%', ''],
            ['Average Rating', f"{avg_rating:.1f}/100", '', '']
        ]

        rating_table = Table(rating_metrics, colWidths=[1.5*inch, 1*inch, 1*inch, 2.5*inch])
        rating_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 1), (-1, -3), colors.beige),
            ('BACKGROUND', (0, -2), (-1, -1), colors.lightblue),
            ('FONTNAME', (0, -2), (-1, -1), 'Helvetica-Bold'),
        ]))

        story.append(rating_table)
        story.append(Spacer(1, 20))

        # Explanation
        story.append(Paragraph("Rating Methodology", self.styles['Heading3']))
        explanation = (
            "Each content item receives a comprehensive rating (0-100) calculated as a weighted average "
            "across six trust dimensions: Provenance, Verification, Transparency, Coherence, Resonance, "
            ". Detected trust attributes (e.g., SSL certificates, schema markup, author "
            "attribution) provide bonuses or penalties to the base dimensional scores."
        )
        story.append(Paragraph(explanation, self.styles['Normal']))
        story.append(Spacer(1, 12))

        # Create rating distribution chart
        chart_path = self._create_rating_chart(excellent, good, fair, poor)
        if chart_path:
            story.append(Image(chart_path, width=6*inch, height=4*inch))

        return story

    def _create_legacy_ar_section(self, report_data: Dict[str, Any]) -> List:
        """Create legacy Authenticity Ratio section for backward compatibility"""
        story = []
        story.append(Paragraph("Legacy Metrics (Authenticity Ratio)", self.styles['SectionHeader']))
        story.append(Paragraph("Note: These metrics are provided for backward compatibility. The primary focus is Trust Stack Ratings.", self.styles['Normal']))
        story.append(Spacer(1, 10))

        ar_data = report_data.get('authenticity_ratio', {})

        # AR metrics table
        ar_metrics = [
            ['Metric', 'Count', 'Percentage'],
            ['Total Content', f"{ar_data.get('total_items', 0):,}", '100.0%'],
            ['Authentic', f"{ar_data.get('authentic_items', 0):,}", f"{ar_data.get('authentic_items', 0) / max(ar_data.get('total_items', 1), 1) * 100:.1f}%"],
            ['Suspect', f"{ar_data.get('suspect_items', 0):,}", f"{ar_data.get('suspect_items', 0) / max(ar_data.get('total_items', 1), 1) * 100:.1f}%"],
            ['Inauthentic', f"{ar_data.get('inauthentic_items', 0):,}", f"{ar_data.get('inauthentic_items', 0) / max(ar_data.get('total_items', 1), 1) * 100:.1f}%"],
            ['', '', ''],
            ['Core AR', f"{ar_data.get('authenticity_ratio_pct', 0.0):.1f}%", ''],
            ['Extended AR', f"{ar_data.get('extended_ar_pct', 0.0):.1f}%", '']
        ]

        ar_table = Table(ar_metrics, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
        ar_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 1), (-1, -3), colors.beige),
            ('BACKGROUND', (0, -2), (-1, -1), colors.lightblue),
            ('FONTNAME', (0, -2), (-1, -1), 'Helvetica-Bold'),
        ]))

        story.append(ar_table)
        story.append(Spacer(1, 20))

        # Add a small explanatory paragraph showing the simple Core AR formula and why Extended AR can differ
        try:
            total = ar_data.get('total_items', 0)
            auth = ar_data.get('authentic_items', 0)
            ext = ar_data.get('extended_ar_pct', 0.0)
            core_pct = ar_data.get('authenticity_ratio_pct', 0.0)
            expl = (
                f"Core AR (simple): Authentic / Total * 100 = {auth} / {total} * 100 = {core_pct:.1f}%\n"
                f"Extended AR: {ext:.1f}% — this is a rubric-adjusted blend that can pull items toward authenticity or inauthenticity based on 5D scores and attribute rules."
            )
            story.append(Paragraph(expl, self.styles['Normal']))
        except Exception:
            pass

        # Dimension sections
        dimension_data = report_data.get('dimension_breakdown', {})
        defs = {
            'provenance': 'How traceable and source-verified the content is.',
            'verification': 'Alignment with verifiable brand or regulatory data.',
            'transparency': 'Clarity of ownership, disclosure, and intent.',
            'coherence': 'Consistency of messaging and tone with known brand assets.',
            'resonance': 'Audience engagement that aligns with brand values.'
        }

        for dim in ['provenance', 'verification', 'transparency', 'coherence', 'resonance']:
            stats = dimension_data.get(dim, {})
            avg = stats.get('average', 0.0)
            lo = stats.get('min', 0.0)
            hi = stats.get('max', 0.0)
            interp = ''
            if dim == 'provenance':
                interp = 'Moderate provenance indicates some content includes brand-linked metadata or source signals (e.g., official product listings or verified user accounts), but most lacks clear traceability.'
            elif dim == 'verification':
                interp = 'Verification is the weakest pillar. Few posts or listings reference authoritative identifiers (such as verified domains, SSL certificates, or official brand handles).'
            elif dim == 'transparency':
                interp = 'Transparency remains low, likely due to missing disclosure tags or ambiguous authorship.'
            elif dim == 'coherence':
                interp = 'Inconsistent tone or visual style may indicate unofficial reshares or imitations.'
            elif dim == 'resonance':
                interp = 'Resonance is relatively stable but not strongly correlated with authenticity, suggesting popular content may not be brand-originated.'

            story.append(Paragraph(dim.title(), self.styles['SectionHeader']))
            story.append(Paragraph(f"Definition: {defs.get(dim)}", self.styles['Normal']))
            story.append(Paragraph(f"Key Stats: Average: {avg:.3f} | Range: {lo:.2f}–{hi:.2f}", self.styles['Normal']))
            story.append(Paragraph(interp, self.styles['Normal']))
            story.append(Spacer(1, 12))
        
        return story
    
    def _create_dimension_breakdown(self, report_data: Dict[str, Any]) -> List:
        """Create dimension breakdown section"""
        story = []

        story.append(Paragraph("5D Trust Dimensions Analysis", self.styles['SectionHeader']))
        
        dimension_data = report_data.get('dimension_breakdown', {})
        
        if dimension_data:
            # Dimension scores table
            dim_headers = ['Dimension', 'Average', 'Min', 'Max', 'Std Dev']
            dim_rows = [dim_headers]
            
            for dimension, stats in dimension_data.items():
                dim_rows.append([
                    dimension.title(),
                    f"{stats.get('average', 0):.3f}",
                    f"{stats.get('min', 0):.3f}",
                    f"{stats.get('max', 0):.3f}",
                    f"{stats.get('std_dev', 0):.3f}"
                ])
            
            dim_table = Table(dim_rows, colWidths=[1.5*inch, 1*inch, 1*inch, 1*inch, 1*inch])
            dim_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ]))
            
            story.append(dim_table)
            story.append(Spacer(1, 20))
            
            # Dimension chart
            chart_path = self._create_dimension_chart(dimension_data)
            if chart_path:
                story.append(Image(chart_path, width=6*inch, height=4*inch))

        # Attempt to embed visuals created by markdown generator (heatmap, trendline, channel breakdown)
        # They are saved in the output directory if present
        out_dir = report_data.get('output_dir', './output')
        run_id = report_data.get('run_id', 'run')
        heatmap = os.path.join(out_dir, f"heatmap_{run_id}.png")
        trend = os.path.join(out_dir, f"ar_trend_{run_id}.png")
        channel = os.path.join(out_dir, f"channel_breakdown_{run_id}.png")
        # Content-type visuals (created by MarkdownReportGenerator)
        ctype_pie = os.path.join(out_dir, f"content_type_pie_{run_id}.png")
        ctype_bar = os.path.join(out_dir, f"content_type_bar_{run_id}.png")

        for img_path in (heatmap, trend, channel, ctype_pie, ctype_bar):
            if not img_path:
                continue
            if os.path.exists(img_path):
                try:
                    story.append(Spacer(1, 12))
                    # For pie charts, prefer a square-ish box; for bars/trend use a wider box
                    basename = os.path.basename(img_path).lower()
                    if 'pie' in basename:
                        story.append(Image(img_path, width=5*inch, height=4*inch))
                    elif 'dim' in basename or 'dimension' in basename:
                        story.append(Image(img_path, width=6*inch, height=4*inch))
                    else:
                        # default sizing for other charts
                        story.append(Image(img_path, width=6*inch, height=3*inch))
                except Exception as e:
                    logger.debug(f"Could not embed image {img_path}: {e}")
        
        return story

    def _create_rating_chart(self, excellent: int, good: int, fair: int, poor: int) -> str:
        """Create rating distribution chart"""
        try:
            # Create pie chart
            fig, ax = plt.subplots(figsize=(8, 6))

            labels = ['Excellent (80+)', 'Good (60-79)', 'Fair (40-59)', 'Poor (<40)']
            sizes = [excellent, good, fair, poor]
            colors_list = ['#2ecc71', '#3498db', '#f39c12', '#e74c3c']

            # Remove zero values
            non_zero_data = [(label, size, color) for label, size, color in zip(labels, sizes, colors_list) if size > 0]
            if non_zero_data:
                labels, sizes, colors_list = zip(*non_zero_data)

            wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors_list, autopct='%1.1f%%', startangle=90)

            # Customize text
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')

            ax.set_title('Rating Distribution', fontsize=14, fontweight='bold')

            # Save to temporary file
            chart_path = f"/tmp/rating_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close()

            return chart_path

        except Exception as e:
            logger.error(f"Error creating rating chart: {e}")
            return None

    def _create_classification_analysis(self, report_data: Dict[str, Any]) -> List:
        """Create classification analysis section"""
        story = []
        
        story.append(Paragraph("Content Classification Analysis", self.styles['SectionHeader']))
        
        classification_data = report_data.get('classification_analysis', {})
        
        if classification_data:
            # Classification summary
            dist = classification_data.get('classification_distribution', {})
            total = sum(dist.values())
            
            if total > 0:
                summary_text = f"""
                Content classification analysis reveals the following distribution:
                • Authentic content: {dist.get('authentic', 0):,} items ({dist.get('authentic', 0)/total*100:.1f}%)
                • Suspect content: {dist.get('suspect', 0):,} items ({dist.get('suspect', 0)/total*100:.1f}%)
                • Inauthentic content: {dist.get('inauthentic', 0):,} items ({dist.get('inauthentic', 0)/total*100:.1f}%)
                
                This classification helps identify content that requires immediate attention 
                (inauthentic), content that may need verification (suspect), and content 
                that strengthens brand authenticity (authentic).
                """
                
                story.append(Paragraph(summary_text, self.styles['Normal']))
        
        return story
    
    def _create_ar_chart(self, ar_data: Dict[str, Any]) -> str:
        """Create Authenticity Ratio chart"""
        try:
            # Create pie chart
            fig, ax = plt.subplots(figsize=(8, 6))
            
            labels = ['Authentic', 'Suspect', 'Inauthentic']
            sizes = [
                ar_data.get('authentic_items', 0),
                ar_data.get('suspect_items', 0),
                ar_data.get('inauthentic_items', 0)
            ]
            colors_list = ['#2ecc71', '#f39c12', '#e74c3c']
            
            # Remove zero values
            non_zero_data = [(label, size, color) for label, size, color in zip(labels, sizes, colors_list) if size > 0]
            if non_zero_data:
                labels, sizes, colors_list = zip(*non_zero_data)
            
            wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors_list, autopct='%1.1f%%', startangle=90)
            
            # Customize text
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
            
            ax.set_title('Content Classification Distribution', fontsize=14, fontweight='bold')
            
            # Save to temporary file
            chart_path = f"/tmp/ar_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            return chart_path
            
        except Exception as e:
            logger.error(f"Error creating AR chart: {e}")
            return None
    
    def _create_dimension_chart(self, dimension_data: Dict[str, Any]) -> str:
        """Create dimension scores chart"""
        try:
            # Create bar chart
            fig, ax = plt.subplots(figsize=(10, 6))
            
            dimensions = list(dimension_data.keys())
            averages = [dimension_data[dim]['average'] for dim in dimensions]
            
            bars = ax.bar(dimensions, averages, color=['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6'])
            
            # Customize chart
            ax.set_ylim(0, 1)
            ax.set_ylabel('Average Score')
            ax.set_title('5D Trust Dimensions - Average Scores', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
            
            # Add value labels on bars
            for bar, avg in zip(bars, averages):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                       f'{avg:.3f}', ha='center', va='bottom', fontweight='bold')
            
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            # Save to temporary file
            chart_path = f"/tmp/dimensions_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            return chart_path
        except Exception as e:
            logger.error(f"Error creating dimension chart: {e}")
            return None
