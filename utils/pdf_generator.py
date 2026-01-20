from fpdf import FPDF
import tempfile
from fastapi.responses import FileResponse
from datetime import datetime

def generate_invoice_pdf(invoice, customer, plan_name="Subscription Service"):
    pdf = FPDF()
    pdf.add_page()
    
    # Colors
    primary_color = (220, 38, 38) # Skeeter Red
    text_color = (31, 41, 55)     # Dark Gray
    
    # Header
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*primary_color)
    pdf.cell(0, 15, "SKEETERMAN", ln=True, align="L")
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "& TURF NINJA MANAGEMENT", ln=True, align="L")
    pdf.ln(10)
    
    # Invoice Title Header
    pdf.set_fill_color(249, 250, 251)
    pdf.rect(10, 40, 190, 40, "F")
    
    pdf.set_y(45)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*text_color)
    pdf.cell(90, 10, "BILL TO:", ln=False)
    pdf.cell(90, 10, "INVOICE DETAILS:", ln=True)
    
    # Customer and Invoice Info
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(50, 50, 50)
    
    # Line 1
    pdf.set_x(15)
    pdf.cell(90, 5, f"{customer.first_name} {customer.last_name}", ln=False)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(45, 5, "Invoice ID:", ln=False)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(45, 5, f"{invoice.square_invoice_id}", ln=True)
    
    # Line 2
    pdf.set_x(15)
    pdf.cell(90, 5, f"{customer.address or ''}", ln=False)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(45, 5, "Date:", ln=False)
    pdf.set_font("Helvetica", "", 10)
    # Use due_date (synced from Square) instead of local created_at
    display_date = invoice.due_date.strftime('%B %d, %Y') if invoice.due_date else invoice.created_at.strftime('%B %d, %Y')
    pdf.cell(45, 5, f"{display_date}", ln=True)
    
    # Line 3
    pdf.set_x(15)
    pdf.cell(90, 5, f"{customer.city or ''}, {customer.zip_code or ''}", ln=False)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(45, 5, "Status:", ln=False)
    pdf.set_font("Helvetica", "B", 10)
    if invoice.status == "PAID":
        pdf.set_text_color(22, 163, 74) # Green
    pdf.cell(45, 5, f"{invoice.status}", ln=True)
    pdf.set_text_color(50, 50, 50)
    
    pdf.ln(20)
    
    # Table Header
    pdf.set_fill_color(*primary_color)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(140, 10, "  DESCRIPTION", border=0, fill=True)
    pdf.cell(50, 10, "  AMOUNT", border=0, fill=True, align="R")
    pdf.ln(12)
    
    # Table Row
    pdf.set_text_color(*text_color)
    pdf.set_font("Helvetica", "", 11)
            
    pdf.cell(140, 10, f"  {plan_name} Monthly Subscription", border="B")
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(50, 10, f"  ${invoice.amount:.2f}  ", border="B", align="R")
    pdf.ln(20)
    
    # Total
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(140, 10, "TOTAL PAID", align="R")
    pdf.set_fill_color(243, 244, 246)
    pdf.cell(50, 10, f"  ${invoice.amount:.2f}  ", fill=True, align="R")
    
    # Footer
    pdf.set_y(-40)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 10, "Thank you for choosing Skeeterman for your turf management!", align="C", ln=True)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 5, "This is a computer-generated document. No signature required.", align="C")
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        return FileResponse(tmp.name, filename=f"Skeeter_Invoice_{invoice.square_invoice_id}.pdf", media_type="application/pdf")

def generate_one_time_receipt_pdf(order):
    pdf = FPDF()
    pdf.add_page()
    
    # Colors
    primary_color = (220, 38, 38) # Skeeter Red
    text_color = (31, 41, 55)     # Dark Gray
    
    # Header
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*primary_color)
    pdf.cell(0, 15, "SKEETERMAN", ln=True, align="L")
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "& TURF NINJA MANAGEMENT", ln=True, align="L")
    pdf.ln(10)
    
    # Details Header
    pdf.set_fill_color(249, 250, 251)
    pdf.rect(10, 40, 190, 40, "F")
    
    pdf.set_y(45)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*text_color)
    pdf.cell(90, 10, "CUSTOMER:", ln=False)
    pdf.cell(90, 10, "RECEIPT DETAILS:", ln=True)
    
    # Info
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(50, 50, 50)
    
    details = order.customer_details or {}
    name = details.get("name", "Customer")
    address = details.get("address", "")
    
    # Line 1
    pdf.set_x(15)
    pdf.cell(90, 5, f"{name}", ln=False)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(45, 5, "Order ID:", ln=False)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(45, 5, f"#{order.id}", ln=True)
    
    # Line 2
    pdf.set_x(15)
    pdf.cell(90, 5, f"{address}", ln=False)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(45, 5, "Date:", ln=False)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(45, 5, f"{order.created_at.strftime('%B %d, %Y')}", ln=True)
    
    # Line 3
    pdf.set_x(15)
    pdf.cell(90, 5, "", ln=False)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(45, 5, "Status:", ln=False)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(22, 163, 74) # Green
    pdf.cell(45, 5, "PAID", ln=True)
    pdf.set_text_color(50, 50, 50)
    
    pdf.ln(20)
    
    # Table Header
    pdf.set_fill_color(*primary_color)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(140, 10, "  DESCRIPTION", border=0, fill=True)
    pdf.cell(50, 10, "  AMOUNT", border=0, fill=True, align="R")
    pdf.ln(12)
    
    # Table Rows
    pdf.set_text_color(*text_color)
    pdf.set_font("Helvetica", "", 11)
            
    # Base Plan
    pdf.cell(140, 10, f"  {order.plan_name} (One-Time Treatment)", border="B")
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(50, 10, f"  ${order.plan_cost:.2f}  ", border="B", align="R")
    pdf.ln(12)
    
    # Addons
    addons = order.addons or []
    pdf.set_font("Helvetica", "", 11)
    for addon in addons:
        pdf.cell(140, 10, f"  + {addon.get('name', 'Addon')}", border="B")
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(50, 10, f"  ${addon.get('price', 0):.2f}  ", border="B", align="R")
        pdf.ln(12)
        pdf.set_font("Helvetica", "", 11)

    pdf.ln(10)
    
    # Total
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(140, 10, "TOTAL PAID", align="R")
    pdf.set_fill_color(243, 244, 246)
    pdf.cell(50, 10, f"  ${order.total_cost:.2f}  ", fill=True, align="R")
    
    # Footer
    pdf.set_y(-40)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 10, "Thank you for choosing Skeeterman for your turf treatment!", align="C", ln=True)
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        return FileResponse(tmp.name, filename=f"Skeeter_Receipt_{order.id}.pdf", media_type="application/pdf")
