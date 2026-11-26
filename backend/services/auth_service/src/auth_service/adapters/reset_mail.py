"""Доставка восстановления: SMTP с TLS либо локальный почтовый ящик разработки."""

import asyncio
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode
from uuid import uuid4

from auth_service.domain.reset import ResetDeliveryError
from auth_service.settings import AuthSettings


class PasswordResetMailer:
    def __init__(self, settings: AuthSettings) -> None:
        self.settings = settings

    async def send(self, email: str, token: str) -> None:
        try:
            await asyncio.to_thread(self._send, email, token)
        except (OSError, smtplib.SMTPException) as error:
            raise ResetDeliveryError() from error

    def _send(self, email: str, token: str) -> None:
        message = EmailMessage()
        message["From"] = self.settings.smtp_sender
        message["To"] = email
        message["Subject"] = "Восстановление пароля ReactiVKS"
        link = self.settings.public_base_url.rstrip("/") + "/reset-password?" + urlencode({"token": token})
        message.set_content(f"Ссылка действует 30 минут и только один раз:\n{link}")
        if self.settings.reset_mail_directory is not None:
            directory = self.settings.reset_mail_directory
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = directory / f"{uuid4()}.eml"
            with path.open("x", encoding="utf-8") as output:
                path.chmod(0o600)
                output.write(message.as_string())
            return
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=5) as smtp:
            smtp.starttls()
            if self.settings.smtp_username:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password.get_secret_value())
            smtp.send_message(message)
