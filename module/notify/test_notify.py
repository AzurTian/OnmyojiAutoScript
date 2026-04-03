#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notification system tests.
Tests both webhook providers and onepush compatibility.

Usage:
    python3 -m pytest module/notify/test_notify.py -v
    python3 module/notify/test_notify.py  # direct run for integration test
"""

import json
import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from module.notify.notify import Notifier, WebhookSender, WEBHOOK_PROVIDERS


class TestWebhookSender(unittest.TestCase):
    """Test WebhookSender for various platforms."""

    def test_feishu_payload_structure(self):
        """Verify Feishu card payload is correctly structured."""
        sender = WebhookSender('feishu_webhook', {
            'webhook_url': 'https://example.com/hook',
            'card_color': 'green'
        })

        with patch('module.notify.notify.requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'StatusCode': 0, 'StatusMessage': 'success'}
            mock_post.return_value = mock_resp

            result = sender.send('Test Title', 'Test Content')

            self.assertTrue(result)
            call_args = mock_post.call_args
            payload = call_args[1]['json'] if 'json' in call_args[1] else call_args[0][1]
            self.assertEqual(payload['msg_type'], 'interactive')
            self.assertIn('card', payload)
            self.assertEqual(payload['card']['header']['template'], 'green')

    def test_dingtalk_payload_structure(self):
        """Verify DingTalk markdown payload."""
        sender = WebhookSender('dingtalk_webhook', {
            'webhook_url': 'https://oapi.dingtalk.com/robot/send?access_token=xxx'
        })

        with patch('module.notify.notify.requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'errcode': 0, 'errmsg': 'ok'}
            mock_post.return_value = mock_resp

            result = sender.send('Test', 'Content')

            self.assertTrue(result)
            payload = mock_post.call_args[1]['json']
            self.assertEqual(payload['msgtype'], 'markdown')

    def test_dingtalk_with_secret(self):
        """Verify DingTalk signed mode adds timestamp and sign."""
        sender = WebhookSender('dingtalk_webhook', {
            'webhook_url': 'https://oapi.dingtalk.com/robot/send?access_token=xxx',
            'secret': 'SECtest123'
        })

        with patch('module.notify.notify.requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'errcode': 0}
            mock_post.return_value = mock_resp

            sender.send('Test', 'Content')

            called_url = mock_post.call_args[0][0]
            self.assertIn('timestamp=', called_url)
            self.assertIn('sign=', called_url)

    def test_wecom_payload_structure(self):
        """Verify WeCom markdown payload."""
        sender = WebhookSender('wecom_webhook', {
            'webhook_url': 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx'
        })

        with patch('module.notify.notify.requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'errcode': 0}
            mock_post.return_value = mock_resp

            result = sender.send('Test', 'Content')

            self.assertTrue(result)
            payload = mock_post.call_args[1]['json']
            self.assertEqual(payload['msgtype'], 'markdown')

    def test_generic_webhook_with_template(self):
        """Verify generic webhook uses custom template."""
        sender = WebhookSender('webhook', {
            'webhook_url': 'https://example.com/hook',
            'template': '{"text": "{title} - {content}"}'
        })

        with patch('module.notify.notify.requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp

            result = sender.send('Hello', 'World')

            self.assertTrue(result)
            payload = mock_post.call_args[1]['json']
            self.assertEqual(payload['text'], 'Hello - World')

    def test_generic_webhook_get_method(self):
        """Verify generic webhook supports GET method."""
        sender = WebhookSender('webhook', {
            'webhook_url': 'https://example.com/hook',
            'method': 'get'
        })

        with patch('module.notify.notify.requests.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_get.return_value = mock_resp

            result = sender.send('Test', 'Content')

            self.assertTrue(result)
            mock_get.assert_called_once()

    def test_empty_webhook_url(self):
        """Verify graceful handling of empty URL."""
        sender = WebhookSender('feishu_webhook', {'webhook_url': ''})
        result = sender.send('Test', 'Content')
        self.assertFalse(result)

    def test_connection_error(self):
        """Verify graceful handling of network errors."""
        sender = WebhookSender('feishu_webhook', {
            'webhook_url': 'https://unreachable.example.com/hook'
        })

        with patch('module.notify.notify.requests.post') as mock_post:
            mock_post.side_effect = ConnectionError("Network unreachable")
            # Should not raise, just return False
            result = sender.send('Test', 'Content')
            self.assertFalse(result)

    def test_timeout_error(self):
        """Verify graceful handling of timeout."""
        sender = WebhookSender('feishu_webhook', {
            'webhook_url': 'https://slow.example.com/hook',
            'timeout': 1
        })

        with patch('module.notify.notify.requests.post') as mock_post:
            import requests as req
            mock_post.side_effect = req.exceptions.Timeout("Timed out")
            result = sender.send('Test', 'Content')
            self.assertFalse(result)


class TestNotifier(unittest.TestCase):
    """Test Notifier class (unified interface)."""

    def test_disabled_notifier(self):
        """Disabled notifier should return False silently."""
        n = Notifier("provider: feishu_webhook", enable=False)
        self.assertFalse(n.push(title='Test', content='Hello'))

    def test_feishu_webhook_config(self):
        """Feishu webhook config should create WebhookSender."""
        config = """
provider: feishu_webhook
webhook_url: https://open.feishu.cn/open-apis/bot/v2/hook/test123
card_color: red
"""
        n = Notifier(config, enable=True)
        self.assertIsNotNone(n._webhook_sender)
        self.assertIsNone(n._onepush_notifier)
        self.assertEqual(n.provider_name, 'feishu_webhook')

    def test_lark_webhook_alias(self):
        """lark_webhook should be treated as feishu_webhook."""
        config = """
provider: lark_webhook
webhook_url: https://open.feishu.cn/open-apis/bot/v2/hook/test123
"""
        n = Notifier(config, enable=True)
        self.assertIsNotNone(n._webhook_sender)

    def test_onepush_provider_config(self):
        """Non-webhook provider should use onepush."""
        config = """
provider: bark
key: test_key
"""
        n = Notifier(config, enable=True)
        self.assertIsNone(n._webhook_sender)
        self.assertIsNotNone(n._onepush_notifier)

    def test_no_provider(self):
        """Missing provider should not crash."""
        n = Notifier("provider: null", enable=True)
        self.assertFalse(n.push(title='Test', content='Hello'))

    def test_invalid_yaml(self):
        """Invalid YAML should not crash."""
        n = Notifier("{{invalid yaml", enable=True)
        self.assertFalse(n.push(title='Test', content='Hello'))

    def test_config_name_prepended(self):
        """Config name should be prepended to title."""
        config = """
provider: feishu_webhook
webhook_url: https://example.com/hook
"""
        n = Notifier(config, enable=True)
        n.config_name = "ACCOUNT1"

        with patch.object(n._webhook_sender, 'send', return_value=True) as mock_send:
            n.push(title='Task Done', content='Hello')
            mock_send.assert_called_once()
            called_title = mock_send.call_args[0][0]
            self.assertTrue(called_title.startswith('ACCOUNT1'))

    def test_push_with_message_kwarg(self):
        """'message' kwarg should be treated as content (backward compat)."""
        config = """
provider: feishu_webhook
webhook_url: https://example.com/hook
"""
        n = Notifier(config, enable=True)

        with patch.object(n._webhook_sender, 'send', return_value=True) as mock_send:
            n.push(title='Test', message='Hello via message')
            called_content = mock_send.call_args[0][1]
            self.assertEqual(called_content, 'Hello via message')

    def test_webhook_providers_set(self):
        """Verify all expected webhook providers are registered."""
        expected = {'feishu_webhook', 'lark_webhook', 'dingtalk_webhook',
                    'dingding_webhook', 'wecom_webhook', 'wechatwork_webhook',
                    'webhook'}
        self.assertEqual(WEBHOOK_PROVIDERS, expected)


# ============================================================
# Integration test (run directly to test real webhook)
# ============================================================
def integration_test():
    """
    Live integration test with real Feishu webhook.
    Run: python3 module/notify/test_notify.py
    """
    print("=" * 60)
    print("🦞 OnmyojiAutoScript Notification System - Integration Test")
    print("=" * 60)

    # Test 1: Feishu Webhook
    feishu_url = os.environ.get(
        'FEISHU_WEBHOOK_URL',
        'https://open.feishu.cn/open-apis/bot/v2/hook/c2564391-d4de-451d-a58e-5cc4e7b16791'
    )

    print(f"\n[Test 1] Feishu Webhook -> {feishu_url[:60]}...")
    config = f"""
provider: feishu_webhook
webhook_url: {feishu_url}
card_color: green
"""
    n = Notifier(config, enable=True)
    n.config_name = "TEST"
    result = n.push(
        title='通知系统集成测试',
        content='**测试项目**:\n- ✅ Feishu Webhook 连通\n- ✅ 富文本卡片发送\n- ✅ 配置解析正常\n\n🦞 Powered by Claw'
    )
    print(f"  Result: {'✅ SUCCESS' if result else '❌ FAILED'}")

    # Test 2: Generic Webhook (same URL, text mode)
    print(f"\n[Test 2] Generic Webhook (text) -> same URL")
    config2 = f"""
provider: webhook
webhook_url: {feishu_url}
template: '{{"msg_type": "text", "content": {{"text": "{{title}}: {{content}}"}}}}'
"""
    n2 = Notifier(config2, enable=True)
    result2 = n2.push(title='Generic Test', content='通用 Webhook 也能发飞书')
    print(f"  Result: {'✅ SUCCESS' if result2 else '❌ FAILED'}")

    print(f"\n{'=' * 60}")
    print(f"Tests complete. Check your Feishu for messages!")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    if '--unit' in sys.argv:
        sys.argv.remove('--unit')
        unittest.main()
    else:
        integration_test()
