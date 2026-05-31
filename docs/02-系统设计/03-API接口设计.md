# 企业售后工单系统 API 接口设计

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.0（已确认版） |
| 适用版本 | 最小可行产品（MVP） |
| 文档性质 | 系统设计阶段接口方案 |
| 编制依据 | 《企业售后工单系统 软件需求规格说明书（SRS）v1.0》、《企业售后工单系统 页面与交互说明 v1.0》、《企业售后工单系统 技术设计说明书 v1.0》、《企业售后工单系统 数据模型设计 v1.0》 |
| 当前状态 | 已经用户确认，作为前后端实现、接口测试与实施计划编制的接口基线 |
| 编制日期 | 2026-05-26 |

## 1. 文档目的

本文档定义最小可行产品（MVP）的 HTTP API 边界，包括版本化路由、认证 Cookie、通用请求响应格式、错误模型、接口权限、请求和响应字段、状态码以及页面与接口的调用对应关系。

本文档仅覆盖已确认 MVP 业务范围，不提供统计、附件、外部通知、高级搜索、批量操作、密码找回或数据库迁移相关接口。文档确认后，应作为后端路由实现、前端请求封装、接口测试和 MVP 实施计划的接口基线。

## 2. 接口设计原则

| 编号 | 原则 | 说明 |
| --- | --- | --- |
| API-P01 | 版本化路径 | 业务接口统一使用 `/api/v1` 前缀，便于后续演进。 |
| API-P02 | 同源会话认证 | 浏览器依赖后端设置的 `HttpOnly` 会话 Cookie，不由前端保存令牌。 |
| API-P03 | 后端强授权 | 每个受保护接口均校验登录身份、角色、资源归属及工单状态。 |
| API-P04 | 数据最小返回 | 响应仅返回页面需要的数据，不返回密码哈希、会话摘要等敏感字段。 |
| API-P05 | 错误结构统一 | 业务失败以统一错误体返回，便于原生 JavaScript 页面处理。 |
| API-P06 | 流程动作显式 | 留言、分配和状态推进为独立接口，不产生隐式业务变化。 |
| API-P07 | MVP 简洁 | 列表接口仅支持已确认的排序与状态筛选，不预留未实现的高级查询参数。 |

## 3. 通用约定

### 3.1 基础路径

| 项目 | 值 |
| --- | --- |
| API 基础前缀 | `/api/v1` |
| 静态页面路径 | 不属于本文业务 API，由 `FastAPI` 静态资源服务提供 |
| 请求数据格式 | `application/json; charset=utf-8` |
| 响应数据格式 | `application/json; charset=utf-8` |

### 3.2 时间、标识符与枚举

| 数据类型 | 接口表示 |
| --- | --- |
| 实体标识符 | UUID v4 字符串 |
| 时间字段 | UTC ISO 8601 字符串，例如 `2026-05-26T10:20:30Z` |
| 用户角色 | `customer`、`agent`、`admin` |
| 用户状态 | `active`、`disabled` |
| 分类状态 | `active`、`inactive` |
| 工单状态 | `unassigned`、`processing`、`resolved`、`closed` |

前端负责将枚举值和 UTC 时间转换为已确认的中文展示文本与本地时间表示。

### 3.3 成功响应

单资源操作成功时直接返回资源或操作结果对象；列表操作统一返回 `items` 数组。

```json
{
  "items": []
}
```

对于需表达操作结果但无新增资源的动作，例如退出，可返回：

```json
{
  "success": true
}
```

### 3.4 错误响应

所有预期业务错误使用以下结构：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "输入内容不符合要求。",
    "field_errors": {
      "title": "标题长度必须为 1 至 100 个字符。"
    }
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `error.code` | string | 是 | 稳定的错误代码，供前端按场景处理。 |
| `error.message` | string | 是 | 可向用户展示的中文错误说明。 |
| `error.field_errors` | object/null | 否 | 表单字段错误映射，仅校验失败时返回。 |

### 3.5 通用错误代码

| 错误代码 | HTTP 状态码 | 使用场景 |
| --- | --- | --- |
| `VALIDATION_ERROR` | `422` | 请求字段缺失、格式或长度不符合要求。 |
| `AUTHENTICATION_REQUIRED` | `401` | 未登录、会话已过期或会话已撤销。 |
| `LOGIN_FAILED` | `401` | 登录失败，统一覆盖账号不存在、密码错误或账号不可用。 |
| `FORBIDDEN` | `403` | 已登录但角色或操作权限不足。 |
| `RESOURCE_NOT_FOUND` | `404` | 资源不存在，或为避免泄露而将无权读取资源表现为不存在。 |
| `CONFLICT` | `409` | 唯一性冲突或资源当前状态不允许执行动作。 |
| `STORAGE_ERROR` | `500` | 持久化失败，操作未完成。 |

### 3.6 列表排序与分页

| 主题 | MVP 约定 |
| --- | --- |
| 客户工单列表 | 按 `created_at` 倒序返回。 |
| 内部工单列表 | 按 `created_at` 倒序返回。 |
| 工单公开留言 | 按 `sent_at` 正序返回。 |
| 工单操作记录 | 按 `occurred_at` 倒序返回。 |
| 分类、客户、客服管理列表 | 可按 `created_at` 倒序返回，以保持最新创建优先。 |
| 分页 | MVP 不提供分页参数，在小规模数据范围内返回全部授权可见结果。 |

## 4. 会话 Cookie 与认证规则

### 4.1 Cookie 约定

| 属性 | 设计 |
| --- | --- |
| Cookie 名称 | `ticket_session` |
| 值 | 服务端生成的高熵随机会话原始值 |
| `HttpOnly` | `true` |
| `SameSite` | `Lax` |
| `Path` | `/` |
| `Max-Age` | `28800` 秒，即 8 小时 |
| `Secure` | 本地 HTTP 开发演示可为 `false`；HTTPS 环境必须为 `true` |

服务端只在 `store.json` 保存该值的摘要 `token_hash`，任何接口响应不得返回 Cookie 原始值或摘要值。

### 4.2 会话处理

| 场景 | API 行为 |
| --- | --- |
| 登录成功 | 创建服务端会话，通过响应设置 `ticket_session` Cookie。 |
| 获取当前用户 | 验证 Cookie、会话期限与用户状态，返回可展示身份信息。 |
| 退出 | 撤销当前会话并通过响应清除 Cookie。 |
| 客户被禁用后发起请求 | 当前会话视为无效，可撤销会话并返回 `401`。 |
| 会话过期或已撤销 | 返回 `401 AUTHENTICATION_REQUIRED` 并清除无效 Cookie。 |

## 5. 接口总览

### 5.1 认证与身份

| 方法 | 路径 | 用途 | 权限 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/auth/register` | 注册客户账号 | 未登录用户 |
| `POST` | `/api/v1/auth/login` | 登录并创建会话 | 未登录用户 |
| `POST` | `/api/v1/auth/logout` | 退出并撤销当前会话 | 已登录用户 |
| `GET` | `/api/v1/auth/me` | 获取当前登录身份 | 已登录用户 |

### 5.2 分类

| 方法 | 路径 | 用途 | 权限 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/categories/active` | 获取建单可选有效分类 | 客户 |
| `GET` | `/api/v1/admin/categories` | 获取全部分类管理列表 | 管理员 |
| `POST` | `/api/v1/admin/categories` | 创建分类 | 管理员 |
| `PATCH` | `/api/v1/admin/categories/{category_id}` | 编辑分类名称 | 管理员 |
| `PATCH` | `/api/v1/admin/categories/{category_id}/status` | 切换分类启用状态 | 管理员 |

### 5.3 内部账号与客户管理

| 方法 | 路径 | 用途 | 权限 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/admin/agents` | 查看客服账号列表 | 管理员 |
| `POST` | `/api/v1/admin/agents` | 创建客服账号 | 管理员 |
| `GET` | `/api/v1/admin/customers` | 查看客户账号列表 | 管理员 |
| `PATCH` | `/api/v1/admin/customers/{customer_id}/status` | 启用或禁用客户账号 | 管理员 |

### 5.4 客户工单

| 方法 | 路径 | 用途 | 权限 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/customer/tickets` | 获取本人工单列表 | 客户 |
| `POST` | `/api/v1/customer/tickets` | 创建新工单 | 客户 |
| `GET` | `/api/v1/customer/tickets/{ticket_id}` | 获取本人工单详情与留言 | 工单所属客户 |
| `POST` | `/api/v1/customer/tickets/{ticket_id}/messages` | 为本人未关闭工单添加留言 | 工单所属客户 |

### 5.5 内部工单处理

| 方法 | 路径 | 用途 | 权限 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/internal/tickets` | 获取全部工单，可按状态筛选 | 客服、管理员 |
| `GET` | `/api/v1/internal/tickets/{ticket_id}` | 获取内部工单详情、留言和记录 | 客服、管理员 |
| `PATCH` | `/api/v1/internal/tickets/{ticket_id}/assignment` | 分配或重新分配工单 | 管理员 |
| `POST` | `/api/v1/internal/tickets/{ticket_id}/messages` | 添加内部公开留言 | 当前负责人、管理员 |
| `PATCH` | `/api/v1/internal/tickets/{ticket_id}/status` | 推进工单状态 | 当前负责人、管理员 |

## 6. 通用响应模型

### 6.1 当前用户概要 `CurrentUserResponse`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "zhangsan",
  "email": "zhangsan@example.com",
  "role": "customer",
  "status": "active"
}
```

| 字段 | 客户本人 | 客服本人 | 管理员本人 |
| --- | --- | --- | --- |
| `id` | 返回 | 返回 | 返回 |
| `username` | 返回 | 返回 | 返回 |
| `email` | 返回 | 返回 | 返回 |
| `role` | 返回 | 返回 | 返回 |
| `status` | 返回 | 返回 | 返回 |

### 6.2 有效分类概要 `ActiveCategoryResponse`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "name": "使用问题"
}
```

### 6.3 客户工单列表项 `CustomerTicketListItem`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "title": "无法正常使用服务",
  "category_name": "使用问题",
  "status": "unassigned",
  "created_at": "2026-05-26T10:20:30Z"
}
```

客户响应不包含负责人标识或负责人名称。

### 6.4 公开留言 `MessageResponse`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440003",
  "sender_role": "customer",
  "sender_name": "zhangsan",
  "content": "请协助处理。",
  "sent_at": "2026-05-26T10:22:00Z"
}
```

响应使用保存的发送人角色和名称快照，不返回发送人的邮箱。

### 6.5 客户工单详情 `CustomerTicketDetailResponse`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "title": "无法正常使用服务",
  "description": "登录后页面无法继续操作。",
  "category_name": "使用问题",
  "status": "unassigned",
  "created_at": "2026-05-26T10:20:30Z",
  "updated_at": "2026-05-26T10:22:00Z",
  "messages": []
}
```

### 6.6 内部工单列表项 `InternalTicketListItem`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "title": "无法正常使用服务",
  "customer": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "zhangsan"
  },
  "category_name": "使用问题",
  "status": "unassigned",
  "assignee": null,
  "created_at": "2026-05-26T10:20:30Z"
}
```

内部工单响应不返回客户邮箱；负责人非空时仅返回客服 `id` 与 `username`。

### 6.7 操作记录 `AuditLogResponse`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440004",
  "action": "ticket_status_changed",
  "actor": {
    "id": "550e8400-e29b-41d4-a716-446655440005",
    "role": "agent",
    "username": "service01"
  },
  "changes": {
    "status": {
      "before": "processing",
      "after": "resolved"
    }
  },
  "occurred_at": "2026-05-26T11:00:00Z"
}
```

### 6.8 内部工单详情 `InternalTicketDetailResponse`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "title": "无法正常使用服务",
  "description": "登录后页面无法继续操作。",
  "category_name": "使用问题",
  "customer": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "zhangsan"
  },
  "status": "processing",
  "assignee": {
    "id": "550e8400-e29b-41d4-a716-446655440005",
    "username": "service01"
  },
  "created_at": "2026-05-26T10:20:30Z",
  "updated_at": "2026-05-26T11:00:00Z",
  "messages": [],
  "audit_logs": []
}
```

## 7. 认证与身份接口

### 7.1 注册客户账号

| 项目 | 内容 |
| --- | --- |
| 接口 | `POST /api/v1/auth/register` |
| 权限 | 未登录用户 |
| 页面调用 | 客户注册页 |

请求体：

```json
{
  "username": "zhangsan",
  "email": "zhangsan@example.com",
  "password": "Password123",
  "confirm_password": "Password123"
}
```

| 字段 | 规则 |
| --- | --- |
| `username` | 必填；3 至 50 个字符；符合 SRS 用户名规则。 |
| `email` | 必填；有效邮箱格式；不超过 254 个字符。 |
| `password` | 必填；8 至 128 个字符。 |
| `confirm_password` | 必填；必须与 `password` 一致。 |

成功响应：`201 Created`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "zhangsan",
  "email": "zhangsan@example.com",
  "role": "customer",
  "status": "active",
  "created_at": "2026-05-26T10:00:00Z"
}
```

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 字段校验不通过 | `422` | `VALIDATION_ERROR` |
| 用户名或邮箱已经存在 | `409` | `CONFLICT` |

注册成功不自动登录，不设置会话 Cookie。

### 7.2 登录

| 项目 | 内容 |
| --- | --- |
| 接口 | `POST /api/v1/auth/login` |
| 权限 | 未登录用户 |
| 页面调用 | 登录页 |

请求体：

```json
{
  "identifier": "zhangsan@example.com",
  "password": "Password123"
}
```

成功响应：`200 OK`，响应体为 `CurrentUserResponse`，同时设置 `ticket_session` Cookie。

| 失败场景 | 状态码 | 错误代码 | 用户提示 |
| --- | --- | --- | --- |
| 请求字段缺失 | `422` | `VALIDATION_ERROR` | 填写必填信息。 |
| 账号不存在、密码错误或账号不可用 | `401` | `LOGIN_FAILED` | 账号或密码错误，或账号不可用。 |

### 7.3 退出

| 项目 | 内容 |
| --- | --- |
| 接口 | `POST /api/v1/auth/logout` |
| 权限 | 已登录用户 |
| 处理结果 | 撤销当前会话并清除 `ticket_session` Cookie。 |

成功响应：`200 OK`

```json
{
  "success": true
}
```

### 7.4 获取当前登录身份

| 项目 | 内容 |
| --- | --- |
| 接口 | `GET /api/v1/auth/me` |
| 权限 | 已登录用户 |
| 页面调用 | 登录后页面初始化、导航渲染 |

成功响应：`200 OK`，响应体为 `CurrentUserResponse`。

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 无有效会话、会话过期或用户已禁用 | `401` | `AUTHENTICATION_REQUIRED` |

## 8. 分类接口

### 8.1 获取有效分类

| 项目 | 内容 |
| --- | --- |
| 接口 | `GET /api/v1/categories/active` |
| 权限 | 已登录且启用的客户 |
| 页面调用 | 新建工单页 |

成功响应：`200 OK`

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "使用问题"
    }
  ]
}
```

仅返回状态为 `active` 的分类。

### 8.2 获取分类管理列表

| 项目 | 内容 |
| --- | --- |
| 接口 | `GET /api/v1/admin/categories` |
| 权限 | 管理员 |
| 页面调用 | 分类管理页 |

成功响应：`200 OK`

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "使用问题",
      "status": "active",
      "created_at": "2026-05-26T10:00:00Z",
      "updated_at": "2026-05-26T10:00:00Z"
    }
  ]
}
```

### 8.3 创建分类

| 项目 | 内容 |
| --- | --- |
| 接口 | `POST /api/v1/admin/categories` |
| 权限 | 管理员 |
| 操作记录 | 成功时写入 `category_created` |

请求体：

```json
{
  "name": "使用问题"
}
```

成功响应：`201 Created`，返回完整分类管理响应对象。

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 名称为空或超过 50 个字符 | `422` | `VALIDATION_ERROR` |
| 分类名称已经存在 | `409` | `CONFLICT` |

### 8.4 编辑分类名称

| 项目 | 内容 |
| --- | --- |
| 接口 | `PATCH /api/v1/admin/categories/{category_id}` |
| 权限 | 管理员 |
| 操作记录 | 成功时写入 `category_updated` |

请求体：

```json
{
  "name": "产品使用问题"
}
```

成功响应：`200 OK`，返回更新后的分类。既有工单的 `category_name_snapshot` 不变化。

### 8.5 启用或停用分类

| 项目 | 内容 |
| --- | --- |
| 接口 | `PATCH /api/v1/admin/categories/{category_id}/status` |
| 权限 | 管理员 |
| 页面要求 | 停用前由前端展示确认提示。 |
| 操作记录 | 成功时写入 `category_status_changed` |

请求体：

```json
{
  "status": "inactive"
}
```

成功响应：`200 OK`，返回更新后的分类。

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 分类不存在 | `404` | `RESOURCE_NOT_FOUND` |
| 状态值不合法 | `422` | `VALIDATION_ERROR` |

## 9. 管理员用户管理接口

### 9.1 获取客服账号列表

| 项目 | 内容 |
| --- | --- |
| 接口 | `GET /api/v1/admin/agents` |
| 权限 | 管理员 |
| 页面调用 | 客服账号管理页 |

成功响应：`200 OK`

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440005",
      "username": "service01",
      "email": "service01@example.com",
      "created_at": "2026-05-26T10:00:00Z"
    }
  ]
}
```

### 9.2 创建客服账号

| 项目 | 内容 |
| --- | --- |
| 接口 | `POST /api/v1/admin/agents` |
| 权限 | 管理员 |
| 页面调用 | 客服账号管理页 |

请求体：

```json
{
  "username": "service01",
  "email": "service01@example.com",
  "password": "Password123",
  "confirm_password": "Password123"
}
```

成功响应：`201 Created`，返回新客服账号信息，不包含密码或密码哈希。

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 字段校验错误 | `422` | `VALIDATION_ERROR` |
| 用户名或邮箱已存在 | `409` | `CONFLICT` |

### 9.3 获取客户账号列表

| 项目 | 内容 |
| --- | --- |
| 接口 | `GET /api/v1/admin/customers` |
| 权限 | 管理员 |
| 页面调用 | 客户账号管理页 |

成功响应：`200 OK`

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "username": "zhangsan",
      "email": "zhangsan@example.com",
      "status": "active",
      "created_at": "2026-05-26T10:00:00Z"
    }
  ]
}
```

### 9.4 启用或禁用客户账号

| 项目 | 内容 |
| --- | --- |
| 接口 | `PATCH /api/v1/admin/customers/{customer_id}/status` |
| 权限 | 管理员 |
| 页面要求 | 禁用前由前端展示确认提示。 |
| 操作记录 | 成功时写入 `customer_status_changed` |

请求体：

```json
{
  "status": "disabled"
}
```

成功响应：`200 OK`，返回更新后的客户账号信息。

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 目标客户不存在 | `404` | `RESOURCE_NOT_FOUND` |
| 目标用户不是客户 | `409` | `CONFLICT` |
| 状态值不合法 | `422` | `VALIDATION_ERROR` |

客户被禁用后，后续携带既有会话访问受保护接口时返回 `401 AUTHENTICATION_REQUIRED`。

## 10. 客户工单接口

### 10.1 获取本人工单列表

| 项目 | 内容 |
| --- | --- |
| 接口 | `GET /api/v1/customer/tickets` |
| 权限 | 已登录且启用的客户 |
| 页面调用 | 我的工单页 |

成功响应：`200 OK`

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "title": "无法正常使用服务",
      "category_name": "使用问题",
      "status": "unassigned",
      "created_at": "2026-05-26T10:20:30Z"
    }
  ]
}
```

不接收搜索、状态筛选或分页参数，结果按创建时间倒序返回。

### 10.2 创建工单

| 项目 | 内容 |
| --- | --- |
| 接口 | `POST /api/v1/customer/tickets` |
| 权限 | 已登录且启用的客户 |
| 页面调用 | 新建工单页 |
| 操作记录 | 成功时写入 `ticket_created` |

请求体：

```json
{
  "category_id": "550e8400-e29b-41d4-a716-446655440001",
  "title": "无法正常使用服务",
  "description": "登录后页面无法继续操作。"
}
```

成功响应：`201 Created`，返回 `CustomerTicketDetailResponse`。状态为 `unassigned`，且响应中不包含负责人。

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 标题或描述校验失败 | `422` | `VALIDATION_ERROR` |
| 分类不存在或已经停用 | `409` | `CONFLICT` |

### 10.3 获取本人工单详情

| 项目 | 内容 |
| --- | --- |
| 接口 | `GET /api/v1/customer/tickets/{ticket_id}` |
| 权限 | 创建该工单的启用客户 |
| 页面调用 | 客户工单详情页 |

成功响应：`200 OK`，返回 `CustomerTicketDetailResponse`，其中 `messages` 按发送时间正序排列。

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 工单不存在或不属于当前客户 | `404` | `RESOURCE_NOT_FOUND` |

### 10.4 客户添加公开留言

| 项目 | 内容 |
| --- | --- |
| 接口 | `POST /api/v1/customer/tickets/{ticket_id}/messages` |
| 权限 | 创建该工单的启用客户，且工单未关闭 |
| 页面调用 | 客户工单详情页 |

请求体：

```json
{
  "content": "请问目前的处理进度如何？"
}
```

成功响应：`201 Created`，返回 `MessageResponse`。

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 留言为空或超过 2000 个字符 | `422` | `VALIDATION_ERROR` |
| 工单不存在或不属于当前客户 | `404` | `RESOURCE_NOT_FOUND` |
| 工单已经关闭 | `409` | `CONFLICT` |

## 11. 内部工单接口

### 11.1 获取内部工单列表

| 项目 | 内容 |
| --- | --- |
| 接口 | `GET /api/v1/internal/tickets` |
| 权限 | 客服、管理员 |
| 页面调用 | 内部工单列表页 |

查询参数：

| 参数 | 必填 | 规则 |
| --- | --- | --- |
| `status` | 否 | 省略时返回全部；传入时只能是单个工单状态枚举值。 |

请求示例：

```text
GET /api/v1/internal/tickets?status=processing
```

成功响应：`200 OK`

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "title": "无法正常使用服务",
      "customer": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "username": "zhangsan"
      },
      "category_name": "使用问题",
      "status": "processing",
      "assignee": {
        "id": "550e8400-e29b-41d4-a716-446655440005",
        "username": "service01"
      },
      "created_at": "2026-05-26T10:20:30Z"
    }
  ]
}
```

响应不包含客户邮箱，结果按创建时间倒序返回。

### 11.2 获取内部工单详情

| 项目 | 内容 |
| --- | --- |
| 接口 | `GET /api/v1/internal/tickets/{ticket_id}` |
| 权限 | 客服、管理员 |
| 页面调用 | 内部工单详情页 |

成功响应：`200 OK`，返回 `InternalTicketDetailResponse`。其中：

- `messages` 按 `sent_at` 正序排列。
- `audit_logs` 仅包含该工单相关记录，并按 `occurred_at` 倒序排列。
- 响应包含客户用户名和负责人用户名，但不包含客户邮箱。

### 11.3 分配或重新分配工单

| 项目 | 内容 |
| --- | --- |
| 接口 | `PATCH /api/v1/internal/tickets/{ticket_id}/assignment` |
| 权限 | 管理员 |
| 页面调用 | 内部工单详情页分配区 |
| 操作记录 | 首次分配写入 `ticket_assigned`；更换负责人写入 `ticket_reassigned`。 |

请求体：

```json
{
  "assignee_user_id": "550e8400-e29b-41d4-a716-446655440005"
}
```

成功响应：`200 OK`

```json
{
  "ticket_id": "550e8400-e29b-41d4-a716-446655440002",
  "assignee": {
    "id": "550e8400-e29b-41d4-a716-446655440005",
    "username": "service01"
  },
  "status": "unassigned",
  "updated_at": "2026-05-26T10:40:00Z"
}
```

分配不自动修改工单状态。

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 工单不存在 | `404` | `RESOURCE_NOT_FOUND` |
| 目标用户不存在或不是客服 | `409` | `CONFLICT` |
| 工单已关闭 | `409` | `CONFLICT` |

### 11.4 内部添加公开留言

| 项目 | 内容 |
| --- | --- |
| 接口 | `POST /api/v1/internal/tickets/{ticket_id}/messages` |
| 权限 | 当前负责客服或管理员，且工单未关闭 |
| 页面调用 | 内部工单详情页 |

请求体：

```json
{
  "content": "我们正在核查该问题，请稍候。"
}
```

成功响应：`201 Created`，返回 `MessageResponse`。发送留言不自动推进工单状态。

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 留言内容不合法 | `422` | `VALIDATION_ERROR` |
| 工单不存在 | `404` | `RESOURCE_NOT_FOUND` |
| 客服不是当前负责人 | `403` | `FORBIDDEN` |
| 工单已关闭 | `409` | `CONFLICT` |

### 11.5 推进工单状态

| 项目 | 内容 |
| --- | --- |
| 接口 | `PATCH /api/v1/internal/tickets/{ticket_id}/status` |
| 权限 | 当前负责客服或管理员 |
| 页面调用 | 内部工单详情页状态操作区 |
| 操作记录 | 成功时写入 `ticket_status_changed` |

请求体：

```json
{
  "status": "processing"
}
```

允许的状态请求：

| 当前状态 | 可提交目标状态 |
| --- | --- |
| `unassigned` | `processing` |
| `processing` | `resolved` |
| `resolved` | `closed` |
| `closed` | 无 |

成功响应：`200 OK`

```json
{
  "ticket_id": "550e8400-e29b-41d4-a716-446655440002",
  "status": "processing",
  "updated_at": "2026-05-26T10:45:00Z"
}
```

| 失败场景 | 状态码 | 错误代码 |
| --- | --- | --- |
| 工单不存在 | `404` | `RESOURCE_NOT_FOUND` |
| 客服不是当前负责人 | `403` | `FORBIDDEN` |
| 状态值不合法 | `422` | `VALIDATION_ERROR` |
| 状态跳级、回退或工单已关闭 | `409` | `CONFLICT` |

关闭工单的确认对话由前端在请求发送前执行；后端无论前端表现如何，仍只接受合法状态变化。

## 12. 状态码与错误处理映射

| 接口类别 | `401` | `403` | `404` | `409` | `422` |
| --- | --- | --- | --- | --- | --- |
| 认证 | 未登录/登录失败 | 不适用 | 不适用 | 标识冲突仅注册适用 | 字段错误 |
| 分类管理 | 未登录 | 非管理员 | 分类不存在 | 名称冲突 | 字段/状态错误 |
| 用户管理 | 未登录 | 非管理员 | 目标不存在 | 标识或目标角色冲突 | 字段/状态错误 |
| 客户工单 | 未登录/客户禁用 | 非客户角色 | 不存在或非本人资源 | 分类不可用、工单关闭 | 字段错误 |
| 内部工单 | 未登录 | 角色无权或非负责人处理 | 工单不存在 | 状态冲突、关闭限制、分配目标错误 | 字段/枚举错误 |

### 12.1 资源隐藏策略

对于客户请求访问非本人拥有的工单，接口返回 `404 RESOURCE_NOT_FOUND`，不返回 `403`，从而避免泄露其他客户工单是否存在。内部人员访问已有工单但执行无权动作时，可返回 `403 FORBIDDEN`，因为客服已具备查看全部工单的权限。

## 13. 前端页面与接口映射

| 页面 | 初始化读取接口 | 提交/操作接口 |
| --- | --- | --- |
| 登录页 | 可选调用 `GET /auth/me` 判断已有会话 | `POST /auth/login` |
| 客户注册页 | 无 | `POST /auth/register` |
| 我的工单页 | `GET /auth/me`、`GET /customer/tickets` | 无 |
| 新建工单页 | `GET /auth/me`、`GET /categories/active` | `POST /customer/tickets` |
| 客户工单详情页 | `GET /auth/me`、`GET /customer/tickets/{id}` | `POST /customer/tickets/{id}/messages` |
| 内部工单列表页 | `GET /auth/me`、`GET /internal/tickets` | 通过 `status` 参数筛选 |
| 内部工单详情页 | `GET /auth/me`、`GET /internal/tickets/{id}` | `PATCH /assignment`、`POST /messages`、`PATCH /status` |
| 分类管理页 | `GET /auth/me`、`GET /admin/categories` | `POST /admin/categories`、`PATCH /admin/categories/{id}`、`PATCH /status` |
| 客服账号管理页 | `GET /auth/me`、`GET /admin/agents` | `POST /admin/agents` |
| 客户账号管理页 | `GET /auth/me`、`GET /admin/customers` | `PATCH /admin/customers/{id}/status` |

表中省略的接口路径均使用 `/api/v1` 前缀。

## 14. 权限与接口追踪矩阵

| 业务能力 | 相关接口 | 权限要点 |
| --- | --- | --- |
| 客户开放注册与登录 | `/auth/register`、`/auth/login`、`/auth/logout`、`/auth/me` | 注册只产生客户；会话校验用户状态。 |
| 管理员创建客服 | `/admin/agents` | 仅管理员；不返回密码哈希。 |
| 管理员启停客户 | `/admin/customers/{id}/status` | 仅管理员；禁用后客户会话不可继续使用。 |
| 管理员维护分类 | `/admin/categories` 系列接口 | 仅管理员；停用不改变历史工单分类快照。 |
| 客户创建查看工单 | `/customer/tickets` 系列接口 | 仅客户本人资源；不返回负责人。 |
| 客户公开留言 | `/customer/tickets/{id}/messages` | 本人、账号有效、工单未关闭。 |
| 内部查看全部工单 | `/internal/tickets` 系列 `GET` 接口 | 客服和管理员均可查看；不返回客户邮箱。 |
| 管理员分配工单 | `/internal/tickets/{id}/assignment` | 仅管理员；仅指派客服；未关闭工单。 |
| 内部公开留言 | `/internal/tickets/{id}/messages` | 负责人或管理员；未关闭工单。 |
| 内部推进状态 | `/internal/tickets/{id}/status` | 负责人或管理员；遵循线性状态转换。 |

## 15. 安全与接口实现要求

| 编号 | 要求 |
| --- | --- |
| API-SEC-001 | 受保护接口必须从服务端会话解析当前用户，不接受请求体中自报角色或操作者标识。 |
| API-SEC-002 | 建单请求中的创建客户由当前会话确定，不接受 `customer_user_id` 输入。 |
| API-SEC-003 | 留言发送人和审计操作者由当前会话确定，不接受前端指定。 |
| API-SEC-004 | 客户工单响应不得返回负责人信息或内部操作记录。 |
| API-SEC-005 | 内部工单响应不得返回客户邮箱、密码字段或会话字段。 |
| API-SEC-006 | 用户管理响应不得返回密码哈希或会话信息。 |
| API-SEC-007 | 页面展示服务端返回的标题、描述和留言时，必须作为文本处理，防止脚本执行。 |
| API-SEC-008 | 写入接口应在业务变更与必要审计记录全部持久化成功后才返回成功响应。 |

## 16. 已确认的接口决策

以下内容将已确认需求、交互与数据模型落实为具体接口契约，未扩大 MVP 功能范围；这些接口决策已经用户确认，将作为前后端实现和接口测试的正式依据：

| 编号 | 已确认接口决策 | 方案 |
| --- | --- | --- |
| API-C01 | API 路径版本 | 业务接口统一使用 `/api/v1` 前缀。 |
| API-C02 | 路由分区 | 采用 `/auth`、`/categories`、`/customer`、`/internal`、`/admin` 分区表达访问边界。 |
| API-C03 | Cookie 名称及属性 | 会话 Cookie 命名为 `ticket_session`，使用 `HttpOnly`、`SameSite=Lax`、`Path=/` 与 8 小时期限。 |
| API-C04 | 成功与错误响应 | 单资源直接返回对象，列表返回 `{ "items": [] }`；失败统一返回 `error.code/message/field_errors`。 |
| API-C05 | 业务错误状态码 | 使用 `401` 未认证、`403` 无处理权限、`404` 不存在或客户越权资源隐藏、`409` 状态/冲突、`422` 字段校验。 |
| API-C06 | 客户工单详情暴露范围 | 客户详情响应不包含负责人和内部操作记录。 |
| API-C07 | 内部工单详情暴露范围 | 内部详情包含客户用户名、负责人和工单操作记录，但不包含客户邮箱。 |
| API-C08 | 分类有效列表访问 | 建单使用的有效分类接口仅开放给已登录客户，不提供匿名建单准备接口。 |
| API-C09 | 工单分配接口 | 首次分配与重新分配合并为同一个负责人更新接口，由当前负责人是否为空决定审计动作。 |
| API-C10 | 状态推进接口 | 前端提交目标状态，后端校验其是否为唯一合法下一状态；关闭确认由页面负责展示。 |
| API-C11 | MVP 列表范围 | 不设计分页、高级筛选或搜索参数，内部工单仅提供单一 `status` 查询参数。 |

## 17. 后续文档衔接

本 API 设计经确认后，后续文档应依据本文继续细化：

| 文档 | 需要继承的内容 |
| --- | --- |
| 测试与验收方案 | 接口正常路径、角色越权、状态冲突、敏感字段隔离、会话与持久化验证。 |
| MVP 实施计划 | 路由、模型、服务、仓储、前端请求模块及接口联调任务拆解。 |

## 18. 确认记录

| 日期 | 确认人 | 结果 | 备注 |
| --- | --- | --- | --- |
| 2026-05-26 | 用户 | 已确认 | 本文档及第 16 章接口决策可作为后续前后端实现、接口测试与实施计划的正式接口基线。 |
