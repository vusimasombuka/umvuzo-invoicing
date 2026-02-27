from dotenv import load_dotenv
load_dotenv()

from app.emailer import send_email

try:
    send_email(
        to_email="your-test-email@example.com",
        subject="Test from Umvuzo Invoicing",
        body="This is a test email from your invoicing system.",
        pdf_path=None
    )
    print("✅ Email sent successfully!")
except Exception as e:
    print(f"❌ Error: {e}")