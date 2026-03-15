#!/usr/bin/env python3
"""B 站数据获取工具 - 通过 bilibili-api-python 获取 B 站公开数据"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime

# ── 依赖检查 ──────────────────────────────────────────────────────────────────
try:
    from bilibili_api import video, search, user, comment, hot, Credential, sync
    from bilibili_api.comment import CommentResourceType, OrderType
except ImportError:
    print(json.dumps({
        "error": "bilibili-api-python 未安装",
        "fix": "pip install bilibili-api-python aiohttp"
    }))
    sys.exit(1)

logger = logging.getLogger(__name__)

# ── URL / BV 号解析 ──────────────────────────────────────────────────────────
def extract_bvid(text: str) -> str | None:
    """从 URL 或文本中提取 BV 号"""
    m = re.search(r'(BV[a-zA-Z0-9]{10})', text)
    return m.group(1) if m else None

def extract_uid(text: str) -> int | None:
    """从 URL 或文本中提取用户 UID"""
    m = re.search(r'space\.bilibili\.com/(\d+)', text)
    return int(m.group(1)) if m else None

def get_bvid(args) -> str:
    """从 args 获取 bvid，支持 --bvid 和 --url"""
    if hasattr(args, 'bvid') and args.bvid:
        bvid = extract_bvid(args.bvid) or args.bvid
        return bvid
    if hasattr(args, 'url') and args.url:
        bvid = extract_bvid(args.url)
        if bvid:
            return bvid
    print(json.dumps({"error": "请提供 --bvid 或 --url 参数"}))
    sys.exit(1)

def get_credential() -> Credential | None:
    """从环境变量获取 Credential"""
    sessdata = os.environ.get('BILI_SESSDATA')
    if sessdata:
        return Credential(sessdata=sessdata)
    return None

def output(data):
    """统一 JSON 输出"""
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))

# ── 子命令实现 ────────────────────────────────────────────────────────────────

async def cmd_video(args):
    """获取视频信息"""
    bvid = get_bvid(args)
    v = video.Video(bvid=bvid, credential=get_credential())

    info = await v.get_info()
    stat = info.get('stat', {})

    # 获取标签
    tags = []
    try:
        tag_list = await v.get_tags()
        tags = [t.get('tag_name', '') for t in tag_list]
    except Exception:
        pass

    # 获取分P列表
    pages = info.get('pages', [])
    page_list = [{"index": p.get('page', i+1), "title": p.get('part', ''), "duration": p.get('duration', 0)} for i, p in enumerate(pages)]

    result = {
        "bvid": info.get('bvid'),
        "aid": info.get('aid'),
        "title": info.get('title'),
        "description": info.get('desc'),
        "duration": info.get('duration'),
        "cover": info.get('pic'),
        "publish_time": datetime.fromtimestamp(info.get('pubdate', 0)).isoformat(),
        "up": {
            "uid": info.get('owner', {}).get('mid'),
            "name": info.get('owner', {}).get('name'),
            "face": info.get('owner', {}).get('face'),
        },
        "stats": {
            "view": stat.get('view'),
            "like": stat.get('like'),
            "coin": stat.get('coin'),
            "favorite": stat.get('favorite'),
            "share": stat.get('share'),
            "danmaku": stat.get('danmaku'),
            "reply": stat.get('reply'),
        },
        "tags": tags,
        "pages": page_list,
        "subtitle_languages": [
            {"lan": s.get('lan'), "lan_doc": s.get('lan_doc')}
            for s in info.get('subtitle', {}).get('list', [])
        ],
    }
    output(result)


async def _fetch_subtitle(v, info, page=0, lang=None):
    """获取字幕的通用逻辑，返回字幕结果字典"""
    credential = v.credential
    pages = info.get('pages', [])
    cid = pages[page]['cid'] if page < len(pages) else None

    if not credential:
        # 无登录态，尝试从 get_info 获取字幕列表（仅CC字幕可能可用）
        subtitle_list = info.get('subtitle', {}).get('list', [])
        if subtitle_list:
            return {
                "status": "need_sessdata",
                "message": "下载字幕内容需要配置 SESSDATA",
                "available_languages": [{"lan": s.get('lan'), "lan_doc": s.get('lan_doc')} for s in subtitle_list],
            }
        return {"status": "no_subtitles", "message": "该视频没有可用字幕（配置 SESSDATA 可获取 AI 字幕）"}

    # 有登录态，直接调用 get_subtitle（通过 /x/player/wbi/v2 接口）
    # 这个接口比 get_info 更可靠，能获取 AI 字幕
    try:
        subtitle_data = await v.get_subtitle(cid=cid)
        subtitles = subtitle_data.get('subtitles', []) if subtitle_data else []

        if not subtitles:
            return {"status": "no_subtitles", "message": "该视频没有可用字幕"}

        # 选择字幕语言
        target = None
        if lang:
            for s in subtitles:
                if s.get('lan') == lang:
                    target = s
                    break
        if not target:
            # 优先中文（ai-zh > zh-CN > zh > 其他含zh的）
            for prefix in ['ai-zh', 'zh-CN', 'zh']:
                for s in subtitles:
                    if s.get('lan', '').startswith(prefix):
                        target = s
                        break
                if target:
                    break
            if not target:
                for s in subtitles:
                    if 'zh' in s.get('lan', ''):
                        target = s
                        break
        if not target:
            target = subtitles[0]

        # 下载字幕内容
        subtitle_url = target.get('subtitle_url', '')
        if subtitle_url.startswith('//'):
            subtitle_url = 'https:' + subtitle_url

        if not subtitle_url:
            return {
                "status": "no_url",
                "message": "字幕 URL 为空（SESSDATA 可能已过期）",
                "available_languages": [{"lan": s.get('lan'), "lan_doc": s.get('lan_doc')} for s in subtitles],
            }

        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(subtitle_url) as resp:
                sub_json = await resp.json()

        # 转为纯文本（带时间戳）
        lines = []
        for item in sub_json.get('body', []):
            start = item.get('from', 0)
            end = item.get('to', 0)
            content = item.get('content', '')
            m_s, s_s = divmod(int(start), 60)
            m_e, s_e = divmod(int(end), 60)
            lines.append(f"[{m_s:02d}:{s_s:02d}-{m_e:02d}:{s_e:02d}] {content}")

        return {
            "status": "ok",
            "language": target.get('lan_doc', target.get('lan')),
            "available_languages": [{"lan": s.get('lan'), "lan_doc": s.get('lan_doc')} for s in subtitles],
            "subtitle_count": len(lines),
            "text": "\n".join(lines),
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


async def cmd_subtitle(args):
    """获取视频字幕"""
    bvid = get_bvid(args)
    credential = get_credential()
    v = video.Video(bvid=bvid, credential=credential)
    page = getattr(args, 'page', 0) or 0
    lang = getattr(args, 'lang', None)

    info = await v.get_info()
    result = await _fetch_subtitle(v, info, page=page, lang=lang)
    result["video_title"] = info.get('title')
    output(result)


async def cmd_danmaku(args):
    """获取弹幕"""
    bvid = get_bvid(args)
    v = video.Video(bvid=bvid, credential=get_credential())
    page = getattr(args, 'page', 0) or 0

    info = await v.get_info()
    pages = info.get('pages', [])
    cid = pages[page]['cid'] if page < len(pages) else None

    dms = await v.get_danmakus(cid=cid)

    dm_list = sorted([
        {
            "time": round(dm.dm_time, 2),
            "text": dm.text,
            "send_time": datetime.fromtimestamp(dm.send_time).isoformat() if dm.send_time else None,
            "mode": dm.mode.value if hasattr(dm.mode, 'value') else dm.mode,
            "color": dm.color,
        }
        for dm in dms
    ], key=lambda x: x['time'])

    output({
        "video_title": info.get('title'),
        "bvid": bvid,
        "page": page,
        "danmaku_count": len(dm_list),
        "danmakus": dm_list,
    })


async def cmd_comments(args):
    """获取评论"""
    bvid = get_bvid(args)
    v = video.Video(bvid=bvid, credential=get_credential())
    info = await v.get_info()
    aid = info['aid']
    limit = getattr(args, 'limit', 20) or 20
    sort = getattr(args, 'sort', 'hot') or 'hot'

    order = OrderType.LIKE if sort == 'hot' else OrderType.TIME

    all_comments = []
    page_num = 1
    while len(all_comments) < limit:
        try:
            data = await comment.get_comments(
                oid=aid,
                type_=CommentResourceType.VIDEO,
                page_index=page_num,
                order=order,
                credential=get_credential(),
            )
        except Exception:
            break

        replies = data.get('replies') or []
        if not replies:
            break

        for r in replies:
            if len(all_comments) >= limit:
                break
            c = {
                "user": r.get('member', {}).get('uname'),
                "uid": r.get('member', {}).get('mid'),
                "content": r.get('content', {}).get('message'),
                "like": r.get('like'),
                "reply_count": r.get('rcount'),
                "time": datetime.fromtimestamp(r.get('ctime', 0)).isoformat(),
            }
            # 包含热门子评论
            sub_replies = r.get('replies') or []
            if sub_replies:
                c['top_replies'] = [
                    {
                        "user": sr.get('member', {}).get('uname'),
                        "content": sr.get('content', {}).get('message'),
                        "like": sr.get('like'),
                    }
                    for sr in sub_replies[:3]
                ]
            all_comments.append(c)
        page_num += 1

    output({
        "video_title": info.get('title'),
        "bvid": bvid,
        "sort": sort,
        "comment_count": len(all_comments),
        "comments": all_comments,
    })


async def cmd_search(args):
    """搜索B站"""
    keyword = args.keyword
    limit = getattr(args, 'limit', 20) or 20
    sort = getattr(args, 'sort', None)
    search_type = getattr(args, 'type', 'video') or 'video'

    # search_by_type 用于视频搜索
    page = 1
    all_results = []

    while len(all_results) < limit:
        try:
            kwargs = {
                "keyword": keyword,
                "search_type": search.SearchObjectType.VIDEO,
                "page": page,
            }
            if sort:
                kwargs["order_type"] = search.OrderVideo[sort.upper()] if hasattr(search.OrderVideo, sort.upper()) else None
                if kwargs["order_type"] is None:
                    # Try direct value
                    kwargs.pop("order_type")

            data = await search.search_by_type(**kwargs)
        except Exception as e:
            logger.debug(f"Search error: {e}")
            # Fallback to basic search
            try:
                data = await search.search(keyword=keyword, page=page)
                if isinstance(data, dict) and 'result' in data:
                    # Basic search returns nested structure
                    video_results = []
                    for group in data.get('result', []):
                        if isinstance(group, dict) and group.get('result_type') == 'video':
                            video_results = group.get('data', [])
                            break
                    data = {"result": video_results}
            except Exception as e2:
                output({"error": f"搜索失败: {e2}"})
                return
            break

        results = data.get('result', [])
        if not results:
            break

        for r in results:
            if len(all_results) >= limit:
                break
            # 清理 HTML 标签
            title = re.sub(r'<[^>]+>', '', r.get('title', ''))
            all_results.append({
                "bvid": r.get('bvid'),
                "title": title,
                "description": r.get('description', '')[:200],
                "duration": r.get('duration'),
                "play": r.get('play'),
                "danmaku": r.get('danmaku'),
                "like": r.get('like'),
                "up_name": r.get('author'),
                "up_uid": r.get('mid'),
                "publish_time": r.get('pubdate_text', '') or (
                    datetime.fromtimestamp(r['pubdate']).isoformat() if r.get('pubdate') else ''
                ),
                "url": f"https://www.bilibili.com/video/{r.get('bvid')}",
            })
        page += 1

    output({
        "keyword": keyword,
        "result_count": len(all_results),
        "results": all_results,
    })


async def cmd_user(args):
    """获取用户信息"""
    uid = None
    if args.uid:
        uid = args.uid
    elif args.url:
        uid = extract_uid(args.url)

    if not uid:
        output({"error": "请提供 --uid 或 --url 参数"})
        return

    u = user.User(uid=uid, credential=get_credential())
    info = await u.get_user_info()

    result = {
        "uid": uid,
        "name": info.get('name'),
        "sign": info.get('sign'),
        "face": info.get('face'),
        "level": info.get('level'),
        "sex": info.get('sex'),
        "fans_badge": info.get('fans_badge'),
        "official": info.get('official', {}).get('title', ''),
        "vip_type": info.get('vip', {}).get('type'),
    }

    # 获取关注/粉丝等统计（通过 get_relation_info）
    try:
        rel = await u.get_relation_info()
        result["stats"] = {
            "following": rel.get('following'),
            "follower": rel.get('follower'),
        }
    except Exception:
        pass

    # 获取视频列表（可选）
    if getattr(args, 'videos', False):
        limit = getattr(args, 'limit', 10) or 10
        try:
            vids = await u.get_videos(pn=1, ps=min(limit, 50))
            vid_list = vids.get('list', {}).get('vlist', [])
            result["videos"] = [
                {
                    "bvid": v.get('bvid'),
                    "title": v.get('title'),
                    "play": v.get('play'),
                    "duration": v.get('length'),
                    "publish_time": datetime.fromtimestamp(v.get('created', 0)).isoformat(),
                    "description": v.get('description', '')[:200],
                }
                for v in vid_list[:limit]
            ]
        except Exception as e:
            result["videos_error"] = str(e)

    output(result)


async def cmd_hot(args):
    """获取热门视频"""
    limit = getattr(args, 'limit', 20) or 20
    weekly = getattr(args, 'weekly', False)

    if weekly:
        try:
            # 获取每周必看
            weeks = await hot.get_weekly_hot_videos_list()
            if weeks:
                latest = weeks[-1]
                week_num = latest.get('number')
                data = await hot.get_weekly_hot_videos(week_num)
                videos = data[:limit]
                output({
                    "type": "weekly",
                    "week_number": week_num,
                    "week_name": latest.get('name', ''),
                    "video_count": len(videos),
                    "videos": [
                        {
                            "bvid": v.get('bvid'),
                            "title": v.get('title'),
                            "description": v.get('desc', '')[:200],
                            "play": v.get('stat', {}).get('view'),
                            "like": v.get('stat', {}).get('like'),
                            "up_name": v.get('owner', {}).get('name'),
                            "up_uid": v.get('owner', {}).get('mid'),
                            "duration": v.get('duration'),
                            "url": f"https://www.bilibili.com/video/{v.get('bvid')}",
                            "rcmd_reason": v.get('rcmd_reason', ''),
                        }
                        for v in videos
                    ],
                })
                return
        except Exception as e:
            output({"error": f"获取每周必看失败: {e}"})
            return

    # 获取热门视频
    try:
        data = await hot.get_hot_videos(pn=1, ps=min(limit, 50))
        videos = data.get('list', [])[:limit]
        output({
            "type": "hot",
            "video_count": len(videos),
            "videos": [
                {
                    "bvid": v.get('bvid'),
                    "title": v.get('title'),
                    "description": v.get('desc', '')[:200],
                    "play": v.get('stat', {}).get('view'),
                    "like": v.get('stat', {}).get('like'),
                    "up_name": v.get('owner', {}).get('name'),
                    "up_uid": v.get('owner', {}).get('mid'),
                    "duration": v.get('duration'),
                    "url": f"https://www.bilibili.com/video/{v.get('bvid')}",
                    "rcmd_reason": v.get('rcmd_reason', ''),
                }
                for v in videos
            ],
        })
    except Exception as e:
        output({"error": f"获取热门视频失败: {e}"})


async def cmd_all(args):
    """一次性获取视频的所有信息（视频信息、字幕、评论、弹幕）"""
    bvid = get_bvid(args)
    credential = get_credential()
    v = video.Video(bvid=bvid, credential=credential)
    page = 0
    comment_limit = getattr(args, 'comment_limit', 50) or 50

    result = {}

    # 1. 获取视频基本信息
    info = await v.get_info()
    stat = info.get('stat', {})

    tags = []
    try:
        tag_list = await v.get_tags()
        tags = [t.get('tag_name', '') for t in tag_list]
    except Exception:
        pass

    pages = info.get('pages', [])
    page_list = [{"index": p.get('page', i+1), "title": p.get('part', ''), "duration": p.get('duration', 0)} for i, p in enumerate(pages)]

    result["video"] = {
        "bvid": info.get('bvid'),
        "aid": info.get('aid'),
        "title": info.get('title'),
        "description": info.get('desc'),
        "duration": info.get('duration'),
        "cover": info.get('pic'),
        "publish_time": datetime.fromtimestamp(info.get('pubdate', 0)).isoformat(),
        "up": {
            "uid": info.get('owner', {}).get('mid'),
            "name": info.get('owner', {}).get('name'),
            "face": info.get('owner', {}).get('face'),
        },
        "stats": {
            "view": stat.get('view'),
            "like": stat.get('like'),
            "coin": stat.get('coin'),
            "favorite": stat.get('favorite'),
            "share": stat.get('share'),
            "danmaku": stat.get('danmaku'),
            "reply": stat.get('reply'),
        },
        "tags": tags,
        "pages": page_list,
    }

    # 2. 获取字幕（使用公共函数，直接通过 /x/player/wbi/v2 获取，不依赖 get_info）
    result["subtitle"] = await _fetch_subtitle(v, info, page=page)

    # 3. 获取评论（热门前N条）
    try:
        aid = info['aid']
        all_comments = []
        page_num = 1
        while len(all_comments) < comment_limit:
            try:
                data = await comment.get_comments(
                    oid=aid,
                    type_=CommentResourceType.VIDEO,
                    page_index=page_num,
                    order=OrderType.LIKE,
                    credential=credential,
                )
            except Exception:
                break
            replies = data.get('replies') or []
            if not replies:
                break
            for r in replies:
                if len(all_comments) >= comment_limit:
                    break
                c = {
                    "user": r.get('member', {}).get('uname'),
                    "content": r.get('content', {}).get('message'),
                    "like": r.get('like'),
                    "reply_count": r.get('rcount'),
                    "time": datetime.fromtimestamp(r.get('ctime', 0)).isoformat(),
                }
                sub_replies = r.get('replies') or []
                if sub_replies:
                    c['top_replies'] = [
                        {"user": sr.get('member', {}).get('uname'), "content": sr.get('content', {}).get('message'), "like": sr.get('like')}
                        for sr in sub_replies[:3]
                    ]
                all_comments.append(c)
            page_num += 1
        result["comments"] = {"comment_count": len(all_comments), "comments": all_comments}
    except Exception as e:
        result["comments"] = {"error": str(e)}

    # 4. 获取弹幕（protobuf 分段接口，自动遍历所有段）
    try:
        cid = pages[page]['cid'] if page < len(pages) else None
        dms = await v.get_danmakus(cid=cid)
        dm_list = sorted([
            {"time": round(dm.dm_time, 2), "text": dm.text}
            for dm in dms
        ], key=lambda x: x['time'])
        result["danmaku"] = {
            "danmaku_count": len(dm_list),
            "note": f"当前弹幕池数量（历史累计 {stat.get('danmaku', '未知')} 条）",
            "danmakus": dm_list,
        }
    except Exception as e:
        result["danmaku"] = {"error": str(e)}

    output(result)


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="B 站数据获取工具")
    parser.add_argument('--debug', action='store_true', help='显示调试日志')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # video
    p_video = subparsers.add_parser('video', help='获取视频信息')
    p_video.add_argument('--bvid', help='BV 号')
    p_video.add_argument('--url', help='视频 URL')

    # subtitle
    p_sub = subparsers.add_parser('subtitle', help='获取视频字幕')
    p_sub.add_argument('--bvid', help='BV 号')
    p_sub.add_argument('--url', help='视频 URL')
    p_sub.add_argument('--lang', help='字幕语言，如 zh-CN, en-US')
    p_sub.add_argument('--page', type=int, default=0, help='分 P 索引（从 0 开始）')

    # danmaku
    p_dm = subparsers.add_parser('danmaku', help='获取弹幕')
    p_dm.add_argument('--bvid', help='BV 号')
    p_dm.add_argument('--url', help='视频 URL')
    p_dm.add_argument('--page', type=int, default=0, help='分 P 索引')

    # comments
    p_cm = subparsers.add_parser('comments', help='获取评论')
    p_cm.add_argument('--bvid', help='BV 号')
    p_cm.add_argument('--url', help='视频 URL')
    p_cm.add_argument('--sort', choices=['hot', 'time'], default='hot', help='排序方式')
    p_cm.add_argument('--limit', type=int, default=20, help='获取数量')

    # search
    p_search = subparsers.add_parser('search', help='搜索B站')
    p_search.add_argument('--keyword', required=True, help='搜索关键词')
    p_search.add_argument('--sort', choices=['totalrank', 'click', 'pubdate', 'dm', 'stow'],
                          help='排序方式')
    p_search.add_argument('--type', default='video', help='搜索类型')
    p_search.add_argument('--limit', type=int, default=20, help='结果数量')

    # user
    p_user = subparsers.add_parser('user', help='获取用户信息')
    p_user.add_argument('--uid', type=int, help='用户 UID')
    p_user.add_argument('--url', help='用户主页 URL')
    p_user.add_argument('--videos', action='store_true', help='同时获取视频列表')
    p_user.add_argument('--limit', type=int, default=10, help='视频列表数量')

    # hot
    p_hot = subparsers.add_parser('hot', help='获取热门视频')
    p_hot.add_argument('--weekly', action='store_true', help='获取每周必看')
    p_hot.add_argument('--limit', type=int, default=20, help='获取数量')

    # all
    p_all = subparsers.add_parser('all', help='一次性获取视频所有信息')
    p_all.add_argument('--bvid', help='BV 号')
    p_all.add_argument('--url', help='视频 URL')
    p_all.add_argument('--comment-limit', type=int, default=50, dest='comment_limit', help='评论获取数量')

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    cmd_map = {
        'video': cmd_video,
        'subtitle': cmd_subtitle,
        'danmaku': cmd_danmaku,
        'comments': cmd_comments,
        'search': cmd_search,
        'user': cmd_user,
        'hot': cmd_hot,
        'all': cmd_all,
    }

    try:
        asyncio.run(cmd_map[args.command](args))
    except Exception as e:
        output({"error": str(e), "type": type(e).__name__})
        sys.exit(1)


if __name__ == '__main__':
    main()
