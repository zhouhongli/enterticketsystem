# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

企业售后工单系统 MVP——单体 Web 应用，已完成 M0-M5 阶段开发。后端 FastAPI + JSON 文件持久化，前端原生 HTML/CSS/JS 多页面应用。

## 开发命令

```bash
# 安装依赖
cd backend && pip install -e ".[dev]"

# 启动开发服务器（自动重载）
cd backend && uvicorn app.main:app --reload

# 运行全部测试
cd backend && pytest

# 运行单个测试文件 / 指定测试函数
cd backend && pytest tests/api/test_auth_routes.py -v
cd backend && pytest tests/api/test_auth_routes.py -k test_login -v
```

## 技术栈

- **后端**: Python FastAPI（单进程），**Python >=3.10**，**Pydantic v2**
- **前端**: 原生 HTML/CSS/JavaScript（无框架、无构建链，**ES Modules**）
- **持久化**: `backend/data/store.json` 单文件，schema_version=1
- **认证**: 服务端会话，`HttpOnly`/`SameSite=Lax` Cookie（`ticket_session`），8 小时 TTL
- **密码**: Argon2id 哈希
- **标识**: UUID v4；时间戳: UTC ISO 8601（`Z` 后缀）

## 架构概览

```
浏览器（原生 HTML/JS 静态页面）
        |
FastAPI REST API (/api/v1) + 静态文件服务
        ├── /          → 重定向到登录页
        ├── /pages/    → 静态 HTML 页面
        ├── /assets/   → CSS/JS 资源
        └── /api/v1/*  → REST 接口
              ├── /auth         注册、登录、退出、会话
              ├── /categories   问题分类管理
              ├── /admin        管理员功能（账号管理）
              ├── /customer     客户工单操作
              └── /internal     内部工单处理
```

### 分层架构

```
API 路由 (api/routes/)
    ↓  FastAPI Depends 注入
应用服务 (services/)        ← 用例编排，调用仓储，转换响应
    ↓
仓储 (repositories/)         ← JsonRepository，面向业务的操作接口
    ↓
存储 (storage/)              ← JsonFileStore，原子写入 + 线程锁
```

业务服务只面向 `JsonRepository`，不直接操作 `JsonFileStore`。

### JSON Store Schema

```json
{
  "schema_version": 1,
  "meta": { "created_at": "...", "updated_at": "..." },
  "users": [],       // 用户（customer/agent/admin）
  "categories": [],  // 问题分类
  "tickets": [],     // 工单
  "messages": [],    // 工单留言
  "audit_logs": [],  // 审计日志
  "sessions": []     // 会话（token_hash 存储）
}
```

`JsonFileStore` 使用 `threading.RLock` + 临时文件 `os.replace()` 实现原子写入。所有写操作通过 `store.transaction(mutator)` 执行——mutator 是接收 `data` dict 并返回结果的 callable，在持有锁时同步执行。

## API 错误响应格式

所有错误统一返回：

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "中文错误描述",
    "field_errors": { "field_name": "错误原因" }
  }
}
```

`field_errors` 仅 422 响应中出现。前端通过 `api-client.js` 的 `codeMessages` 映射处理展示。

### 错误码

| 错误码 | HTTP | 说明 |
|---|---|---|
| `AUTHENTICATION_REQUIRED` | 401 | 未登录或会话失效 |
| `LOGIN_FAILED` | 401 | 账号/密码错误或账号被禁用 |
| `FORBIDDEN` | 403 | 角色权限不足 |
| `RESOURCE_NOT_FOUND` | 404 | 记录不存在 |
| `VALIDATION_ERROR` | 422 | 字段校验失败 |
| `CONFLICT` | 409 | 数据冲突（用户名/邮箱重复） |
| `STORAGE_ERROR` | 500 | 持久化失败 |

## 仓储方法返回值约定

- 查询：`dict | None`（找不到返回 None）
- 创建/更新：`dict | None`
- 带业务错误的写操作：`dict | str`，字符串为错误码（`"not_found"`, `"closed"`, `"forbidden"`, `"invalid_assignee"`, `"invalid_transition"`），服务层将其翻译为 API 错误

## 工单状态机（线性固定）

```
unassigned → processing → resolved → closed
```

由 `TicketStatus.next_status()` 定义合法转换，仓储层执行校验，跳过状态返回 `"invalid_transition"`。

## 认证流程

1. 登录成功 → 创建会话 → 返回 raw_token（一次性）→ 写入 HttpOnly Cookie
2. 后续请求 → 读 Cookie → SHA256 哈希 → 查找会话 → 验证未过期/未撤销 → 返回用户
3. 用户被禁用 → 自动撤销该用户所有会话

## 权限验证

所有受保护路由通过 FastAPI `Depends` 注入：
- `get_current_user` — 需要登录（任意角色）
- `require_admin` — 仅 admin
- `require_customer` — 仅 customer
- `require_internal_user` — agent 或 admin

前端按钮隐藏不构成安全措施。

## 输入校验规则

- **用户名**: 3-50 字符，仅限中文/英文/数字/下划线/连字符（`^[\w一-鿿-]+$`）
- **邮箱**: 3-254 字符，含 `@`，不区分大小写（存储前转小写）
- **密码**: 8-128 字符（无复杂度要求，注册时需二次确认）
- 登录支持用户名或邮箱（通过是否含 `@` 判断）

## 前端架构

**页面组织**: `frontend/pages/` 按角色分目录（`customer/`, `internal/`），每个 HTML 页面内联 `<script type="module">` 加载对应 JS。

**会话检查**: 每个页面通过 `session-ui.js` 的 `export const sessionReady` promise 检查认证——自动调 `/api/v1/auth/me`，401 时跳转登录页。页面 JS 应 `await sessionReady` 再继续业务逻辑。

**角色导航**: `session-ui.js` 根据用户 role 渲染不同的导航链接和身份标识。页面访问权限在前端也会被 `isAllowedOnCurrentPage()` 拦截并跳转。

**JS 模块职责**:
- `api-client.js` — 统一 `apiRequest()`，`credentials: "include"`，错误构建
- `session-ui.js` — 会话验证、身份展示、导航渲染、退出登录
- `auth-pages.js` — 登录/注册表单处理
- `customer-tickets.js` — 客户工单 CRUD
- `internal-tickets.js` — 内部工单列表/详情/分配/状态流转
- `admin-management.js` — 分类、客服账号、客户账号管理
- `form-utils.js` — 表单反馈工具
- `ticket-ui.js` — 工单状态标签等通用 UI

## 测试模式

- 使用 `httpx.AsyncClient` + `httpx.ASGITransport(app)` 做 API 集成测试
- 异步测试通过 `anyio.run(async_fn)` 在同步 pytest 函数中执行
- 使用 `app.dependency_overrides[get_settings] = lambda: test_settings` 注入测试配置
- 数据文件通过 `pytest tmp_path` fixture 指向临时目录
- 每个测试独立创建 app、repo、client，不共享状态

```python
# 典型测试模式
def test_something(tmp_path) -> None:
    settings = make_settings(tmp_path)  # 指向临时数据文件
    repo = make_repo(settings)
    app = make_app(settings)            # 含 dependency_overrides

    async def run() -> None:
        async with await make_client(app) as client:
            response = await client.post("/api/v1/...", json={...})
        assert response.status_code == 201

    anyio.run(run)
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_NAME` | `企业售后工单系统` | 应用名称 |
| `APP_ENV` | `local` | 运行环境 |
| `TICKET_DATA_FILE` | `backend/data/store.json` | 数据文件路径 |
| `SESSION_COOKIE_NAME` | `ticket_session` | 会话 Cookie 名 |
| `SESSION_COOKIE_SECURE` | `false` | 是否启用 Secure 标记 |
| `SESSION_TTL_HOURS` | `8` | 会话有效期（小时） |
| `INITIAL_ADMIN_USERNAME` | `""` | 初始管理员用户名 |
| `INITIAL_ADMIN_EMAIL` | `""` | 初始管理员邮箱 |
| `INITIAL_ADMIN_PASSWORD` | `""` | 初始管理员密码 |

首次启动时，若配置了初始管理员信息且系统中尚无管理员，`bootstrap.py` 会自动创建。

## 不在 MVP 范围内的功能

附件、外部通知、SLA、统计报表、高级搜索、导出、客户确认关闭、取消、退回、重开、自动关闭、密码找回、多因素认证、验证码、关系型数据库迁移、多实例并发写入。
