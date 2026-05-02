"""
🟣 Rally Agent — Universal Channel System
50+ messaging channels. Connect EVERYWHERE.
"""

import os
import asyncio
import json
from typing import Optional, Callable
from abc import ABC, abstractmethod
from datetime import datetime

from cli.theme import Theme


class BaseChannel(ABC):
    """Base class for messaging channels"""
    name: str = "unknown"
    description: str = ""
    emoji: str = "💬"
    requires_config: bool = True

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.connected = False
        self.message_handler: Optional[Callable] = None

    @abstractmethod
    async def connect(self) -> bool:
        pass

    @abstractmethod
    async def send(self, target: str, message: str, **kwargs) -> bool:
        pass

    @abstractmethod
    async def receive(self) -> Optional[dict]:
        pass

    async def disconnect(self):
        self.connected = False

    def on_message(self, handler: Callable):
        self.message_handler = handler

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "emoji": self.emoji,
            "connected": self.connected,
        }


# ═══════════════════════════════════════════════════════════════
# 📱 TIER 1 — Major Messaging Platforms
# ═══════════════════════════════════════════════════════════════

class WhatsAppChannel(BaseChannel):
    name = "whatsapp"
    description = "WhatsApp — via WhatsApp Business API or WA Web"
    emoji = "📱"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", os.environ.get("WHATSAPP_TOKEN", ""))
        phone_id = self.config.get("phone_id", os.environ.get("WHATSAPP_PHONE_ID", ""))
        if not token or not phone_id:
            return False
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"messaging_product": "whatsapp", "to": target, "type": "text", "text": {"body": message}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"https://graph.facebook.com/v18.0/{phone_id}/messages", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class TelegramChannel(BaseChannel):
    name = "telegram"
    description = "Telegram — Bot API"
    emoji = "✈️"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
        if not token:
            return False
        body = {"chat_id": target, "text": message, "parse_mode": "Markdown"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class DiscordChannel(BaseChannel):
    name = "discord"
    description = "Discord — Bot & Webhook"
    emoji = "🎮"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        webhook = self.config.get("webhook_url", "")
        if webhook:
            body = {"content": message}
            async with httpx.AsyncClient() as client:
                resp = await client.post(webhook, json=body)
                return resp.status_code in (200, 204)
        token = self.config.get("token", os.environ.get("DISCORD_BOT_TOKEN", ""))
        if token:
            headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
            body = {"content": message}
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"https://discord.com/api/v10/channels/{target}/messages", headers=headers, json=body)
                return resp.status_code == 200
        return False

    async def receive(self) -> Optional[dict]:
        return None


class SlackChannel(BaseChannel):
    name = "slack"
    description = "Slack — Bot & Webhook"
    emoji = "💼"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        webhook = self.config.get("webhook_url", "")
        if webhook:
            body = {"text": message}
            async with httpx.AsyncClient() as client:
                resp = await client.post(webhook, json=body)
                return resp.status_code == 200
        token = self.config.get("token", os.environ.get("SLACK_BOT_TOKEN", ""))
        if token:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            body = {"channel": target, "text": message}
            async with httpx.AsyncClient() as client:
                resp = await client.post("https://slack.com/api/chat.postMessage", headers=headers, json=body)
                data = resp.json()
                return data.get("ok", False)
        return False

    async def receive(self) -> Optional[dict]:
        return None


class SignalChannel(BaseChannel):
    name = "signal"
    description = "Signal — via signal-cli REST API"
    emoji = "🔒"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("api_url", "http://localhost:8080")
        body = {"message": message, "number": self.config.get("number", ""), "recipients": [target]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/v2/send", json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class iMessageChannel(BaseChannel):
    name = "imessage"
    description = "iMessage — via BlueBubbles or pypush"
    emoji = "🍎"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("api_url", "http://localhost:1234")
        password = self.config.get("password", "")
        headers = {"Authorization": f"Bearer {password}"} if password else {}
        body = {"chatGuid": target, "message": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/api/v1/message/text", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class LineChannel(BaseChannel):
    name = "line"
    description = "LINE — Messaging platform (Japan/Asia)"
    emoji = "🟢"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", os.environ.get("LINE_CHANNEL_TOKEN", ""))
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"to": target, "messages": [{"type": "text", "text": message}]}
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.line.me/v2/bot/message/push", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class ViberChannel(BaseChannel):
    name = "viber"
    description = "Viber — Messaging platform"
    emoji = "💜"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", os.environ.get("VIBER_AUTH_TOKEN", ""))
        headers = {"X-Viber-Auth-Token": token, "Content-Type": "application/json"}
        body = {"receiver": target, "type": "text", "text": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://chatapi.viber.com/pa/send_message", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class WeChatChannel(BaseChannel):
    name = "wechat"
    description = "WeChat — via WeCom/企业微信 API"
    emoji = "💬"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", "")
        body = {"touser": target, "msgtype": "text", "agentid": self.config.get("agent_id", ""), "text": {"content": message}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}", json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


# ═══════════════════════════════════════════════════════════════
# 🏢 TIER 2 — Enterprise & Team Platforms
# ═══════════════════════════════════════════════════════════════

class MicrosoftTeamsChannel(BaseChannel):
    name = "teams"
    description = "Microsoft Teams — Enterprise messaging"
    emoji = "👥"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        webhook = self.config.get("webhook_url", "")
        if webhook:
            body = {"text": message}
            async with httpx.AsyncClient() as client:
                resp = await client.post(webhook, json=body)
                return resp.status_code == 200
        return False

    async def receive(self) -> Optional[dict]:
        return None


class GoogleChatChannel(BaseChannel):
    name = "googlechat"
    description = "Google Chat — Workspace messaging"
    emoji = "🔵"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        webhook = self.config.get("webhook_url", "")
        if webhook:
            body = {"text": message}
            async with httpx.AsyncClient() as client:
                resp = await client.post(webhook, json=body)
                return resp.status_code == 200
        return False

    async def receive(self) -> Optional[dict]:
        return None


class IRCChannel(BaseChannel):
    name = "irc"
    description = "IRC — Internet Relay Chat"
    emoji = "📡"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        # IRC requires persistent TCP connection
        return False

    async def receive(self) -> Optional[dict]:
        return None


class MatrixChannel(BaseChannel):
    name = "matrix"
    description = "Matrix — Decentralized messaging"
    emoji = "🟩"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("homeserver", "https://matrix.org")
        token = self.config.get("token", "")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"msgtype": "m.text", "body": message}
        async with httpx.AsyncClient() as client:
            resp = await client.put(f"{base}/_matrix/client/v3/rooms/{target}/send/m.room.message/1", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class MattermostChannel(BaseChannel):
    name = "mattermost"
    description = "Mattermost — Open-source team messaging"
    emoji = "🔵"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("server_url", "")
        token = self.config.get("token", "")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"channel_id": target, "message": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/api/v4/posts", headers=headers, json=body)
            return resp.status_code == 201

    async def receive(self) -> Optional[dict]:
        return None


class RocketchatChannel(BaseChannel):
    name = "rocketchat"
    description = "Rocket.Chat — Open-source team chat"
    emoji = "🚀"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("server_url", "")
        token = self.config.get("token", "")
        headers = {"X-Auth-Token": token, "X-User-Id": self.config.get("user_id", ""), "Content-Type": "application/json"}
        body = {"channel": target, "text": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/api/v1/chat.postMessage", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class ZulipChannel(BaseChannel):
    name = "zulip"
    description = "Zulip — Threaded team chat"
    emoji = "🔵"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("server_url", "")
        auth = (self.config.get("email", ""), self.config.get("api_key", ""))
        body = {"type": "stream", "to": target, "topic": kwargs.get("topic", "General"), "content": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/api/v1/messages", auth=auth, data=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class FlockChannel(BaseChannel):
    name = "flock"
    description = "Flock — Team messaging"
    emoji = "🐑"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        webhook = self.config.get("webhook_url", "")
        if webhook:
            body = {"text": message}
            async with httpx.AsyncClient() as client:
                resp = await client.post(webhook, json=body)
                return resp.status_code == 200
        return False

    async def receive(self) -> Optional[dict]:
        return None


class TwistChannel(BaseChannel):
    name = "twist"
    description = "Twist — Async team communication"
    emoji = "🌀"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", "")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"channel_id": target, "content": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.twist.com/api/v3/messages/post", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


# ═══════════════════════════════════════════════════════════════
# 📧 TIER 3 — Email & Communication
# ═══════════════════════════════════════════════════════════════

class EmailChannel(BaseChannel):
    name = "email"
    description = "Email — SMTP/IMAP"
    emoji = "📧"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import smtplib
        from email.mime.text import MIMEText
        smtp_host = self.config.get("smtp_host", "smtp.gmail.com")
        smtp_port = self.config.get("smtp_port", 587)
        username = self.config.get("username", os.environ.get("EMAIL_USER", ""))
        password = self.config.get("password", os.environ.get("EMAIL_PASS", ""))
        if not username or not password:
            return False
        msg = MIMEText(message)
        msg["Subject"] = kwargs.get("subject", "Rally Agent Message")
        msg["From"] = username
        msg["To"] = target
        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)
            return True
        except Exception:
            return False

    async def receive(self) -> Optional[dict]:
        return None


class SendGridChannel(BaseChannel):
    name = "sendgrid"
    description = "SendGrid — Email API"
    emoji = "📨"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("api_key", os.environ.get("SENDGRID_API_KEY", ""))
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {
            "personalizations": [{"to": [{"email": target}]}],
            "from": {"email": self.config.get("from_email", "rally@agent.dev")},
            "subject": kwargs.get("subject", "Rally Agent Message"),
            "content": [{"type": "text/plain", "value": message}],
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.sendgrid.com/v3/mail/send", headers=headers, json=body)
            return resp.status_code in (200, 202)

    async def receive(self) -> Optional[dict]:
        return None


class MailgunChannel(BaseChannel):
    name = "mailgun"
    description = "Mailgun — Email API"
    emoji = "🔫"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        api_key = self.config.get("api_key", os.environ.get("MAILGUN_API_KEY", ""))
        domain = self.config.get("domain", "")
        auth = ("api", api_key)
        body = {"from": f"Rally Agent <rally@{domain}>", "to": [target], "subject": kwargs.get("subject", "Rally Agent"), "text": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"https://api.mailgun.net/v3/{domain}/messages", auth=auth, data=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


# ═══════════════════════════════════════════════════════════════
# 🌐 TIER 4 — Social Media
# ═══════════════════════════════════════════════════════════════

class TwitterChannel(BaseChannel):
    name = "twitter"
    description = "X/Twitter — Social media"
    emoji = "🐦"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("bearer_token", os.environ.get("TWITTER_BEARER_TOKEN", ""))
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"text": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.twitter.com/2/tweets", headers=headers, json=body)
            return resp.status_code == 201

    async def receive(self) -> Optional[dict]:
        return None


class RedditChannel(BaseChannel):
    name = "reddit"
    description = "Reddit — Forum platform"
    emoji = "🔴"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", "")
        headers = {"Authorization": f"Bearer {token}", "User-Agent": "RallyAgent/1.0"}
        body = {"text": message, "thing_id": target}
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://oauth.reddit.com/api/comment", headers=headers, data=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class MastodonChannel(BaseChannel):
    name = "mastodon"
    description = "Mastodon — Decentralized social"
    emoji = "🐘"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("instance_url", "https://mastodon.social")
        token = self.config.get("token", "")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"status": message, "visibility": kwargs.get("visibility", "public")}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/api/v1/statuses", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class LinkedInChannel(BaseChannel):
    name = "linkedin"
    description = "LinkedIn — Professional network"
    emoji = "💼"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        return False  # LinkedIn API requires OAuth 2.0

    async def receive(self) -> Optional[dict]:
        return None


class FacebookChannel(BaseChannel):
    name = "facebook"
    description = "Facebook Messenger — via Messenger Platform"
    emoji = "📘"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("page_token", "")
        body = {"recipient": {"id": target}, "message": {"text": message}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"https://graph.facebook.com/v18.0/me/messages?access_token={token}", json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class InstagramChannel(BaseChannel):
    name = "instagram"
    description = "Instagram — via Instagram Graph API"
    emoji = "📸"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", "")
        body = {"recipient": {"id": target}, "message": {"text": message}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"https://graph.instagram.com/v18.0/me/messages?access_token={token}", json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class TikTokChannel(BaseChannel):
    name = "tiktok"
    description = "TikTok — Short video platform"
    emoji = "🎵"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        return False  # TikTok messaging API is limited

    async def receive(self) -> Optional[dict]:
        return None


class YouTubeChannel(BaseChannel):
    name = "youtube"
    description = "YouTube — via YouTube Data API"
    emoji = "📺"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("api_key", "")
        body = {"snippet": {"videoId": target, "topLevelComment": {"snippet": {"textOriginal": message}}}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"https://www.googleapis.com/youtube/v3/commentThreads?part=snippet&key={token}", json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


# ═══════════════════════════════════════════════════════════════
# 🔧 TIER 5 — Developer & Automation
# ═══════════════════════════════════════════════════════════════

class GitHubChannel(BaseChannel):
    name = "github"
    description = "GitHub — Issues, PRs, Discussions"
    emoji = "🐙"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", os.environ.get("GITHUB_TOKEN", ""))
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
        action = kwargs.get("action", "issue_comment")
        if action == "issue_comment":
            body = {"body": message}
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"https://api.github.com/repos/{target}/issues/{kwargs.get('issue_number', 1)}/comments", headers=headers, json=body)
                return resp.status_code == 201
        return False

    async def receive(self) -> Optional[dict]:
        return None


class GitLabChannel(BaseChannel):
    name = "gitlab"
    description = "GitLab — Issues, MRs, Discussions"
    emoji = "🦊"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", "")
        headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
        body = {"body": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"https://gitlab.com/api/v4/projects/{target}/issues/{kwargs.get('issue_iid', 1)}/notes", headers=headers, json=body)
            return resp.status_code == 201

    async def receive(self) -> Optional[dict]:
        return None


class WebhookChannel(BaseChannel):
    name = "webhook"
    description = "Webhook — HTTP POST to any URL"
    emoji = "🔗"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        headers = self.config.get("headers", {})
        headers["Content-Type"] = "application/json"
        body = {"message": message, "timestamp": datetime.now().isoformat(), "source": "rally-agent"}
        body.update(kwargs.get("extra", {}))
        async with httpx.AsyncClient() as client:
            resp = await client.post(target, headers=headers, json=body)
            return resp.status_code < 400

    async def receive(self) -> Optional[dict]:
        return None


class ZapierChannel(BaseChannel):
    name = "zapier"
    description = "Zapier — Automation platform"
    emoji = "⚡"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        webhook = self.config.get("webhook_url", target)
        body = {"message": message, "data": kwargs.get("data", {})}
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class NtfyChannel(BaseChannel):
    name = "ntfy"
    description = "ntfy — Push notifications"
    emoji = "🔔"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("server", "https://ntfy.sh")
        headers = {}
        if self.config.get("token"):
            headers["Authorization"] = f"Bearer {self.config['token']}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/{target}", headers=headers, data=message)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class GotifyChannel(BaseChannel):
    name = "gotify"
    description = "Gotify — Self-hosted push notifications"
    emoji = "📢"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("server_url", "")
        token = self.config.get("token", "")
        body = {"message": message, "title": kwargs.get("title", "Rally Agent"), "priority": kwargs.get("priority", 5)}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/message?token={token}", json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class PushoverChannel(BaseChannel):
    name = "pushover"
    description = "Pushover — Push notifications"
    emoji = "📲"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("api_token", "")
        body = {"token": token, "user": target, "message": message, "title": kwargs.get("title", "Rally Agent")}
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.pushover.net/1/messages.json", data=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class AppriseChannel(BaseChannel):
    name = "apprise"
    description = "Appprise — Universal notification library"
    emoji = "📢"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("server_url", "http://localhost:8000")
        body = {"urls": target, "body": message, "title": kwargs.get("title", "Rally Agent")}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/notify/1/", json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class ShoutrrrChannel(BaseChannel):
    name = "shoutrrr"
    description = "Shoutrrr — Go-based notification router"
    emoji = "📡"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("server_url", "http://localhost:8080")
        body = {"message": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/api/v1/send/{target}", json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


# ═══════════════════════════════════════════════════════════════
# 🎮 TIER 6 — Gaming & Specialized
# ═══════════════════════════════════════════════════════════════

class TwitchChannel(BaseChannel):
    name = "twitch"
    description = "Twitch — Live streaming chat"
    emoji = "🎮"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("oauth_token", "")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"broadcaster_id": target, "moderator_id": self.config.get("moderator_id", ""), "message": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.twitch.tv/helix/chat/messages", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class SteamChannel(BaseChannel):
    name = "steam"
    description = "Steam — Gaming platform"
    emoji = "🎮"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        return False  # Steam chat API is limited

    async def receive(self) -> Optional[dict]:
        return None


# ═══════════════════════════════════════════════════════════════
# 📞 TIER 7 — Voice & SMS
# ═══════════════════════════════════════════════════════════════

class TwilioSMSChannel(BaseChannel):
    name = "twilio_sms"
    description = "Twilio — SMS & Voice"
    emoji = "📞"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        sid = self.config.get("account_sid", os.environ.get("TWILIO_SID", ""))
        token = self.config.get("auth_token", os.environ.get("TWILIO_TOKEN", ""))
        from_num = self.config.get("from_number", "")
        auth = (sid, token)
        body = {"From": from_num, "To": target, "Body": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=auth, data=body)
            return resp.status_code == 201

    async def receive(self) -> Optional[dict]:
        return None


class TwilioWhatsAppChannel(BaseChannel):
    name = "twilio_whatsapp"
    description = "Twilio WhatsApp — WhatsApp via Twilio"
    emoji = "📱"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        sid = self.config.get("account_sid", "")
        token = self.config.get("auth_token", "")
        from_num = f"whatsapp:{self.config.get('from_number', '')}"
        auth = (sid, token)
        body = {"From": from_num, "To": f"whatsapp:{target}", "Body": message}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=auth, data=body)
            return resp.status_code == 201

    async def receive(self) -> Optional[dict]:
        return None


class VonageChannel(BaseChannel):
    name = "vonage"
    description = "Vonage (Nexmo) — SMS & Voice"
    emoji = "📞"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        api_key = self.config.get("api_key", "")
        api_secret = self.config.get("api_secret", "")
        body = {"from": self.config.get("from", "Rally"), "to": target, "text": message, "api_key": api_key, "api_secret": api_secret}
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://rest.nexmo.com/sms/json", data=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class SNSChannel(BaseChannel):
    name = "sns"
    description = "Amazon SNS — Push notifications & SMS"
    emoji = "☁️"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        return False  # Requires boto3

    async def receive(self) -> Optional[dict]:
        return None


# ═══════════════════════════════════════════════════════════════
# 🏠 TIER 8 — IoT & Smart Home
# ═══════════════════════════════════════════════════════════════

class HomeAssistantChannel(BaseChannel):
    name = "homeassistant"
    description = "Home Assistant — Smart home platform"
    emoji = "🏠"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("url", "http://homeassistant.local:8123")
        token = self.config.get("token", "")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"message": message, "title": kwargs.get("title", "Rally Agent")}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/api/services/persistent_notification/create", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class MQTTChannel(BaseChannel):
    name = "mqtt"
    description = "MQTT — IoT messaging protocol"
    emoji = "📡"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        # Requires paho-mqtt
        try:
            import paho.mqtt.publish as publish
            auth = None
            if self.config.get("username"):
                auth = {"username": self.config["username"], "password": self.config.get("password", "")}
            publish.single(
                target,
                message,
                hostname=self.config.get("broker", "localhost"),
                port=self.config.get("port", 1883),
                auth=auth,
            )
            return True
        except Exception:
            return False

    async def receive(self) -> Optional[dict]:
        return None


class AlexaChannel(BaseChannel):
    name = "alexa"
    description = "Amazon Alexa — Voice assistant"
    emoji = "🔵"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        return False  # Requires ASK SDK

    async def receive(self) -> Optional[dict]:
        return None


class GoogleHomeChannel(BaseChannel):
    name = "googlehome"
    description = "Google Home — Voice assistant"
    emoji = "🔴"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        return False  # Requires Google Assistant SDK

    async def receive(self) -> Optional[dict]:
        return None


# ═══════════════════════════════════════════════════════════════
# 📋 TIER 9 — Project Management
# ═══════════════════════════════════════════════════════════════

class JiraChannel(BaseChannel):
    name = "jira"
    description = "Jira — Project management"
    emoji = "📋"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        base = self.config.get("server_url", "")
        auth = (self.config.get("email", ""), self.config.get("api_token", ""))
        body = {"fields": {"project": {"key": target}, "summary": kwargs.get("title", "Rally Agent"), "description": message, "issuetype": {"name": "Task"}}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base}/rest/api/3/issue", auth=auth, json=body)
            return resp.status_code == 201

    async def receive(self) -> Optional[dict]:
        return None


class LinearChannel(BaseChannel):
    name = "linear"
    description = "Linear — Modern project management"
    emoji = "📐"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("api_key", "")
        headers = {"Authorization": token, "Content-Type": "application/json"}
        query = {"query": 'mutation { issueCreate(input: { title: "%s", teamId: "%s" }) { success } }' % (message[:100], target)}
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.linear.app/graphql", headers=headers, json=query)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class NotionChannel(BaseChannel):
    name = "notion"
    description = "Notion — All-in-one workspace"
    emoji = "📝"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", "")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
        body = {"parent": {"page_id": target}, "properties": {"title": [{"text": {"content": message[:100]}}]}}
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.notion.com/v1/pages", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


class AirtableChannel(BaseChannel):
    name = "airtable"
    description = "Airtable — Spreadsheet-database hybrid"
    emoji = "📊"

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def send(self, target: str, message: str, **kwargs) -> bool:
        import httpx
        token = self.config.get("token", "")
        base_id = self.config.get("base_id", "")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"fields": {"Name": message[:100], "Content": message}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"https://api.airtable.com/v0/{base_id}/{target}", headers=headers, json=body)
            return resp.status_code == 200

    async def receive(self) -> Optional[dict]:
        return None


# ═══════════════════════════════════════════════════════════════
# 🎯 Channel Manager — Routes messages to all channels
# ═══════════════════════════════════════════════════════════════

class ChannelManager:
    """Manages all messaging channels"""

    ALL_CHANNELS = {
        # Major Messaging
        "whatsapp": WhatsAppChannel,
        "telegram": TelegramChannel,
        "discord": DiscordChannel,
        "slack": SlackChannel,
        "signal": SignalChannel,
        "imessage": iMessageChannel,
        "line": LineChannel,
        "viber": ViberChannel,
        "wechat": WeChatChannel,
        # Enterprise
        "teams": MicrosoftTeamsChannel,
        "googlechat": GoogleChatChannel,
        "irc": IRCChannel,
        "matrix": MatrixChannel,
        "mattermost": MattermostChannel,
        "rocketchat": RocketchatChannel,
        "zulip": ZulipChannel,
        "flock": FlockChannel,
        "twist": TwistChannel,
        # Email
        "email": EmailChannel,
        "sendgrid": SendGridChannel,
        "mailgun": MailgunChannel,
        # Social
        "twitter": TwitterChannel,
        "reddit": RedditChannel,
        "mastodon": MastodonChannel,
        "linkedin": LinkedInChannel,
        "facebook": FacebookChannel,
        "instagram": InstagramChannel,
        "tiktok": TikTokChannel,
        "youtube": YouTubeChannel,
        # Developer
        "github": GitHubChannel,
        "gitlab": GitLabChannel,
        "webhook": WebhookChannel,
        "zapier": ZapierChannel,
        # Notifications
        "ntfy": NtfyChannel,
        "gotify": GotifyChannel,
        "pushover": PushoverChannel,
        "apprise": AppriseChannel,
        "shoutrrr": ShoutrrrChannel,
        # Gaming
        "twitch": TwitchChannel,
        "steam": SteamChannel,
        # Voice/SMS
        "twilio_sms": TwilioSMSChannel,
        "twilio_whatsapp": TwilioWhatsAppChannel,
        "vonage": VonageChannel,
        "sns": SNSChannel,
        # IoT
        "homeassistant": HomeAssistantChannel,
        "mqtt": MQTTChannel,
        "alexa": AlexaChannel,
        "googlehome": GoogleHomeChannel,
        # Project Management
        "jira": JiraChannel,
        "linear": LinearChannel,
        "notion": NotionChannel,
        "airtable": AirtableChannel,
    }

    def __init__(self, config):
        self.config = config
        self.channels: dict[str, BaseChannel] = {}

    def get_channel(self, name: str) -> Optional[BaseChannel]:
        """Get a channel by name"""
        if name not in self.channels:
            channel_class = self.ALL_CHANNELS.get(name)
            if channel_class:
                channel_config = self.config.get(f"channels.{name}", {})
                self.channels[name] = channel_class(channel_config)
        return self.channels.get(name)

    def get_all_info(self) -> list[dict]:
        """Get info about all channels"""
        return [
            {
                "name": name,
                "description": cls.description,
                "emoji": cls.emoji,
                "configured": bool(self.config.get(f"channels.{name}", {})),
            }
            for name, cls in self.ALL_CHANNELS.items()
        ]

    async def send(self, channel_name: str, target: str, message: str, **kwargs) -> bool:
        """Send a message via a channel"""
        channel = self.get_channel(channel_name)
        if not channel:
            return False
        try:
            return await channel.send(target, message, **kwargs)
        except Exception as e:
            Theme.error(f"Channel {channel_name} error: {e}")
            return False

    async def broadcast(self, target: str, message: str, channels: list[str] = None, **kwargs) -> dict:
        """Broadcast to multiple channels"""
        channels = channels or list(self.ALL_CHANNELS.keys())
        results = {}
        for ch in channels:
            results[ch] = await self.send(ch, target, message, **kwargs)
        return results
