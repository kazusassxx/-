# Design: add-user-registration

## Architecture Overview
新增 User 模块，包含注册 Service 和验证 Service。使用 bcrypt 哈希密码，JWT 生成验证 token。

## Data Model Changes

### User 表
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| email | VARCHAR(255) | UNIQUE, NOT NULL |
| password_hash | VARCHAR(255) | NOT NULL |
| status | ENUM('pending', 'active', 'disabled') | DEFAULT 'pending' |
| created_at | TIMESTAMP | DEFAULT NOW() |
| verified_at | TIMESTAMP | NULLABLE |

## API / Interface Contract

### POST /api/auth/register
- Body: `{ "email": string, "password": string }`
- Success: 201 `{ "message": "Verification email sent" }`
- Errors: 400, 409

### GET /api/auth/verify?token=<token>
- Success: 200 `{ "message": "Account activated" }`
- Errors: 400 (invalid/expired token)

## Migration Strategy
- 新表，无数据迁移需求
- 先建表再上线 API
