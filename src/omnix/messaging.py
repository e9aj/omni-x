"""Explicit, credential-scoped messaging adapters for official APIs.

Adapters are transport-only. IntegrationRegistry, channel policy and approval
logic remain the caller's authority; no adapter stores credentials or connects
until the caller supplies an authorised credential and host policy.
"""

from __future__ import annotations

import json
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.parse import quote
import urllib.request
from urllib.request import Request


class MessagingError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class MessageRequest:
    channel: str
    text: str
    recipient: str


class OfficialMessaging:
    def __init__(self, *, credential: str, allowed_hosts: set[str], timeout: float = 10.0):
        if not credential or not allowed_hosts or timeout <= 0 or timeout > 60:
            raise ValueError("messaging adapter configuration is invalid")
        self.credential, self.allowed_hosts, self.timeout = credential, frozenset(allowed_hosts), timeout

    def _post_json(self, url: str, payload: dict, headers: dict[str, str]) -> dict:
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts or parsed.username or parsed.password:
            raise MessagingError("messaging endpoint is not authorised")
        body = json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, headers={**headers, "Content-Type": "application/json"}, method="POST")
        try:
            opener = urllib.request.build_opener(_NoRedirect)
            with opener.open(request, timeout=self.timeout) as response:
                if int(response.headers.get("Content-Length", "0") or 0) > 2_000_000:
                    raise MessagingError("messaging response is too large")
                return json.loads(response.read(2_000_000).decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise MessagingError("messaging request failed") from exc


class TelegramAdapter(OfficialMessaging):
    def send(self, request: MessageRequest) -> dict:
        return self._post_json(f"https://api.telegram.org/bot{quote(self.credential, safe='')}/sendMessage", {"chat_id": request.recipient, "text": request.text}, {})


class DiscordAdapter(OfficialMessaging):
    def send(self, request: MessageRequest) -> dict:
        return self._post_json(f"https://discord.com/api/v10/channels/{quote(request.channel, safe='')}/messages", {"content": request.text}, {"Authorization": f"Bot {self.credential}"})


class SlackAdapter(OfficialMessaging):
    def send(self, request: MessageRequest) -> dict:
        return self._post_json("https://slack.com/api/chat.postMessage", {"channel": request.channel, "text": request.text}, {"Authorization": f"Bearer {self.credential}"})


class WhatsAppAdapter(OfficialMessaging):
    def __init__(self, *, credential: str, phone_number_id: str, allowed_hosts: set[str], timeout: float = 10.0):
        super().__init__(credential=credential, allowed_hosts=allowed_hosts, timeout=timeout)
        self.phone_number_id = phone_number_id

    def send(self, request: MessageRequest) -> dict:
        return self._post_json(f"https://graph.facebook.com/v20.0/{quote(self.phone_number_id, safe='')}/messages", {"messaging_product": "whatsapp", "to": request.recipient, "type": "text", "text": {"body": request.text}}, {"Authorization": f"Bearer {self.credential}"})


class EmailAdapter:
    def __init__(self, *, username: str, password: str, host: str, port: int = 465, timeout: float = 10.0):
        if not username or not password or not host or port not in {465, 587}:
            raise ValueError("email configuration is invalid")
        self.username, self.password, self.host, self.port, self.timeout = username, password, host, port, timeout

    def send(self, request: MessageRequest) -> dict:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self.username, request.recipient, request.channel
        message.set_content(request.text)
        context = ssl.create_default_context()
        try:
            if self.port == 465:
                with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context) as server:
                    server.login(self.username, self.password); server.send_message(message)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as server:
                    server.starttls(context=context); server.login(self.username, self.password); server.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise MessagingError("email request failed") from exc
        return {"sent": True, "recipient": request.recipient}
