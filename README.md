# Aticle：多领域内容 → 微信公众号草稿箱

支持多个**内容领域**，各自推送到**不同公众号草稿箱**。当前内置两个领域：

| 领域 ID | 说明 | 状态 |
|---------|------|------|
| `stock` | A 股上市公司介绍 | 已实现 |
| `reserved` | 第二个公众号槽位 | 待配置内容 |

## 配置

```bash
cd /Users/a58/Desktop/aiticle
source .venv/bin/activate
cp .env.example .env   # 首次
```

`.env` 必填：`DEEPSEEK_API_KEY`；`stock` 领域还需 `WECHAT_APP_ID`、`WECHAT_APP_SECRET`。  
第二个公众号在 `VERTICAL_RESERVED_WECHAT_APP_ID` / `VERTICAL_RESERVED_WECHAT_APP_SECRET` 中配置。

公众平台 **基本配置** 里把本机 **公网 IP** 加入白名单（每个公众号各自配置）。

## 常用命令

```bash
python -m aiticle verticals              # 列出领域
python -m aiticle check-wechat           # 测 stock 公众号连通（默认领域）
python -m aiticle check-wechat -v reserved  # 测第二个公众号
python -m aiticle run                    # stock 领域：跑 1 家公司
python -m aiticle run -v stock --count 2
python -m aiticle status --all           # 全部领域进度
```

## 其他命令

```bash
python -m aiticle generate --code 600519           # 指定一家 A 股
python -m aiticle publish --code 600519            # 用本地文稿重发草稿
python -m aiticle fetch --code 600519              # 调试拉数
python -m aiticle reset-registry                   # 清空 stock 已写记录
```

`reserved` 领域内容生成尚未实现，可先配置微信凭证并用 `check-wechat -v reserved` 验证。

## 数据文件

| 路径 | 作用 |
|------|------|
| `data/stock/written_registry.json` | stock 已写公司（兼容旧 `data/written_registry.json`） |
| `data/stock/daily_runs.jsonl` | stock 运行日志 |
| `output/stock/<代码>/` | stock 本地文稿 |
| `data/reserved/` | 预留领域数据（待实现） |
| `output/reserved/` | 预留领域输出（待实现） |

旧版 `output/<代码>/` 仍可用于 `publish --code`。

## 你每天只做

对应公众号 → **草稿箱** → 检查文章 → 发布。
