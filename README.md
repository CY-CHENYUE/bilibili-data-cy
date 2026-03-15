# 📺 bilibili-data — B 站数据获取技能

通过 [bilibili-api-python](https://github.com/Nemo2011/bilibili-api) 获取 B 站各类公开数据。杀手级能力：**字幕获取**让 AI 能"读"视频内容。

## 功能特性

- **视频信息** — 标题、描述、播放量、点赞、投币、收藏、UP 主、标签、分 P 列表
- **字幕获取** — 下载视频字幕（带时间戳），让 AI 理解和总结视频内容
- **弹幕抓取** — 获取实时弹幕数据，分析观众反应
- **评论获取** — 热门/最新评论，含子回复和互动数据
- **视频搜索** — 按关键词搜索，支持多种排序（播放量/最新/弹幕/收藏）
- **用户信息** — UP 主资料、粉丝数据、视频列表
- **热门排行** — 全站热门、每周必看

## 安装

```bash
pip install -r requirements.txt
```

依赖：`bilibili-api-python`、`aiohttp`

## 快速开始

```bash
# 获取视频信息
python3 scripts/bili.py video --bvid BV1HuwxzFEcZ

# 搜索视频
python3 scripts/bili.py search --keyword "Python 教程" --sort click --limit 5

# 获取弹幕
python3 scripts/bili.py danmaku --bvid BV1HuwxzFEcZ

# 获取评论
python3 scripts/bili.py comments --bvid BV1HuwxzFEcZ --sort hot --limit 20

# 获取热门视频
python3 scripts/bili.py hot --limit 10

# 获取用户信息
python3 scripts/bili.py user --uid 402808950 --videos

# 获取字幕（需要 SESSDATA）
python3 scripts/bili.py subtitle --bvid BV1HuwxzFEcZ
```

也支持 `--url` 参数直接传入 B 站链接：

```bash
python3 scripts/bili.py video --url "https://www.bilibili.com/video/BV1HuwxzFEcZ"
```

## 认证配置（可选）

字幕下载需要登录态，设置环境变量即可：

```bash
export BILI_SESSDATA="你的SESSDATA"
```

**获取方式**：浏览器登录 bilibili.com → F12 → Application → Cookies → 复制 `SESSDATA` 值。

未配置时大部分功能正常可用，字幕命令会返回可用语言列表但无法下载内容。

## 命令速查

| 命令 | 说明 | 需要登录 |
|------|------|----------|
| `video` | 视频元数据（标题、播放量、UP主等） | 否 |
| `subtitle` | 字幕文本（带时间戳） | 是 |
| `danmaku` | 弹幕列表（按时间排序） | 否 |
| `comments` | 评论（支持 `--sort hot/time`） | 否 |
| `search` | 搜索视频（支持 `--sort click/pubdate/dm/stow`） | 否 |
| `user` | 用户资料和视频列表（`--videos`） | 否 |
| `hot` | 热门视频 / 每周必看（`--weekly`） | 否 |

所有命令输出 JSON 格式，加 `--debug` 查看详细日志。

## 项目结构

```
bilibili-data/
├── SKILL.md           # Claude Code Skill 描述文件
├── README.md          # 本文件
├── requirements.txt   # Python 依赖
├── evals/
│   └── evals.json     # 触发测试用例
└── scripts/
    └── bili.py         # 主脚本（7 个子命令）
```

## 作为 Claude Code Skill 使用

将本目录放入 Claude Code 的 skills 目录后，对话中提到 B 站、bilibili、BV 号或分享 B 站链接时会自动触发。

```
"帮我看看这个B站视频讲了什么 https://www.bilibili.com/video/BV1HuwxzFEcZ"
"搜一下B站上Python教程的视频"
"B站最近什么比较火"
```
