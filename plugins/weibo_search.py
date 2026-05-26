import re
import time
import math
import httpx
from nonebot import on_message
from nonebot.rule import Rule
from nonebot.log import logger
from nonebot.adapters.qq import Bot, C2CMessageCreateEvent, GroupAtMessageCreateEvent

# ============================================================
# 微博搜索插件 — 通过 m.weibo.cn JSON API 搜微博 + 热度排序推荐
# ============================================================

MAX_RESULTS = 5

_cookie_cache: dict[str, str] = {}
_cookie_expiry: float = 0.0

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)


async def _ensure_cookies(client: httpx.AsyncClient) -> dict[str, str]:
    global _cookie_cache, _cookie_expiry

    now = time.time()
    if _cookie_cache and now < _cookie_expiry - 60:
        return _cookie_cache

    await client.get(
        "https://visitor.passport.weibo.cn/visitor/visitor",
        params={
            "entry": "sinawap", "a": "enter",
            "url": "https://m.weibo.cn/", "domain": ".weibo.cn",
        },
    )
    resp = await client.get(
        "https://visitor.passport.weibo.cn/visitor/genvisitor2",
        params={
            "cb": "genvisitor", "ver": "20250916",
            "tid": "", "from": "weibo", "webdriver": "", "rid": "1",
            "return_url": "https://m.weibo.cn/",
        },
        headers={"Referer": "https://visitor.passport.weibo.cn/"},
    )

    cookies = dict(resp.cookies)
    if "SUB" in cookies:
        _cookie_cache = cookies
        _cookie_expiry = now + 1200
        logger.info("[weibo_search] visitor cookies refreshed")
    else:
        logger.warning("[weibo_search] failed to get SUB cookie, resp: %s", resp.text[:200])

    return _cookie_cache


def _parse_results(data: dict) -> list[dict]:
    posts = []
    for card in data.get("data", {}).get("cards", []):
        if card.get("card_type") != 9:
            continue
        mblog = card.get("mblog")
        if not mblog:
            continue
        text = mblog.get("text", "")
        text = re.sub(r"<[^>]+>", "", text).strip()
        text = re.sub(r"\s+", " ", text)
        posts.append({
            "id": mblog.get("id"),
            "user": mblog.get("user", {}).get("screen_name", "?"),
            "text": text,
            "reposts": mblog.get("reposts_count", 0),
            "comments": mblog.get("comments_count", 0),
            "likes": mblog.get("attitudes_count", 0),
            "url": f"https://m.weibo.cn/detail/{mblog.get('id')}",
        })
    return posts


def _select(posts: list[dict], n: int = MAX_RESULTS) -> list[dict]:
    scored = []
    for p in posts:
        score = math.log2(1 + p["reposts"] * 2 + p["comments"] + p["likes"])
        scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)

    seen: set[str] = set()
    result = []
    for _, p in scored:
        if p["user"] in seen:
            continue
        seen.add(p["user"])
        result.append(p)
        if len(result) >= n:
            break
    return result


# ============================================================
# 核心搜索函数 — 可被 NoneBot handler 和 LangGraph tool 复用
# ============================================================

async def search_weibo(keyword: str) -> str:
    """搜索微博，返回格式化的 Top 5 结果文本。"""
    logger.info(f"[weibo_search] searching: {keyword}")

    async with httpx.AsyncClient(
        timeout=15,
        headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    ) as client:
        cookies = await _ensure_cookies(client)
        if not cookies:
            return "微博搜索暂时不可用喵...等会儿再试试喵"

        resp = await client.get(
            "https://m.weibo.cn/api/container/getIndex",
            params={"containerid": f"100103type=1&q={keyword}", "page": 1},
            cookies=cookies,
        )

        if resp.status_code != 200:
            logger.error(f"[weibo_search] API {resp.status_code}")
            return "微博搜不到喵...可能被限速了，过会儿再试喵"

        data = resp.json()
        if data.get("ok") != 1:
            logger.error(f"[weibo_search] API error: {data}")
            return "微博搜索出错了喵..."

        posts = _parse_results(data)
        if not posts:
            return f"没搜到「{keyword}」相关的内容喵...换几个关键词试试喵？"

        selected = _select(posts)

    lines = [f"搜「{keyword}」找到 {len(posts)} 条，推荐 {len(selected)} 条喵：", ""]
    for i, p in enumerate(selected, 1):
        text = p["text"][:120]
        if len(p["text"]) > 120:
            text += "..."
        lines.append(f"{i}. {text}")
        lines.append(f"   @{p['user']} | 转{p['reposts']} 评{p['comments']} 赞{p['likes']}")
        lines.append(f"   {p['url']}")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# 规则 + 处理器（thin wrapper，保留向后兼容）
# ============================================================

PREFIXES = ("/weibo ", "/wb ", "搜微博 ", "搜索微博 ")


def _is_weibo_search(event) -> bool:
    if not isinstance(event, (C2CMessageCreateEvent, GroupAtMessageCreateEvent)):
        return False
    return event.get_plaintext().strip().lower().startswith(PREFIXES)


weibo_cmd = on_message(rule=Rule(_is_weibo_search), priority=50, block=True)


@weibo_cmd.handle()
async def handle_weibo_search(bot: Bot, event):
    raw = event.get_plaintext().strip()
    keyword = ""
    for p in PREFIXES:
        if raw.lower().startswith(p):
            keyword = raw[len(p):].strip()
            break

    if not keyword:
        await bot.send(event, "搜什么喵？用法: /weibo <关键词>")
        return

    try:
        result = await search_weibo(keyword)
        await bot.send(event, result)
    except httpx.TimeoutException:
        logger.error("[weibo_search] timeout")
        await bot.send(event, "搜索超时了喵...微博那边好慢，过会儿再试喵")
    except Exception as e:
        logger.error(f"[weibo_search] error: {e}")
        await bot.send(event, "搜索出错了喵...")
