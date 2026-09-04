from __future__ import annotations

import re
import time
from http.cookies import SimpleCookie
from typing import Iterable
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://gcdn.grapecity.com.cn"
EDIT_URL = (
    f"{BASE_URL}/forum.php?mod=post&action=newthread&fid=230&special=3"
)
DEFAULT_TYPEID = "286"
MAX_TITLE_LENGTH = 80
MAX_COOKIE_LENGTH = 16_000
MAX_CONTENT_LENGTH = 200_000


class ForumPostError(RuntimeError):
    """A safe-to-display error from the GCDN forum posting flow."""


def _load_cookie_jar(raw_cookie: str) -> requests.cookies.RequestsCookieJar:
    cookie = str(raw_cookie or "").strip()
    if cookie.lower().startswith("cookie:"):
        cookie = cookie.split(":", 1)[1].strip()
    if not cookie:
        raise ForumPostError("论坛 Cookie 不能为空")
    if len(cookie) > MAX_COOKIE_LENGTH:
        raise ForumPostError("论坛 Cookie 过长，请确认粘贴的是 Cookie 请求头内容")
    if "\r" in cookie or "\n" in cookie:
        raise ForumPostError("论坛 Cookie 不能包含换行")

    parsed = SimpleCookie()
    try:
        parsed.load(cookie)
    except (TypeError, ValueError) as exc:
        raise ForumPostError("论坛 Cookie 格式无法解析") from exc
    if not parsed:
        raise ForumPostError("论坛 Cookie 格式无法解析")

    # Ignore attributes such as Path/Expires pasted from a browser export and
    # let requests merge any refreshed cookies returned by the GET request.
    jar = requests.cookies.RequestsCookieJar()
    for morsel in parsed.values():
        jar.set(
            morsel.key,
            morsel.value,
            domain="gcdn.grapecity.com.cn",
            path="/",
        )
    return jar


def _decode_page(response: requests.Response) -> str:
    # The forum's legacy form declares GBK even when the HTTP header is vague.
    try:
        return response.content.decode("gbk")
    except UnicodeDecodeError:
        return response.content.decode("utf-8", errors="replace")


def _selected_option_value(element) -> str:
    option = element.find("option", selected=True) or element.find("option")
    return option.get("value", "") if option else ""


def _form_fields(form) -> list[tuple[str, str]]:
    """Extract values that a normal browser submit would send."""

    fields: list[tuple[str, str]] = []
    for element in form.select("input[name], textarea[name], select[name], button[name]"):
        name = element.get("name")
        if not name:
            continue
        if element.has_attr("disabled"):
            continue
        tag = element.name.lower()
        if tag == "input":
            input_type = (element.get("type") or "text").lower()
            if input_type in {"checkbox", "radio"} and not element.has_attr("checked"):
                continue
            if input_type == "file":
                continue
            value = element.get("value", "")
        elif tag == "select":
            value = _selected_option_value(element)
        elif tag == "textarea":
            value = element.text or ""
        else:
            value = element.get("value", "")
        fields.append((str(name), str(value)))
    return fields


def _replace_field(fields: list[tuple[str, str]], name: str, value: str) -> None:
    replaced = False
    result: list[tuple[str, str]] = []
    for key, old_value in fields:
        if key == name:
            if not replaced:
                result.append((name, value))
                replaced = True
            continue
        result.append((key, old_value))
    if not replaced:
        result.append((name, value))
    fields[:] = result


def _field_value(fields: Iterable[tuple[str, str]], name: str) -> str:
    for key, value in fields:
        if key == name:
            return value
    return ""


def _extract_formhash(html: str, fields: Iterable[tuple[str, str]]) -> str:
    formhash = _field_value(fields, "formhash").strip()
    if formhash:
        return formhash
    patterns = (
        r"\bFORMHASH\b\s*[=:]\s*['\"]([0-9a-z]+)['\"]",
        r"\bformhash\b\s*[=:]\s*['\"]([0-9a-z]+)['\"]",
    )
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _encode_gbk_form(fields: Iterable[tuple[str, str]]) -> bytes:
    pairs: list[str] = []
    for key, value in fields:
        try:
            key_bytes = str(key).encode("gbk")
            value_bytes = str(value).encode("gbk")
        except UnicodeEncodeError as exc:
            raise ForumPostError("标题或内容包含论坛 GBK 不支持的字符") from exc
        pairs.append(
            f"{quote_plus(key_bytes, safe='')}={quote_plus(value_bytes, safe='')}"
        )
    return "&".join(pairs).encode("ascii")


def _response_summary(response: requests.Response) -> str:
    text = _decode_page(response)
    compact = " ".join(BeautifulSoup(text, "html.parser").stripped_strings)
    return compact[:500] + ("..." if len(compact) > 500 else "")


def create_forum_post(
    *,
    cookie: str,
    title: str,
    content: str,
    rewardprice: str = "1",
) -> dict[str, str]:
    """Create one topic using a caller-provided, already-authenticated cookie.

    The cookie is held only by this call and is never returned or logged.
    """

    normalized_title = str(title or "").strip()
    normalized_content = str(content or "").replace("\r\n", "\n").strip()
    if not normalized_title:
        raise ForumPostError("论坛帖子标题不能为空")
    if len(normalized_title) > MAX_TITLE_LENGTH:
        raise ForumPostError(f"论坛帖子标题不能超过 {MAX_TITLE_LENGTH} 个字符")
    if not normalized_content:
        raise ForumPostError("论坛帖子内容不能为空")
    if len(normalized_content) > MAX_CONTENT_LENGTH:
        raise ForumPostError("论坛帖子内容过长")
    try:
        normalized_reward = str(int(str(rewardprice or "1").strip()))
    except (TypeError, ValueError) as exc:
        raise ForumPostError("悬赏金币必须是整数") from exc
    if int(normalized_reward) < 0:
        raise ForumPostError("悬赏金币不能为负数")

    cookie_jar = _load_cookie_jar(cookie)
    session = requests.Session()
    session.cookies.update(cookie_jar)
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )

    try:
        page = session.get(EDIT_URL, timeout=20)
        page.raise_for_status()
        html = _decode_page(page)
        soup = BeautifulSoup(html, "html.parser")
        form = soup.select_one("#postform")
        if form is None:
            raise ForumPostError(
                "没有找到论坛发帖表单；Cookie 可能已失效，或论坛要求验证码/访问验证"
            )

        fields = _form_fields(form)
        formhash = _extract_formhash(html, fields)
        if not formhash:
            raise ForumPostError("没有取得 formhash，请刷新论坛登录状态后重试")

        _replace_field(fields, "formhash", formhash)
        _replace_field(fields, "subject", normalized_title)
        _replace_field(fields, "message", normalized_content)
        _replace_field(fields, "rewardprice", normalized_reward)
        _replace_field(fields, "special", "3")
        _replace_field(fields, "typeid", _field_value(fields, "typeid") or DEFAULT_TYPEID)
        _replace_field(fields, "wysiwyg", _field_value(fields, "wysiwyg") or "0")
        _replace_field(fields, "posttime", _field_value(fields, "posttime") or str(int(time.time())))
        _replace_field(fields, "topicsubmit", "true")

        action = urljoin(EDIT_URL, form.get("action") or "")
        if not action.startswith(f"{BASE_URL}/"):
            raise ForumPostError("论坛发帖表单地址不在 GCDN 域名内")
        if "topicsubmit=" not in action.lower():
            action += "&topicsubmit=yes" if "?" in action else "?topicsubmit=yes"
        response = session.post(
            action,
            data=_encode_gbk_form(fields),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": EDIT_URL,
                "Origin": BASE_URL,
            },
            timeout=20,
            allow_redirects=True,
        )
        response.raise_for_status()
    except ForumPostError:
        raise
    except requests.RequestException as exc:
        raise ForumPostError(f"论坛网络请求失败：{exc}") from exc
    finally:
        session.close()

    response_text = _decode_page(response)
    response_url = str(response.url)
    published = bool(
        re.search(
            r"(?:showtopic|viewthread|mod=redirect|(?:tid|ptid)=\d+)",
            response_url,
            re.IGNORECASE,
        )
        or re.search(r"发表成功|发布成功|主题已发布", response_text)
    )
    if not published:
        summary = _response_summary(response)
        raise ForumPostError(f"论坛未确认发布成功：{summary or '服务器返回了未知页面'}")
    return {"url": response_url, "title": normalized_title}
