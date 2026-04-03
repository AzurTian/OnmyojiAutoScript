# This Python file uses the following encoding: utf-8
# @author runhey (original), enhanced by Claw 🦞
# github https://github.com/runhey
# Webhook support added: 2026-04-03

"""
Notification module with Webhook support.

Supports:
1. Original onepush providers (17+ channels)
2. Native Feishu/Lark Webhook (rich interactive cards)
3. Generic Webhook (DingTalk, WeCom, Slack, Discord, etc.)

Configuration examples (YAML in notify_config):

  # --- Feishu Webhook ---
  provider: feishu_webhook
  webhook_url: https://open.feishu.cn/open-apis/bot/v2/hook/xxx
  card_color: blue  # optional: blue/green/red/yellow/purple

  # --- DingTalk Webhook ---
  provider: dingtalk_webhook
  webhook_url: https://oapi.dingtalk.com/robot/send?access_token=xxx
  secret: SEC...  # optional, for signed mode

  # --- WeCom (企业微信) Webhook ---
  provider: wecom_webhook
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

  # --- Generic Webhook (any URL) ---
  provider: webhook
  webhook_url: https://your-server.com/webhook
  method: post  # post/get, default: post
  headers:      # optional custom headers
    Authorization: Bearer xxx
  template: |   # optional JSON template, {title} and {content} will be replaced
    {"text": "{title}: {content}"}

  # --- Original onepush providers still work ---
  provider: bark
  key: your_bark_key
"""

import hashlib
import hmac
import base64
import time
import json
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import onepush.core
import yaml
import requests
from onepush import get_notifier
from onepush.core import Provider
from onepush.exceptions import OnePushException
from onepush.providers.custom import Custom
from requests import Response
from smtplib import SMTPResponseException

from module.logger import logger

onepush.core.log = logger

# Webhook provider names that we handle natively (bypass onepush)
WEBHOOK_PROVIDERS = {
    'feishu_webhook', 'lark_webhook',
    'dingtalk_webhook', 'dingding_webhook',
    'wecom_webhook', 'wechatwork_webhook',
    'webhook',  # generic
}


class WebhookSender:
    """Handles native Webhook push for various platforms."""

    def __init__(self, provider: str, config: dict):
        self.provider = provider.lower()
        self.config = config
        self.webhook_url = config.get('webhook_url', '')
        self.timeout = config.get('timeout', 10)

    def send(self, title: str, content: str) -> bool:
        """Send notification via webhook. Returns True on success."""
        if not self.webhook_url:
            logger.warning("Webhook URL not configured, skip sending")
            return False

        try:
            if self.provider in ('feishu_webhook', 'lark_webhook'):
                return self._send_feishu(title, content)
            elif self.provider in ('dingtalk_webhook', 'dingding_webhook'):
                return self._send_dingtalk(title, content)
            elif self.provider in ('wecom_webhook', 'wechatwork_webhook'):
                return self._send_wecom(title, content)
            else:
                return self._send_generic(title, content)
        except requests.exceptions.Timeout:
            logger.warning(f"Webhook request timeout ({self.timeout}s)")
            return False
        except requests.exceptions.ConnectionError:
            logger.warning(f"Webhook connection failed: {self.webhook_url}")
            return False
        except Exception as e:
            logger.exception(f"Webhook send failed: {e}")
            return False

    def _send_feishu(self, title: str, content: str) -> bool:
        """Send Feishu/Lark interactive card message."""
        card_color = self.config.get('card_color', 'blue')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"🎮 {title}"},
                    "template": card_color
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": content
                        }
                    },
                    {"tag": "hr"},
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": f"OnmyojiAutoScript | {timestamp}"
                            }
                        ]
                    }
                ]
            }
        }

        resp = requests.post(
            self.webhook_url, json=payload, timeout=self.timeout
        )
        return self._check_feishu_response(resp)

    def _check_feishu_response(self, resp: Response) -> bool:
        """Check Feishu API response."""
        if resp.status_code != 200:
            logger.warning(f"Feishu webhook HTTP {resp.status_code}")
            return False
        data = resp.json()
        code = data.get('code', data.get('StatusCode', -1))
        if code != 0:
            msg = data.get('msg', data.get('StatusMessage', 'unknown'))
            logger.warning(f"Feishu webhook error: {code} - {msg}")
            return False
        return True

    def _send_dingtalk(self, title: str, content: str) -> bool:
        """Send DingTalk webhook message (supports signed mode)."""
        url = self.webhook_url
        secret = self.config.get('secret', '')

        # Sign if secret is provided
        if secret:
            timestamp = str(round(time.time() * 1000))
            string_to_sign = f'{timestamp}\n{secret}'
            hmac_code = hmac.new(
                secret.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                digestmod=hashlib.sha256
            ).digest()
            sign = quote_plus(base64.b64encode(hmac_code))
            url = f"{url}&timestamp={timestamp}&sign={sign}"

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"### {title}\n\n{content}\n\n---\n*OnmyojiAutoScript*"
            }
        }

        resp = requests.post(url, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            logger.warning(f"DingTalk webhook HTTP {resp.status_code}")
            return False
        data = resp.json()
        if data.get('errcode', 0) != 0:
            logger.warning(f"DingTalk error: {data.get('errmsg', 'unknown')}")
            return False
        return True

    def _send_wecom(self, title: str, content: str) -> bool:
        """Send WeCom (企业微信) webhook message."""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"### {title}\n\n{content}\n\n> OnmyojiAutoScript"
            }
        }

        resp = requests.post(
            self.webhook_url, json=payload, timeout=self.timeout
        )
        if resp.status_code != 200:
            logger.warning(f"WeCom webhook HTTP {resp.status_code}")
            return False
        data = resp.json()
        if data.get('errcode', 0) != 0:
            logger.warning(f"WeCom error: {data.get('errmsg', 'unknown')}")
            return False
        return True

    def _send_generic(self, title: str, content: str) -> bool:
        """Send generic webhook message with customizable template."""
        method = self.config.get('method', 'post').lower()
        headers = self.config.get('headers', {})
        template = self.config.get('template', '')

        if template:
            # Use custom template with placeholder replacement
            body_str = template.replace('{title}', title).replace('{content}', content)
            try:
                body = json.loads(body_str)
            except json.JSONDecodeError:
                body = {"text": body_str}
        else:
            # Default JSON body
            body = {
                "title": title,
                "content": content,
                "timestamp": datetime.now().isoformat(),
                "source": "OnmyojiAutoScript"
            }

        if method == 'get':
            resp = requests.get(
                self.webhook_url, params=body,
                headers=headers, timeout=self.timeout
            )
        else:
            resp = requests.post(
                self.webhook_url, json=body,
                headers=headers, timeout=self.timeout
            )

        if resp.status_code not in (200, 201, 204):
            logger.warning(f"Generic webhook HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        return True


class Notifier:
    """
    Unified notification manager.

    Supports both onepush providers and native webhook providers.
    Webhook providers are handled directly without onepush dependency.
    """

    def __init__(self, _config: str, enable: bool = False) -> None:
        self.config_name: str = ""
        self.enable: bool = enable
        self.provider_name: str = ""
        self._webhook_sender: Optional[WebhookSender] = None
        self._onepush_notifier: Optional[Provider] = None
        self.config: dict = {}
        self.required: list = []

        if not self.enable:
            return

        # Parse YAML config
        config = {}
        try:
            for item in yaml.safe_load_all(_config):
                if item:
                    config.update(item)
        except Exception as e:
            logger.error(f"Fail to load notify config: {e}, skip sending")
            return

        self.config = config
        self.provider_name = self.config.pop("provider", None) or ""

        if not self.provider_name:
            logger.info("No provider specified, skip sending")
            return

        # Route to webhook or onepush
        if self.provider_name.lower() in WEBHOOK_PROVIDERS:
            self._init_webhook()
        else:
            self._init_onepush()

    def _init_webhook(self):
        """Initialize native webhook sender."""
        webhook_url = self.config.get('webhook_url', '')
        if not webhook_url:
            logger.warning(
                f"Provider '{self.provider_name}' requires 'webhook_url', "
                f"skip sending"
            )
            return
        self._webhook_sender = WebhookSender(self.provider_name, self.config)
        logger.info(
            f"Webhook notifier initialized: {self.provider_name} -> "
            f"{webhook_url[:50]}..."
        )

    def _init_onepush(self):
        """Initialize onepush provider (original logic)."""
        try:
            self._onepush_notifier = get_notifier(self.provider_name)
            self.required = self._onepush_notifier.params.get("required", [])
        except OnePushException:
            logger.exception("Init onepush notifier failed")
        except Exception as e:
            logger.exception(f"Init notifier error: {e}")

    def push(self, **kwargs) -> bool:
        """
        Send notification.

        Args:
            title: Notification title
            content: Notification body text
            **kwargs: Additional provider-specific parameters

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enable:
            return False

        title = kwargs.get('title', 'Notification')
        content = kwargs.get('content', kwargs.get('message', ''))

        # Prepend config name to title
        if self.config_name:
            title = f"{self.config_name} {title}"

        # Route to appropriate sender
        if self._webhook_sender:
            return self._push_webhook(title, content)
        elif self._onepush_notifier:
            return self._push_onepush(title=title, content=content, **kwargs)
        else:
            logger.warning("No notifier available, skip sending")
            return False

    def _push_webhook(self, title: str, content: str) -> bool:
        """Send via native webhook."""
        try:
            success = self._webhook_sender.send(title, content)
            if success:
                logger.info(f"Webhook notify success: {self.provider_name}")
            else:
                logger.warning(f"Webhook notify failed: {self.provider_name}")
            return success
        except Exception as e:
            logger.exception(f"Webhook push error: {e}")
            return False

    def _push_onepush(self, **kwargs) -> bool:
        """Send via onepush provider (original logic preserved)."""
        kwargs["title"] = kwargs.get("title", "Notification")
        self.config.update(kwargs)

        # Pre-check required params
        for key in self.required:
            if key not in self.config:
                logger.warning(
                    f"Notifier {self._onepush_notifier} require param "
                    f"'{key}' but not provided"
                )

        # Custom provider special handling
        if isinstance(self._onepush_notifier, Custom):
            if "method" not in self.config or self.config["method"] == "post":
                self.config["datatype"] = "json"
            if not ("data" in self.config and isinstance(self.config["data"], dict)):
                self.config["data"] = {}
            if "title" in kwargs:
                self.config["data"]["title"] = kwargs["title"]
            if "content" in kwargs:
                self.config["data"]["content"] = kwargs["content"]

        # gocqhttp special handling
        if self.provider_name.lower() == "gocqhttp":
            access_token = self.config.get("access_token")
            if access_token:
                self.config["token"] = access_token

        try:
            resp = self._onepush_notifier.notify(**self.config)
            if isinstance(resp, Response):
                if resp.status_code != 200:
                    logger.warning(f"Push notify failed! HTTP {resp.status_code}")
                    return False
                if self.provider_name.lower() == "gocqhttp":
                    return_data = resp.json()
                    if return_data.get("status") == "failed":
                        logger.warning(
                            f"Push notify failed: {return_data.get('wording', '')}"
                        )
                        return False
        except SMTPResponseException:
            logger.warning("SMTP response exception")
            return False
        except OnePushException:
            logger.exception("Push notify failed")
            return False
        except Exception as e:
            logger.exception(f"Push error: {e}")
            return False

        logger.info("Push notify success")
        return True
