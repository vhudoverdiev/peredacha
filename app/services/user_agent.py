UNKNOWN_BROWSER_LABEL = "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u0431\u0440\u0430\u0443\u0437\u0435\u0440"
UNKNOWN_OS_LABEL = "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0430\u044f \u041e\u0421"
TABLET_LABEL = "\u041f\u043b\u0430\u043d\u0448\u0435\u0442"
PHONE_LABEL = "\u0422\u0435\u043b\u0435\u0444\u043e\u043d"
DESKTOP_LABEL = "\u041a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440"


def visit_browser_label(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if "yabrowser" in ua:
        return "Yandex Browser"
    if "edg/" in ua:
        return "Microsoft Edge"
    if "opr/" in ua or "opera" in ua:
        return "Opera"
    if "chrome/" in ua and "chromium" not in ua:
        return "Google Chrome"
    if "firefox/" in ua:
        return "Mozilla Firefox"
    if "safari/" in ua and "chrome/" not in ua:
        return "Safari"
    if "postmanruntime" in ua:
        return "Postman"
    if "python-requests" in ua:
        return "Python Requests"
    return UNKNOWN_BROWSER_LABEL


def visit_os_label(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if "windows" in ua:
        return "Windows"
    if "iphone" in ua or "ios" in ua:
        return "iPhone (iOS)"
    if "ipad" in ua:
        return "iPadOS"
    if "android" in ua:
        return "Android"
    if "mac os x" in ua or "macintosh" in ua:
        return "macOS"
    if "linux" in ua:
        return "Linux"
    return UNKNOWN_OS_LABEL


def visit_device_label(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if "ipad" in ua or "tablet" in ua:
        return TABLET_LABEL
    if "iphone" in ua or "android" in ua and "mobile" in ua:
        return PHONE_LABEL
    if "mobile" in ua:
        return PHONE_LABEL
    return DESKTOP_LABEL


def is_mobile_phone_user_agent(user_agent: str | None) -> bool:
    ua = (user_agent or "").lower()
    return (
        "iphone" in ua
        or "ipod" in ua
        or "windows phone" in ua
        or "webos" in ua
        or "blackberry" in ua
        or "opera mini" in ua
        or "iemobile" in ua
        or ("android" in ua and "mobile" in ua)
        or ("mobile" in ua and "ipad" not in ua and "tablet" not in ua)
    )
