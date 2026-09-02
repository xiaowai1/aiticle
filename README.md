# Aticle：A 股上市公司介绍 → 微信公众号草稿箱

每次手动执行：拉**当日** A 股列表 → 找未写过的公司 → 拉公开数据 → DeepSeek 写稿 → 进草稿箱。

## 配置

```bash
cd /Users/a58/Desktop/aiticle
source .venv/bin/activate
cp .env.example .env   # 首次
```

`.env` 必填：`DEEPSEEK_API_KEY`、`WECHAT_APP_ID`、`WECHAT_APP_SECRET`；可选 `DAILY_COMPANY_COUNT=1`。

公众平台 **基本配置** 里把本机 **公网 IP** 加入白名单。

## 每次发文前

```bash
python -m aiticle check-wechat   # 先诊断出口 IP 与白名单
python -m aiticle run
```

每次 `run` 会处理 **1 家公司**（可在 `.env` 里改 `DAILY_COMPANY_COUNT`）。

## 进度

```bash
python -m aiticle status
```

## 其他命令

```bash
python -m aiticle generate --code 600519   # 指定一家（会记入已写）
python -m aiticle publish --code 600519    # 用本地文稿重发草稿
python -m aiticle fetch --code 600519      # 调试拉数
```

## 数据文件

| 文件 | 作用 |
|---|---|
| `data/written_registry.json` | 已写公司 + 失败记录（上云请备份此文件） |
| `data/daily_runs.jsonl` | 每次运行日志 |
| `output/<代码>/` | 本地文稿备份 |

新股上市：出现在当日列表且不在已写 → 自动写。退市：不在当日列表 → 不会被选。

## 你每天只做

微信公众平台 → **草稿箱** → 检查 1 篇 → 发布。
