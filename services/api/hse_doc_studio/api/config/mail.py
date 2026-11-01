"""Исходящая почта сервера."""

from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class MailConfig(BaseModel):
    """SMTP для писем подтверждения и сброса пароля (HSE_STUDIO__MAIL__*).

    Без host письма не отправляются: ссылки подтверждения показываются на экране, а сброс пароля
    выдаёт администратор.
    """

    host: str | None = Field(default=None, description="SMTP host; empty means mail is off.")
    port: int = Field(default=587, ge=1, le=65535, description="SMTP port.")
    security: Literal["starttls", "tls", "none"] = Field(
        default="starttls", description="starttls upgrades a plain connection, tls connects over TLS at once."
    )
    username: str | None = Field(default=None, description="SMTP login; empty means no authentication.")
    password: SecretStr | None = Field(default=None, description="SMTP password.")
    from_address: str = Field(default="no-reply@localhost", description="Envelope and From address.")
    from_name: str = Field(default="HSE Doc Studio", description="Sender name shown to recipients.")
    timeout_s: float = Field(default=10.0, gt=0, description="Connect and command timeout, seconds.")
