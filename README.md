# 游戏测试与 Bug 分析工作台

CPS3740 数据库课程项目。此版本提供 Flask、Jinja、原生 CSS/JavaScript 的四页工作台：Dashboard、Games、Bug Tracker 和 Feedback。当前演示数据保存到本地 JSON 文件；应用没有连接 MySQL。`sql/schema.sql` 保持原样，定义了后续 MySQL 适配器对应的七张表。

## 启动

需要 Python 3.10 或更高版本。Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app app:create_app run
```

工作区已包含可直接使用的 `.venv`，无需依赖系统 `py` 启动器。若在其他电脑从零安装，请使用已安装的 Python 3.10+ 执行 `python -m venv .venv` 后再运行上面的命令。打开 <http://127.0.0.1:5000/>。首次启动会将内置演示样例写入 `instance/playtest.json`；后续启动会继续使用该文件，不会覆盖现有记录。`instance/` 已加入 `.gitignore`。可复制 `.env.example` 为 `.env` 配置本地运行参数。

如需无业务样例的工作区，可在首次启动前设置 `SEED_DATA=false`。此时游戏、版本、场次、Bug 和反馈列表为空，但仍保留四个演示身份，便于切换到 Developer/Admin 后创建数据。数据文件损坏时 API 会返回明确的存储错误，并保留损坏文件；请先备份，再手动修复后重启。

## 演示身份与权限

右上角身份选择器用于在样例用户之间切换，选择值保存在 Flask session。此功能仅供课堂演示，**不是正式身份认证**：没有密码、登录安全或 CSRF 防护，也不应部署到公网。

样例账号：

| Name | Role | Email |
| --- | --- | --- |
| Avery Chen | Tester | avery@example.com |
| Morgan Lee | Tester | morgan@example.com |
| Riley Park | Developer | riley@example.com |
| Jordan Kim | Admin | jordan@example.com |

页面顶部的 **Register** 可创建 Tester 并立即切换到新身份。Tester 只能查看或修改自己的测试场次、场次反馈及自己提交的报告；Developer 和 Admin 可管理游戏、版本与 Bug。Admin 还可通过 API 删除未被引用的记录。所有权限在服务层再次检查，不能靠改界面绕过。

## 演示流程

1. Dashboard 展示 Skyward Isles 的 `0.9.0` 和 `1.0.0` 比较、未解决 Bug 和优先级列表。初始数据中一条视觉 Bug 在两个版本分别建有主记录，用于对比版本变化。
2. 切换到 Tester Avery，在 Games 中登记 `1.0.0` 测试场次；或者使用已有场次。
3. 在 Bug Tracker 提交 `Camera clips through the lighthouse wall`、分类 `Visual` 的报告。系统会提示同版本候选项；Tester 的提交会保留为独立报告，等待开发者确认。
4. 切换到 Developer Riley，可调整 Bug 严重度、影响、状态，将出现报告关联到同版本的已有 Bug，或在 Bug Tracker 使用 **Merge bugs** 合并重复主记录。合并会将所有出现记录迁移到目标，并保留目标的标题、严重度、影响和状态。
5. 切回 Tester 为场次提交 1–5 分反馈。每个场次最多一条反馈；Dashboard 重新汇总平均评分。

样例数据包括一个游戏、两个版本、四名不同角色用户、四个场次、多条重复出现记录和不同评分/状态。新工作区的数据与 `app/storage.py` 中的样例结构一致。

## 页面和 API

四个页面均使用英文界面。页面请求的 API 响应格式统一：

```json
{"ok": true, "data": {}}
```

错误响应包含 `ok: false`、`error.message` 和 `error.status`，并使用相应 HTTP 状态码。主要端点：

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/identity` | 当前演示身份与可选身份 |
| POST | `/api/identity` | 切换演示身份，JSON: `{"user_id": 1}` |
| POST | `/api/register` | 注册 Tester，字段 `name`, `email` |
| GET | `/api/dashboard` | 版本比较、未解决 Bug 和优先级 |
| GET/POST | `/api/users`, `/api/games`, `/api/game_versions`, `/api/playtest_sessions`, `/api/bug_reports`, `/api/bug_occurrences`, `/api/feedback` | 实体列表与创建 |
| GET/PUT/DELETE | `/api/<entity>/<id>` | 实体明细、更新和受限删除 |
| POST | `/api/candidates` | 查找同版本、同分类、标题关键词相交的候选 Bug |
| POST | `/api/merge` | 合并两个同版本 Bug，JSON: `source_bug_id`, `target_bug_id` |
| POST | `/api/associate` | Developer/Admin 确认报告关联，JSON: `occurrence_id`, `bug_id` |

优先级计算为 `0.5 × severity + 0.3 × min(report_count, 5) + 0.2 × impact`。未解决定义为 `Open` 或 `In Progress`。版本统计从 Bug 主记录计算 Bug 数与未解决数，从出现记录计算报告次数；平均评分按场次反馈计算，没有评分时返回 `null`，页面显示 “No ratings”。

## 七表字段映射

JSON 中的数组和字段对应 `sql/schema.sql`：

| Table / JSON collection | Fields |
| --- | --- |
| `users` | `user_id`, `name`, `email`, `role` |
| `games` | `game_id`, `title`, `genre`, `created_at` |
| `game_versions` | `version_id`, `game_id`, `version_name`, `release_date` |
| `playtest_sessions` | `session_id`, `user_id`, `version_id`, `tested_at` |
| `bug_reports` | `bug_id`, `version_id`, `title`, `category`, `severity`, `impact`, `status` |
| `bug_occurrences` | `occurrence_id`, `bug_id`, `session_id`, `version_id`, `notes`, `reported_at` |
| `feedback` | `feedback_id`, `session_id`, `rating`, `comments` |

存储适配器接口位于 `app/storage.py`。服务层依赖 `read()` 和 `transact(operation)`：前者返回完整七表快照，后者在隔离副本上执行业务事务并于成功后提交。未来的 MySQL 适配器应实现相同接口，并在 `create_app()` 中替换 `JsonStore`；应保留服务层的外键、唯一性和权限规则，以数据库事务加约束落实同样保证。`sql/schema.sql` 未修改。

JSON 适配器使用单进程锁、同目录临时文件和原子替换，能避免单进程内部分写入；它不支持多进程并发写入。业务校验失败不会写文件。所有 API 路由只调用服务层，业务服务通过存储适配器读写，不直接操作 JSON 文件。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Flask 测试客户端覆盖权限、校验错误、持久化、事务失败、Bug 合并、统计与损坏文件行为。
