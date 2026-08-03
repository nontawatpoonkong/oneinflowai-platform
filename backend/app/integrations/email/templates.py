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
    subject = "ยืนยันอีเมล OneFlowAI"
    text = (
        f"รหัสยืนยัน OneFlowAI ของคุณคือ {otp}\n"
        f"รหัสนี้หมดอายุภายใน {minutes} นาที\n"
        "ห้ามเปิดเผยรหัสนี้แก่ผู้อื่น"
    )
    html = (
        "<h1>ยืนยันอีเมล OneFlowAI</h1>"
        f"<p>รหัสยืนยันของคุณคือ <strong>{otp}</strong></p>"
        f"<p>รหัสนี้หมดอายุภายใน {minutes} นาที</p>"
        "<p>ห้ามเปิดเผยรหัสนี้แก่ผู้อื่น</p>"
    )
    return VerificationEmailContent(subject=subject, text=text, html=html)
