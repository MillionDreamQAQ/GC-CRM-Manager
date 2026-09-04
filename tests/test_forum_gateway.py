import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from fastapi.testclient import TestClient
from requests.cookies import RequestsCookieJar

from crm_support_ui.app import create_app
from crm_support_ui.forum_gateway import ForumPostError, create_forum_post


FORM_HTML = """
<html><body>
  <form id="postform" action="forum.php?mod=post&action=newthread&fid=230&topicsubmit=yes">
    <input type="hidden" name="formhash" value="abc123">
    <input type="hidden" name="posttime" value="1700000000">
    <input type="hidden" name="special" value="3">
    <input type="hidden" name="rewardprice" value="1">
    <select name="typeid"><option value="286" selected>求助</option></select>
    <input name="subject" value="">
    <textarea name="message"></textarea>
    <input name="topicsubmit" value="true">
  </form>
</body></html>
"""


class FakeResponse:
    def __init__(self, body: str, url: str) -> None:
        self.content = body.encode("gbk")
        self.url = url

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self) -> None:
        self.headers = {}
        self.cookies = RequestsCookieJar()
        self.posted = None
        self.closed = False

    def get(self, url, timeout):
        self.get_url = url
        self.get_timeout = timeout
        return FakeResponse(FORM_HTML, url)

    def post(self, url, data, headers, timeout, allow_redirects):
        self.posted = (url, data, headers, timeout, allow_redirects)
        return FakeResponse(
            "<html>发表成功</html>",
            "https://gcdn.grapecity.com.cn/forum.php?mod=viewthread&tid=123",
        )

    def close(self) -> None:
        self.closed = True


class ForumGatewayTests(unittest.TestCase):
    def test_posts_gbk_form_with_fresh_formhash(self) -> None:
        session = FakeSession()
        with patch("crm_support_ui.forum_gateway.requests.Session", return_value=session):
            result = create_forum_post(
                cookie="Cookie: sid=abc; uid=42; Path=/",
                title="中文主题",
                content="第一行\n第二行",
            )

        self.assertIn("tid=123", result["url"])
        self.assertEqual(session.cookies.get("sid"), "abc")
        self.assertEqual(session.cookies.get("uid"), "42")
        self.assertTrue(session.closed)
        posted_url, body, headers, _, allow_redirects = session.posted
        self.assertIn("topicsubmit=yes", posted_url)
        self.assertEqual(headers["Content-Type"], "application/x-www-form-urlencoded")
        self.assertTrue(allow_redirects)
        fields = parse_qs(body.decode("ascii"), encoding="gbk")
        self.assertEqual(fields["formhash"], ["abc123"])
        self.assertEqual(fields["subject"], ["中文主题"])
        self.assertEqual(fields["message"], ["第一行\n第二行"])
        self.assertEqual(fields["typeid"], ["286"])
        self.assertEqual(fields["special"], ["3"])
        self.assertEqual(fields["topicsubmit"], ["true"])

    def test_rejects_empty_cookie_before_network_call(self) -> None:
        with self.assertRaises(ForumPostError):
            create_forum_post(cookie="", title="主题", content="正文")

    def test_forum_endpoint_does_not_return_cookie(self) -> None:
        class FakeGateway:
            pass

        with patch(
            "crm_support_ui.app.send_forum_post",
            return_value={"url": "https://gcdn.grapecity.com.cn/forum.php?tid=123", "title": "主题"},
        ) as send:
            with TestClient(create_app(FakeGateway())) as client:
                response = client.post(
                    "/api/forum-post",
                    json={"cookie": "sid=secret", "title": "主题", "content": "正文"},
                )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertNotIn("cookie", response.json())
        self.assertEqual(send.call_args.kwargs["cookie"], "sid=secret")
        self.assertEqual(send.call_args.kwargs["title"], "主题")
        self.assertEqual(send.call_args.kwargs["content"], "正文")

    def test_forum_endpoint_rejects_overlong_title_before_network_call(self) -> None:
        with patch("crm_support_ui.app.send_forum_post") as send:
            with TestClient(create_app(object())) as client:
                response = client.post(
                    "/api/forum-post",
                    json={
                        "cookie": "sid=secret",
                        "title": "x" * 81,
                        "content": "正文",
                    },
                )

        self.assertEqual(response.status_code, 400)
        self.assertIn("80", response.json()["detail"])
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
