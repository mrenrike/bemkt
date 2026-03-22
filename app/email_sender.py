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


def _html_email(job_id: int, n_slides: int) -> str:
    app_url = os.getenv("APP_URL", "https://appcarrossel.bemkt.com.br")
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Seu carrossel está pronto — BEMKT</title>
</head>
<body style="margin:0;padding:0;background:#080808;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">

<!-- Wrapper -->
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#080808;padding:40px 16px;">
<tr><td align="center">

  <!-- Card -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="max-width:560px;background:#111111;border-radius:16px;border:1px solid #1e1e1e;overflow:hidden;">

    <!-- Top accent bar -->
    <tr>
      <td style="height:4px;background:linear-gradient(90deg,#8cff2e,#ff6a00);font-size:0;line-height:0;">&nbsp;</td>
    </tr>

    <!-- Logo header -->
    <tr>
      <td align="center" style="padding:36px 40px 28px;">
        <span style="font-size:22px;font-weight:900;color:#f0f0f0;letter-spacing:-0.5px;">
          BEMKT<span style="color:#8cff2e;">.</span>
        </span>
      </td>
    </tr>

    <!-- Hero text -->
    <tr>
      <td align="center" style="padding:0 40px 8px;">
        <p style="margin:0;font-size:28px;font-weight:800;color:#f0f0f0;letter-spacing:-1px;line-height:1.2;">
          Seu carrossel está pronto! 🎉
        </p>
      </td>
    </tr>
    <tr>
      <td align="center" style="padding:12px 40px 32px;">
        <p style="margin:0;font-size:15px;color:#666666;line-height:1.6;">
          {n_slides} slides em 1080×1080px gerados com sucesso.<br>
          O arquivo ZIP está em anexo neste e-mail.
        </p>
      </td>
    </tr>

    <!-- Divider -->
    <tr>
      <td style="padding:0 40px;">
        <div style="height:1px;background:#1e1e1e;font-size:0;">&nbsp;</div>
      </td>
    </tr>

    <!-- Steps -->
    <tr>
      <td style="padding:28px 40px 8px;">
        <p style="margin:0 0 16px;font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:#444;">
          PRÓXIMOS PASSOS
        </p>

        <!-- Step 1 -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:14px;">
          <tr>
            <td width="36" valign="top">
              <div style="width:28px;height:28px;background:rgba(140,255,46,.12);border-radius:8px;
                          text-align:center;line-height:28px;font-size:13px;font-weight:800;color:#8cff2e;">1</div>
            </td>
            <td style="padding-left:12px;">
              <p style="margin:0;font-size:14px;font-weight:700;color:#f0f0f0;">Abra o arquivo ZIP em anexo</p>
              <p style="margin:4px 0 0;font-size:13px;color:#555;">Extraia os {n_slides} slides PNG na sua pasta de fotos.</p>
            </td>
          </tr>
        </table>

        <!-- Step 2 -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:14px;">
          <tr>
            <td width="36" valign="top">
              <div style="width:28px;height:28px;background:rgba(140,255,46,.12);border-radius:8px;
                          text-align:center;line-height:28px;font-size:13px;font-weight:800;color:#8cff2e;">2</div>
            </td>
            <td style="padding-left:12px;">
              <p style="margin:0;font-size:14px;font-weight:700;color:#f0f0f0;">Copie a legenda do post</p>
              <p style="margin:4px 0 0;font-size:13px;color:#555;">Acesse a plataforma para copiar a legenda gerada por IA.</p>
            </td>
          </tr>
        </table>

        <!-- Step 3 -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
          <tr>
            <td width="36" valign="top">
              <div style="width:28px;height:28px;background:rgba(140,255,46,.12);border-radius:8px;
                          text-align:center;line-height:28px;font-size:13px;font-weight:800;color:#8cff2e;">3</div>
            </td>
            <td style="padding-left:12px;">
              <p style="margin:0;font-size:14px;font-weight:700;color:#f0f0f0;">Publique no Instagram</p>
              <p style="margin:4px 0 0;font-size:13px;color:#555;">Crie uma nova publicação, selecione os {n_slides} slides em ordem e cole a legenda.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- CTA button -->
    <tr>
      <td align="center" style="padding:28px 40px 36px;">
        <a href="{app_url}/static/preview.html"
           style="display:inline-block;background:#8cff2e;color:#080808;font-size:15px;font-weight:800;
                  text-decoration:none;padding:14px 36px;border-radius:100px;letter-spacing:-0.2px;">
          Acessar meu carrossel →
        </a>
      </td>
    </tr>

    <!-- Divider -->
    <tr>
      <td style="padding:0 40px;">
        <div style="height:1px;background:#1e1e1e;font-size:0;">&nbsp;</div>
      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td align="center" style="padding:24px 40px 32px;">
        <p style="margin:0 0 6px;font-size:12px;color:#333;">
          Quer criar mais carrosseis?
          <a href="{app_url}/static/chat.html" style="color:#8cff2e;text-decoration:none;font-weight:600;">
            Acesse a plataforma →
          </a>
        </p>
        <p style="margin:0;font-size:11px;color:#2a2a2a;">
          © 2025 BEMKT Carrosseis ·
          <a href="mailto:bruno@bemkt.com.br" style="color:#2a2a2a;text-decoration:none;">bruno@bemkt.com.br</a>
        </p>
      </td>
    </tr>

  </table>
  <!-- /Card -->

</td></tr>
</table>

</body>
</html>"""


def _texto_email(n_slides: int) -> str:
    return (
        f"Seu carrossel está pronto!\n\n"
        f"{n_slides} slides em 1080×1080px gerados com sucesso.\n"
        f"O arquivo ZIP está em anexo neste e-mail.\n\n"
        f"Próximos passos:\n"
        f"1. Abra o ZIP em anexo e extraia os slides\n"
        f"2. Acesse a plataforma para copiar a legenda do post\n"
        f"3. Publique no Instagram selecionando os {n_slides} slides em ordem\n\n"
        f"Bom proveito!\n\nBEMKT Carrosseis\nhttps://appcarrossel.bemkt.com.br"
    )


def enviar_email_zip(destinatario: str, zip_path: Path, job_id: int):
    import re
    # Valida email e previne header injection
    destinatario = destinatario.strip().lower()
    if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', destinatario):
        raise ValueError("Email de destino inválido")
    if any(c in destinatario for c in ['\r', '\n', '\0', ',', ';']):
        raise ValueError("Email de destino inválido")

    host     = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    port     = int(os.getenv("EMAIL_PORT", "587"))
    user     = os.getenv("EMAIL_USER", "")
    password = os.getenv("EMAIL_PASSWORD", "")

    # Conta slides no ZIP para personalizar o e-mail
    try:
        with zipfile.ZipFile(zip_path) as zf:
            n_slides = len([n for n in zf.namelist() if n.endswith(".png")])
    except Exception:
        n_slides = 7

    msg = MIMEMultipart("alternative")
    msg["From"]    = f"BEMKT Carrosseis <{user}>"
    msg["To"]      = destinatario
    msg["Subject"] = f"Seu carrossel está pronto — BEMKT 🎉"

    msg.attach(MIMEText(_texto_email(n_slides), "plain", "utf-8"))
    msg.attach(MIMEText(_html_email(job_id, n_slides), "html", "utf-8"))

    # Anexa o ZIP
    zip_part = MIMEBase("application", "zip")
    with open(zip_path, "rb") as f:
        zip_part.set_payload(f.read())
    encoders.encode_base64(zip_part)
    zip_part.add_header("Content-Disposition", f'attachment; filename="carrossel_{job_id}.zip"')
    msg.attach(zip_part)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, destinatario, msg.as_string())
