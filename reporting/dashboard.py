"""
Dashboard generator for AR tool
Creates interactive Streamlit dashboard for real-time monitoring
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Dict, Any, List
import logging
from datetime import datetime, timedelta

from data.athena_client import AthenaClient
from config.settings import SETTINGS

logger = logging.getLogger(__name__)

class DashboardGenerator:
    """Generates interactive Streamlit dashboard for AR monitoring"""
    
    def __init__(self):
        self.athena_client = AthenaClient()
    
    def create_dashboard(self):
        """Create the main Streamlit dashboard"""
        st.set_page_config(
            page_title="Authenticity Ratio Dashboard",
            page_icon="📊",
            layout="wide"
        )
        
        # Header
        st.title("📊 Authenticity Ratio™ Dashboard")
        st.markdown("Real-time monitoring of brand content authenticity across channels")
        
        # Sidebar for filters
        with st.sidebar:
            st.header("Filters")
            brand_id = st.selectbox("Select Brand", self._get_available_brands())
            time_range = st.selectbox("Time Range", ["Last 7 days", "Last 30 days", "Last 90 days"])
            
        if brand_id:
            # Main dashboard content
            self._create_overview_section(brand_id, time_range)
            self._create_authenticity_ratio_section(brand_id, time_range)
            self._create_dimension_analysis_section(brand_id, time_range)
            self._create_content_classification_section(brand_id, time_range)
            self._create_trend_analysis_section(brand_id, time_range)
    
    def _get_available_brands(self) -> List[str]:
        """Get list of available brands from Athena"""
        # In production, this would query Athena
        return ["demo_brand", "test_brand", "example_brand"]
    
    def _create_overview_section(self, brand_id: str, time_range: str):
        """Create overview section with key metrics"""
        st.header("📈 Overview")
        
        # Get AR data (mock for now)
        ar_data = self._get_mock_ar_data(brand_id)
        
        # Create metric columns
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Authenticity Ratio",
                value=f"{ar_data['authenticity_ratio_pct']:.1f}%",
                delta=f"{ar_data['delta']:.1f}%"
            )
        
        with col2:
            st.metric(
                label="Total Content",
                value=f"{ar_data['total_items']:,}",
                delta=f"{ar_data['total_delta']:+,}"
            )
        
        with col3:
            st.metric(
                label="Authentic Content",
                value=f"{ar_data['authentic_items']:,}",
                delta=f"{ar_data['authentic_delta']:+,}"
            )
        
        with col4:
            st.metric(
                label="Inauthentic Content",
                value=f"{ar_data['inauthentic_items']:,}",
                delta=f"{ar_data['inauthentic_delta']:+,}"
            )
    
    def _create_authenticity_ratio_section(self, brand_id: str, time_range: str):
        """Create Authenticity Ratio analysis section"""
        st.header("🎯 Authenticity Ratio Analysis")
        
        # Get AR data
        ar_data = self._get_mock_ar_data(brand_id)
        
        # Create two columns for charts
        col1, col2 = st.columns(2)
        
        with col1:
            # Pie chart for classification distribution
            fig_pie = px.pie(
                values=[ar_data['authentic_items'], ar_data['suspect_items'], ar_data['inauthentic_items']],
                names=['Authentic', 'Suspect', 'Inauthentic'],
                title="Content Classification Distribution",
                color_discrete_map={'Authentic': '#2ecc71', 'Suspect': '#f39c12', 'Inauthentic': '#e74c3c'}
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, width="stretch")
        
        with col2:
            # Bar chart for AR comparison
            fig_bar = go.Figure(data=[
                go.Bar(name='Core AR', x=['Current'], y=[ar_data['authenticity_ratio_pct']], marker_color='#3498db'),
                go.Bar(name='Extended AR', x=['Current'], y=[ar_data['extended_ar_pct']], marker_color='#9b59b6')
            ])
            fig_bar.update_layout(
                title="Authenticity Ratio Comparison",
                yaxis_title="Percentage (%)",
                barmode='group'
            )
            st.plotly_chart(fig_bar, width="stretch")
        
        # AR interpretation
        ar_pct = ar_data['authenticity_ratio_pct']
        if ar_pct >= 80:
            status = "🟢 Excellent"
            interpretation = "Your brand has excellent content authenticity. Continue maintaining high standards."
        elif ar_pct >= 60:
            status = "🟡 Good"
            interpretation = "Good authenticity with room for improvement. Focus on verification processes."
        elif ar_pct >= 40:
            status = "🟠 Moderate"
            interpretation = "Moderate authenticity requiring attention. Implement stricter content guidelines."
        else:
            status = "🔴 Poor"
            interpretation = "Poor authenticity requiring immediate action. Review and remove inauthentic content."
        
        st.info(f"**Status**: {status} - {interpretation}")
    
    def _create_dimension_analysis_section(self, brand_id: str, time_range: str):
        """Create 5D Trust Dimensions analysis section"""
        st.header("🔍 5D Trust Dimensions Analysis")
        
        # Get dimension data
        dimension_data = self._get_mock_dimension_data(brand_id)
        
        # Create radar chart for dimension scores
        dimensions = ['Provenance', 'Verification', 'Transparency', 'Coherence', 'Resonance']
        scores = [dimension_data[dim.lower()]['average'] for dim in dimensions]
        
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=scores + [scores[0]],  # Close the radar chart
            theta=dimensions + [dimensions[0]],
            fill='toself',
            name='Current Scores',
            line_color='#3498db'
        ))
        
        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 1]
                )),
            showlegend=True,
            title="5D Trust Dimensions - Radar Chart"
        )
        
        st.plotly_chart(fig_radar, width="stretch")
        
        # Dimension scores table
        st.subheader("Dimension Scores")
        
        dimension_df = pd.DataFrame([
            {
                'Dimension': dim.title(),
                'Average': f"{dimension_data[dim.lower()]['average']:.3f}",
                'Min': f"{dimension_data[dim.lower()]['min']:.3f}",
                'Max': f"{dimension_data[dim.lower()]['max']:.3f}",
                'Std Dev': f"{dimension_data[dim.lower()]['std_dev']:.3f}",
                'Status': self._get_dimension_status(dimension_data[dim.lower()]['average'])
            }
            for dim in dimensions
        ])
        
        st.dataframe(dimension_df, width="stretch")
    
    def _create_content_classification_section(self, brand_id: str, time_range: str):
        """Create content classification analysis section"""
        st.header("📝 Content Classification Analysis")
        
        # Get classification data
        classification_data = self._get_mock_classification_data(brand_id)
        
        # Create classification breakdown
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Classification Summary")
            
            # Classification metrics
            total = classification_data['total']
            authentic_pct = classification_data['authentic'] / total * 100
            suspect_pct = classification_data['suspect'] / total * 100
            inauthentic_pct = classification_data['inauthentic'] / total * 100
            
            st.metric("Authentic", f"{classification_data['authentic']:,}", f"{authentic_pct:.1f}%")
            st.metric("Suspect", f"{classification_data['suspect']:,}", f"{suspect_pct:.1f}%")
            st.metric("Inauthentic", f"{classification_data['inauthentic']:,}", f"{inauthentic_pct:.1f}%")
        
        with col2:
            st.subheader("Action Items")
            
            # Action items based on classification
            if classification_data['inauthentic'] > 0:
                st.warning(f"🚨 {classification_data['inauthentic']} items require immediate attention")
            
            if classification_data['suspect'] > 0:
                st.info(f"⚠️ {classification_data['suspect']} items need verification")
            
            if classification_data['authentic'] > 0:
                st.success(f"✅ {classification_data['authentic']} items are authentic and can be amplified")
    
    def _create_trend_analysis_section(self, brand_id: str, time_range: str):
        """Create trend analysis section"""
        st.header("📈 Trend Analysis")
        
        # Get trend data
        trend_data = self._get_mock_trend_data(brand_id, time_range)
        
        # Create time series chart
        fig_trend = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Authenticity Ratio Over Time', 'Content Volume Over Time'),
            vertical_spacing=0.1
        )
        
        # AR trend
        fig_trend.add_trace(
            go.Scatter(
                x=trend_data['dates'],
                y=trend_data['ar_scores'],
                mode='lines+markers',
                name='Authenticity Ratio',
                line=dict(color='#3498db', width=3)
            ),
            row=1, col=1
        )
        
        # Content volume trend
        fig_trend.add_trace(
            go.Scatter(
                x=trend_data['dates'],
                y=trend_data['content_volumes'],
                mode='lines+markers',
                name='Content Volume',
                line=dict(color='#e74c3c', width=2)
            ),
            row=2, col=1
        )
        
        fig_trend.update_layout(
            height=600,
            showlegend=True,
            title_text="Authenticity Ratio and Content Volume Trends"
        )
        
        fig_trend.update_xaxes(title_text="Date", row=2, col=1)
        fig_trend.update_yaxes(title_text="AR (%)", row=1, col=1)
        fig_trend.update_yaxes(title_text="Volume", row=2, col=1)
        
        st.plotly_chart(fig_trend, width="stretch")
        
        # Trend insights
        st.subheader("Trend Insights")
        
        # Calculate trend direction
        recent_ar = trend_data['ar_scores'][-1]
        previous_ar = trend_data['ar_scores'][-2] if len(trend_data['ar_scores']) > 1 else recent_ar
        ar_trend = recent_ar - previous_ar
        
        if ar_trend > 0:
            trend_icon = "📈"
            trend_text = "improving"
        elif ar_trend < 0:
            trend_icon = "📉"
            trend_text = "declining"
        else:
            trend_icon = "➡️"
            trend_text = "stable"
        
        st.info(f"{trend_icon} **Authenticity Ratio is {trend_text}** ({ar_trend:+.1f} percentage points)")
    
    def _get_mock_ar_data(self, brand_id: str) -> Dict[str, Any]:
        """Get mock AR data for dashboard"""
        return {
            'authenticity_ratio_pct': 72.5,
            'extended_ar_pct': 78.2,
            'total_items': 1250,
            'authentic_items': 906,
            'suspect_items': 250,
            'inauthentic_items': 94,
            'delta': 2.3,
            'total_delta': 150,
            'authentic_delta': 120,
            'inauthentic_delta': -15
        }
    
    def _get_mock_dimension_data(self, brand_id: str) -> Dict[str, Any]:
        """Get mock dimension data for dashboard"""
        return {
            'provenance': {'average': 0.78, 'min': 0.12, 'max': 0.98, 'std_dev': 0.15},
            'verification': {'average': 0.65, 'min': 0.08, 'max': 0.95, 'std_dev': 0.22},
            'transparency': {'average': 0.72, 'min': 0.15, 'max': 0.92, 'std_dev': 0.18},
            'coherence': {'average': 0.70, 'min': 0.20, 'max': 0.88, 'std_dev': 0.16},
            'resonance': {'average': 0.68, 'min': 0.10, 'max': 0.90, 'std_dev': 0.20}
        }
    
    def _get_mock_classification_data(self, brand_id: str) -> Dict[str, Any]:
        """Get mock classification data for dashboard"""
        return {
            'total': 1250,
            'authentic': 906,
            'suspect': 250,
            'inauthentic': 94
        }
    
    def _get_mock_trend_data(self, brand_id: str, time_range: str) -> Dict[str, Any]:
        """Get mock trend data for dashboard"""
        days = 7 if time_range == "Last 7 days" else 30 if time_range == "Last 30 days" else 90
        
        dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days, 0, -1)]
        ar_scores = [70 + i * 0.5 + (i % 3 - 1) * 2 for i in range(len(dates))]
        content_volumes = [100 + i * 2 + (i % 5 - 2) * 10 for i in range(len(dates))]
        
        return {
            'dates': dates,
            'ar_scores': ar_scores,
            'content_volumes': content_volumes
        }
    
    def _get_dimension_status(self, score: float) -> str:
        """Get status emoji for dimension score"""
        if score >= 0.8:
            return "🟢 Excellent"
        elif score >= 0.6:
            return "🟡 Good"
        elif score >= 0.4:
            return "🟠 Moderate"
        else:
            return "🔴 Poor"
