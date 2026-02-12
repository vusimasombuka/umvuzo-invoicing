import smtplib
from email.message import EmailMessage
import os

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.xneelo.co.za")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))


def send_email(to_email: str, subject: str, body: str, pdf_path: str):

    if not to_email:
        raise Exception("Client has no email address")

    msg = EmailMessage()
    msg["From"] = EMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with open(pdf_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="pdf",
            filename=os.path.basename(pdf_path)
        )

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()   # 🔥 THIS IS THE KEY LINE
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
            print("Email sent successfully!")

    except Exception as e:
        print("EMAIL ERROR:", e)
        raise e
