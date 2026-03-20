# BI 双环境页面数据比对工具

用于比较生产/测试两套 BI 环境中同一页面（或页面映射）下卡片数据差异。

## 目录定位

当前项目已独立放在仓库子目录：

- 项目根目录：`/Users/guandata/Desktop/cursor_project/page_compare/bi-page-compare`
- Web 入口：`/Users/guandata/Desktop/cursor_project/page_compare/bi-page-compare/web_app.py`
- CLI 入口：`/Users/guandata/Desktop/cursor_project/page_compare/bi-page-compare/main.py`

## 功能

- 登录两套环境，获取 token
- 按页面 ID 拉取卡片列表
- 按卡片 `id` 或 `name` 自动配对（支持手工映射）
- 拉取卡片数据并深度比对 JSON
- 输出 JSON 和 HTML 报告

### sign-in 调用次数

- 默认：每个环境 1 次（prod 1 次 + test 1 次），与页面数/卡片数无关。
- 若两边是同一套地址和同一账号（base_url/domain/login_id/password 全相同），程序会复用同一个 token，单次任务只调用 1 次 sign-in。

## 接口适配

当前已按你提供的 3 个接口实现：

- `POST /public-api/sign-in`
- `GET /public-api/page/{pgId}`
- `POST /public-api/card/{cardId}/data`

## 使用

1) 复制配置模板

```bash
cp config.example.toml config.toml
```

2) 修改 `config.toml`

- 填写 `envs.prod` / `envs.test` 的域名、账号、密码
- 若页面接口要求应用级 token，补充 `envs.prod.page_token` / `envs.test.page_token`
- 配置 `page_pairs` 页面映射
- 可按需设置 `request_filters`、`ignore_paths`、`match_cards_by`

> 注意：程序会自动把密码做 Base64 编码后调用登录接口，配置里请填写原始密码。

3) 执行

```bash
python3 main.py --config config.toml --out-dir output
```

4) 查看结果

- `output/compare_report.json`
- `output/compare_report.html`

## Web 页面（支持多页面对、开始/终止、进度刷新、结果查看）

启动：

```bash
python3 web_app.py --host 127.0.0.1 --port 8787
```

打开浏览器访问：

- `http://127.0.0.1:8787`

功能：

- 输入 prod/test 的 URL、domain、账号密码、应用 token
- 基础信息字段为必填，缺失时会高亮并提示
- 页面对支持动态添加多组（同一次任务可批量比较）
- 支持把当前录入信息保存为模板（服务端持久化，跨设备可读取）
- 点击“开始比较”后后台异步运行任务
- 点击“终止比较”可请求停止任务（会在当前请求结束后停止）
- 点击“刷新进度”查看最新状态，运行中每 2 秒自动刷新
- 完成后点击“查看比较结果”打开 HTML 报告
- 历史任务结果持久化，可回看不同时间的比对结果
- 历史结果列直接给出任务结论：一致（绿）、不一致（红）、异常（橙）
- 支持创建定时计划（按模板周期执行）并可立即触发一次
- 定时计划输入项非必填；若完全不填则不保存计划；若部分缺失则使用默认值补全
- Web 页面不再暴露比对参数，统一按当前固定配置执行

持久化数据位置：

- `app_data/bi_compare.db`：模板、任务元数据、定时计划
- `web_output/<task_id>/compare_report.{json,html}`：每次任务结果文件

## 一键部署脚本（服务器）

```bash
sudo DOMAIN=bi.example.com APP_DIR=/opt/bi-compare APP_PORT=8787 bash deploy_one_click.sh
```

脚本会自动完成：

- 安装系统依赖（nginx、python3、venv、rsync）
- 同步代码到 `APP_DIR`（保留 `app_data` 与 `web_output` 历史）
- 创建 venv 并安装依赖
- 生成并启动 systemd 服务
- 配置并重载 nginx 反向代理

如果你的 80 端口已有其他服务，请使用“仅端口部署”脚本（不修改 nginx）：

```bash
sudo APP_DIR=/opt/bi-compare APP_PORT=8787 SERVICE_NAME=bi-compare bash deploy_port_only.sh
```

该脚本支持 `apt-get` / `dnf` / `yum` 三类系统包管理器。

访问方式：

- `http://<服务器IP>:8787`

## 配置说明（核心）

- `settings.match_cards_by`: `id` / `name`
- `settings.compare_scope`: `chartMain` / `full_response`
- `settings.ignore_paths`: 忽略路径（支持通配符）
- `settings.sort_arrays_before_compare`: 是否忽略数组顺序
- `settings.numeric_tolerance`: 数值容差

## 常见建议

- 如果两边卡片 ID 不一致，优先用 `match_cards_by = "name"`
- 如果卡片名称重复，使用 `page_pairs.card_mappings` 显式映射
- 如果只关注图表数据，不关注元数据，使用 `compare_scope = "chartMain"`

## 当前精确比对规则（已内置）

- `response.chartMain.data`：忽略顺序，做全量比较
- `response.chartMain.column.values`：仅比较 `title` 字段（忽略顺序和其他属性）
- `response.chartMain.row.meta`：仅比较 `title` 字段（忽略顺序和其他属性）
- `response.chartMain.row.values`：忽略顺序，做全量比较
