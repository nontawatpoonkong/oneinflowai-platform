"""Provider-neutral email content templates."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VerificationEmailContent:
    subject: str
    text: str
    html: str


def build_verification_email(
    *, otp: str, expires_in_seconds: int
) -> VerificationEmailContent:
    minutes = max(1, expires_in_seconds // 60)
    subject = "รหัสยืนยันอีเมล OneFlowAI"
    text = (
        "OneFlowAI\n\n"
        f"รหัสยืนยันอีเมลของคุณคือ {otp}\n"
        f"รหัสนี้จะหมดอายุภายใน {minutes} นาที\n\n"
        "โปรดอย่าเปิดเผยรหัสนี้แก่บุคคลอื่น\n"
        "หากคุณไม่ได้เป็นผู้ขอรหัสนี้ คุณสามารถเพิกเฉยต่ออีเมลฉบับนี้ได้"
    )
    html = f"""<!doctype html>
<html lang="th">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{subject}</title>
  </head>
  <body style="margin:0;background:#f4f7fb;font-family:Arial,sans-serif;color:#111827">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
      <tr><td align="center" style="padding:32px 16px">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
               style="max-width:560px;background:#ffffff;border-radius:16px">
          <tr><td style="padding:32px">
            <p style="margin:0 0 24px;font-size:20px;font-weight:700;color:#2563eb">
              OneFlowAI
            </p>
            <h1 style="margin:0 0 16px;font-size:24px">รหัสยืนยันอีเมล</h1>
            <p style="margin:0 0 20px;line-height:1.6">ใช้รหัสด้านล่างเพื่อยืนยันอีเมลของคุณ</p>
            <p style="margin:0 0 20px;padding:18px;text-align:center;background:#eff6ff;
                      border-radius:12px;font-size:32px;font-weight:700;letter-spacing:8px">
              {otp}
            </p>
            <p style="margin:0 0 12px;line-height:1.6">
              รหัสนี้จะหมดอายุภายใน {minutes} นาที
            </p>
            <p style="margin:0;color:#b91c1c;line-height:1.6">
              โปรดอย่าเปิดเผยรหัสนี้แก่บุคคลอื่น
            </p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""
    return VerificationEmailContent(subject=subject, text=text, html=html)


def build_password_reset_email(
    *, otp: str, expires_in_seconds: int
) -> VerificationEmailContent:
    minutes = max(1, expires_in_seconds // 60)
    subject = "รหัสรีเซ็ตรหัสผ่าน OneFlowAI"
    text = (
        "OneFlowAI\n\n"
        f"รหัสรีเซ็ตรหัสผ่านของคุณคือ {otp}\n"
        f"รหัสนี้จะหมดอายุภายใน {minutes} นาที\n\n"
        "โปรดอย่าเปิดเผยรหัสนี้แก่บุคคลอื่น ทีมสนับสนุนจะไม่ขอรหัสนี้จากคุณ\n"
        "หากคุณไม่ได้ขอรีเซ็ตรหัสผ่าน โปรดเพิกเฉยต่ออีเมลฉบับนี้"
    )
    html = f"""<!doctype html>
<html lang="th">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
  </head>
  <body style="margin:0;background:#f4f7fb;font-family:Arial,sans-serif;color:#111827">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
      <tr><td align="center" style="padding:32px 16px">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
               style="max-width:560px;background:#fff;border-radius:16px">
          <tr><td style="padding:32px">
            <p style="margin:0 0 24px;font-size:20px;font-weight:700;color:#2563eb">
              OneFlowAI
            </p>
            <h1 style="margin:0 0 16px;font-size:24px">รีเซ็ตรหัสผ่าน</h1>
            <p>ใช้รหัส 6 หลักด้านล่างเพื่อดำเนินการต่อ</p>
            <p style="padding:18px;text-align:center;background:#eff6ff;
                      border-radius:12px;font-size:32px;font-weight:700;
                      letter-spacing:8px">{otp}</p>
            <p>รหัสนี้จะหมดอายุภายใน {minutes} นาที</p>
            <p style="color:#b91c1c">อย่าเปิดเผยรหัสนี้ ทีมสนับสนุนจะไม่ขอรหัสจากคุณ</p>
            <p>หากคุณไม่ได้ขอรีเซ็ตรหัสผ่าน โปรดเพิกเฉยต่ออีเมลนี้</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""
    return VerificationEmailContent(subject=subject, text=text, html=html)
