"""微博搜索工具 — 通过 m.weibo.cn JSON API 搜索 + 热度排序 Top 5。"""

from langchain_core.tools import tool


@tool
async def search_weibo(keyword: str) -> str:
    """搜索微博（中文社交媒体）上的热门帖子。

    当用户要求搜索微博、查找热搜、或用 /weibo 命令时使用此工具。
    返回按热度排序的 Top 5 帖子，包含作者、内容摘要、互动数和链接。

    Args:
        keyword: 搜索关键词
    """
    from plugins.weibo_search import search_weibo as _search
    return await _search(keyword)
