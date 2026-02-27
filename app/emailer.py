import os
import requests
from email.message import EmailMessage
import base64

def send_email(to_email, subject, body, pdf_path=None):
    BREVO_API_KEY = os.getenv("BREVO_API_KEY")
    FROM_EMAIL = os.getenv("FROM_EMAIL", "info@umvuzomedia.co.za")
    FROM_NAME = "Umvuzo Media"
    
    # Prepare attachments if PDF provided
    attachments = []
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_content = f.read()
            encoded_pdf = base64.b64encode(pdf_content).decode('utf-8')
            attachments.append({
                "name": os.path.basename(pdf_path),
                "content": encoded_pdf
            })
    
    # Brevo API payload
    payload = {
        "sender": {
            "name": FROM_NAME,
            "email": FROM_EMAIL
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
        "attachment": attachments if attachments else None
    }
    
    # Remove None values
    payload = {k: v for k, v in payload.items() if v is not None}
    
    # Send via Brevo API (HTTP/HTTPS - port 443, NOT blocked by Render)
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        },
        json=payload,
        timeout=30
    )
    
    if response.status_code != 201:
        raise Exception(f"Brevo API Error: {response.text}")
    
    return True