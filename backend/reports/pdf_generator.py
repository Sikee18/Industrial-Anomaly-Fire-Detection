import io
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from db.database import get_stats, get_hotspots

def generate_report_pdf(source: str) -> io.BytesIO:
    """Generate a PDF report for the current dataset and return as BytesIO."""
    stats = get_stats(source=source)
    hotspots = get_hotspots(source=source, limit=5000)

    # Calculate frequencies for charts
    class_counts = {}
    sev_counts = {"High": 0, "Medium": 0, "Low": 0}
    
    for h in hotspots:
        cls = h["classification"]
        class_counts[cls] = class_counts.get(cls, 0) + 1
        sev = h["severity"]
        sev_counts[sev] = sev_counts.get(sev, 0) + 1
        
    top_events = sorted(hotspots, key=lambda x: x["risk_score"], reverse=True)[:5]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = styles["Heading1"]
    title_style.textColor = colors.HexColor("#1e293b")
    h2_style = styles["Heading2"]
    h2_style.textColor = colors.HexColor("#334155")
    normal_style = styles["Normal"]

    story = []

    # Title & Overview
    story.append(Paragraph("Industrial Fire Monitor - Insights & Report", title_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"<b>Data Source:</b> {source.capitalize()}", normal_style))
    story.append(Paragraph(f"<b>Total Anomalies:</b> {stats['total_hotspots']}", normal_style))
    story.append(Paragraph(f"<b>Industrial Fires:</b> {stats['industrial_fires']}", normal_style))
    story.append(Paragraph(f"<b>Gas Flares:</b> {stats['gas_flares']}", normal_style))
    story.append(Paragraph(f"<b>Persistent Sources:</b> {stats['persistent_sources']}", normal_style))
    story.append(Paragraph(f"<b>High Risk Events:</b> {stats['high_risk_events']}", normal_style))
    story.append(Spacer(1, 0.3 * inch))

    # --- Charts Generation ---
    # 1. Classification Pie Chart
    def create_pie_chart(data_dict, title):
        plt.figure(figsize=(4, 3))
        labels = list(data_dict.keys())
        sizes = list(data_dict.values())
        
        # Don't plot if empty
        if not sizes or sum(sizes) == 0:
            plt.text(0.5, 0.5, 'No Data', horizontalalignment='center', verticalalignment='center')
        else:
            # Sort for better visual
            sorted_idx = sorted(range(len(sizes)), key=lambda k: sizes[k], reverse=True)
            labels = [labels[i] for i in sorted_idx]
            sizes = [sizes[i] for i in sorted_idx]
            
            # Group small ones if too many
            if len(labels) > 4:
                main_labels = labels[:3]
                main_sizes = sizes[:3]
                main_labels.append("Other")
                main_sizes.append(sum(sizes[3:]))
                labels = main_labels
                sizes = main_sizes

            plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, textprops={'fontsize': 8})
        
        plt.title(title, fontsize=10)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        plt.close()
        buf.seek(0)
        return buf

    # 2. Severity Donut Chart
    def create_donut_chart(data_dict, title):
        plt.figure(figsize=(4, 3))
        labels = ["High", "Medium", "Low"]
        sizes = [data_dict.get(l, 0) for l in labels]
        colors_list = ["#ef4444", "#f97316", "#22c55e"]
        
        if sum(sizes) == 0:
            plt.text(0.5, 0.5, 'No Data', horizontalalignment='center', verticalalignment='center')
        else:
            plt.pie(sizes, labels=labels, colors=colors_list, autopct='%1.1f%%', startangle=90, textprops={'fontsize': 8})
            # Draw circle for donut
            centre_circle = plt.Circle((0,0),0.70,fc='white')
            fig = plt.gcf()
            fig.gca().add_artist(centre_circle)
            
        plt.title(title, fontsize=10)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        plt.close()
        buf.seek(0)
        return buf

    class_buf = create_pie_chart(class_counts, "Classification Distribution")
    sev_buf = create_donut_chart(sev_counts, "Severity Distribution")

    # Combine charts side-by-side in a table
    c_img1 = Image(class_buf, width=3*inch, height=2.25*inch)
    c_img2 = Image(sev_buf, width=3*inch, height=2.25*inch)
    chart_table = Table([[c_img1, c_img2]])
    story.append(chart_table)
    story.append(Spacer(1, 0.4 * inch))

    # Top 5 Risk Events Table
    story.append(Paragraph("Top 5 Highest-Risk Events", h2_style))
    story.append(Spacer(1, 0.1 * inch))
    
    table_data = [["Class", "Risk", "FRP (MW)", "Conf (%)", "Nearby Facility"]]
    for ev in top_events:
        fac = ev["nearest_facility_name"]
        if fac:
            fac = f"{fac[:20]}... ({ev['nearest_facility_dist_km']:.1f}km)"
        else:
            fac = "None"
            
        table_data.append([
            ev["classification"][:15],
            str(ev["risk_score"]),
            str(ev["frp"]),
            str(ev["confidence_score"]),
            fac
        ])

    t = Table(table_data, colWidths=[1.5*inch, 0.8*inch, 0.9*inch, 0.8*inch, 2.5*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#334155")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 10),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f8fafc")),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor("#cbd5e1")),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('TEXTCOLOR', (0,1), (-1,-1), colors.HexColor("#1e293b")),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5 * inch))
    
    # Attributions
    story.append(Paragraph("<b>Data Sources & Attributions:</b>", normal_style))
    story.append(Paragraph("• Thermal Anomalies: NASA FIRMS (VIIRS & MODIS NRT)", normal_style))
    story.append(Paragraph("• Facilities Context: OpenStreetMap Contributors", normal_style))
    story.append(Paragraph("• Land Cover: ESA WorldCover 10m via Planetary Computer", normal_style))
    story.append(Paragraph("• Weather Data: Open-Meteo API", normal_style))

    doc.build(story)
    buffer.seek(0)
    return buffer
