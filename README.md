# 游戏测试与 Bug 分析管理系统

CPS3740 数据库课程项目。项目计划使用 Flask 和 MySQL 管理游戏版本、测试、Bug 报告和玩家反馈，并比较版本质量。当前仓库是初始化骨架，业务页面、数据库连接、CRUD、重复报告关联和统计功能尚未实现。

## 环境与启动

需要 Python 3.10+ 和 MySQL 8.0.16+。在项目目录执行：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
flask --app app:create_app run
```

访问 http://127.0.0.1:5000/。`.env` 中的数据库配置为后续数据库功能预留；请按本机环境修改，不要提交密码。

在 MySQL 中创建空数据库和有适当权限的用户，然后在该数据库中执行 `sql/schema.sql`。例如使用命令行 `mysql -u playtest -p game_playtest < sql/schema.sql`（PowerShell 用户可使用 `cmd /c` 执行该重定向，或使用 MySQL Workbench）。脚本用于空数据库，不会覆盖已有表。

## 数据模型

七张表分别为 users、games、game_versions、playtest_sessions、bug_reports、bug_occurrences 和 feedback。复合外键确保 Bug 与测试场次属于同一版本；每个场次最多一条反馈。`sql/schema.sql` 是数据库结构的初稿，需在团队审批后完善。

## 后续里程碑

1. 确认方案，绘制 ERD，检查数据库设计并加入样例数据。
2. 实现用户、游戏和版本、测试、Bug、反馈的基本操作与数据校验。
3. 实现人工确认的重复 Bug 关联、基于严重度/频次/影响的优先级，以及跨版本统计。
4. 使用两个版本的数据进行端到端测试和演示，完善运行与提交说明。

优先级计划采用 `0.5 × Severity + 0.3 × FrequencyScore + 0.2 × Impact`，各项均为 1–5 分；频次映射规则尚待团队确定。版本对比反映样本中的变化，不代表因果关系。计划来源为团队项目方案，最终课程交付要求以教师说明为准。
