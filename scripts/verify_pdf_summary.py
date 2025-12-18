
import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from reporting.pdf_generator import PDFReportGenerator
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_pdf_generation():
    """Verify that PDF generation works with the new Executive Summary logic."""
    
    # Mock report data
    report_data = {
        "run_id": "verify-run-123",
        "brand_id": "Test Brand",
        "generated_at": datetime.now().strftime("%B %d, %Y"),
        "sources": ["https://example.com"],
        "items": [
            {
                "id": 1,
                "title": "Test Item 1",
                "final_score": 0.5,
                "dimension_scores": {"provenance": 0.4, "verification": 0.6},
                "meta": {"url": "https://example.com/1"},
                "source": "web"
            },
            {
                "id": 2,
                "title": "Test Item 2",
                "final_score": 0.8,
                "dimension_scores": {"provenance": 0.9, "verification": 0.8},
                "meta": {"url": "https://example.com/2"},
                "source": "web"
            }
        ],
        "dimension_breakdown": {
            "provenance": {"average": 0.65},
            "verification": {"average": 0.70},
            "transparency": {"average": 0.60},
            "coherence": {"average": 0.75},
            "resonance": {"average": 0.80}
        },
        "llm_model": "gpt-4o-mini",
        "use_llm_summary": False  # Use template fallback to avoid API costs/keys during simple test
    }
    
    output_path = "test_report_with_summary.pdf"
    
    try:
        generator = PDFReportGenerator()
        generator.generate_report(report_data, output_path)
        
        if os.path.exists(output_path):
            logger.info(f"✅ PDF generated successfully at {output_path}")
            # Clean up
            os.remove(output_path)
        else:
            logger.error("❌ PDF file was not created.")
            
    except Exception as e:
        logger.error(f"❌ PDF generation failed: {e}")
        raise

if __name__ == "__main__":
    verify_pdf_generation()
