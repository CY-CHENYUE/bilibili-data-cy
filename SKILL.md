---
name: bilibili-data
description: >-
  Use when the user mentions B站, bilibili, BV号, or shares a bilibili.com link.
  Covers any request to fetch, read, summarize, or analyze Bilibili content:
  video info and metadata, subtitles (enables AI to "read" videos), danmaku/弹幕,
  comments/评论, search, UP主/user profiles, and trending/hot rankings.
  Trigger examples: "看看这个B站视频", "总结这个视频讲了什么", "B站搜一下",
  "获取弹幕", "这个UP主", "B站热门", or any bilibili.com/video/BVxxx URL.
  This skill is read-only — it fetches data but does NOT log in, like, coin, or perform account actions.
allowed-tools: Bash, Read
metadata: {"clawdbot":{"emoji":"📺","requires":{"bins":["python3"],"packages":["bilibili-api-python","aiohttp"]}}}
---

# B 站数据获取 (bilibili-data)

通过 bilibili-api-python 获取 B 站各类公开数据，杀手级能力：字幕获取让 AI 能"读"视频。

## 首次使用

如依赖未安装，先执行：

```bash
pip install -r {baseDir}/requirements.txt
```

## 认证配置（可选）

部分功能（字幕下载、AI 总结）需要登录态。设置环境变量：

```bash
export BILI_SESSDATA="你的SESSDATA"
```

获取方式：浏览器登录 bilibili.com → F12 → Application → Cookies → 复制 SESSDATA 值。

未配置时，字幕命令会返回可用字幕列表但无法下载内容，其他大部分功能正常可用。

## 核心规则（必须遵守）

1. **必须使用用户给的 URL/BV号**：将用户消息中的完整 URL 原样传给 `--url` 参数，绝对不要使用本文档示例中的占位符
2. **默认使用 `all` 命令**：收到视频链接时直接一次性获取所有信息，不要问用户
3. **不要分步获取**：不要先获取视频信息再问是否需要字幕/弹幕，直接全部获取

## 命令用法

所有命令通过 `python3 {baseDir}/scripts/bili.py` 调用，输出均为 JSON 格式。

### 一次性获取（默认，收到视频链接时必须使用）

```bash
python3 {baseDir}/scripts/bili.py all --url "<用户提供的完整URL>"
```

返回：视频元信息、字幕全文、热门评论（含子评论）、弹幕列表，全部合并在一个 JSON 中。

### 单项命令（仅在用户明确只需要某一类数据时使用）

```bash
# 视频信息
python3 {baseDir}/scripts/bili.py video --url "<URL>"

# 字幕
python3 {baseDir}/scripts/bili.py subtitle --url "<URL>"
python3 {baseDir}/scripts/bili.py subtitle --url "<URL>" --lang zh-CN

# 弹幕
python3 {baseDir}/scripts/bili.py danmaku --url "<URL>"

# 评论
python3 {baseDir}/scripts/bili.py comments --url "<URL>" --sort hot --limit 30

# 搜索
python3 {baseDir}/scripts/bili.py search --keyword "搜索关键词" --limit 20

# 用户信息
python3 {baseDir}/scripts/bili.py user --uid <UID> --videos --limit 10

# 热门视频
python3 {baseDir}/scripts/bili.py hot --limit 20
python3 {baseDir}/scripts/bili.py hot --weekly
```

## URL 解析

所有支持 `--url` 参数的命令会自动解析以下格式：
- `https://www.bilibili.com/video/BVxxxxxxxxxx`（标准链接，可带参数）
- `https://b23.tv/xxxxx`（短链接）
- `https://space.bilibili.com/12345`（用户主页）
- 直接传入 `BVxxxxxxxxxx` 也会被识别

## 注意事项

- 所有输出均为 JSON 格式，便于程序化处理
- 大部分功能无需登录即可使用
- 字幕下载和 AI 总结需要配置 SESSDATA
- 搜索结果默认返回 20 条
- 加 `--debug` 参数可查看详细日志
