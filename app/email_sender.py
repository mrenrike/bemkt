# app/email_sender.py
import os, smtplib, zipfile
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

def criar_zip(pasta: Path) -> Path:
    zip_path = pasta / "carrossel.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for png in sorted(pasta.glob("slide_*.png")):
            zf.write(png, png.name)
    return zip_path

def enviar_email_zip(destinatario: str, zip_path: Path, job_id: int):
    host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    port = int(os.getenv("EMAIL_PORT", "587"))
    user = os.getenv("EMAIL_USER", "")
    password = os.getenv("EMAIL_PASSWORD", "")

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = destinatario
    msg["Subject"] = f"🤖 Seu carrossel #{job_id} está pronto!"

    msg.attach(MIMEText(
        "Olá!\n\nSeu carrossel foi gerado com sucesso. Os 7 slides estão em anexo.\n\nBom proveito! 🚀\n\nAgência IA",
        "plain", "utf-8"
    ))

    with open(zip_path, "rb") as f:
        part = MIMEBase("application", "zip")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="carrossel_{job_id}.zip"')
        msg.attach(part)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, destinatario, msg.as_string())
