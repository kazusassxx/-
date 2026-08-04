# Tasks: add-user-registration

## 1. 数据层
- [ ] 1.1 创建 User 表 migration
- [ ] 1.2 实现 UserRepository

## 2. 核心逻辑
- [ ] 2.1 实现 RegisterService（校验 + 创建用户）
- [ ] 2.2 实现 EmailService（发送验证邮件）
- [ ] 2.3 实现 VerifyService（验证 token 并激活）

## 3. API 层
- [ ] 3.1 实现 POST /api/auth/register 端点
- [ ] 3.2 实现 GET /api/auth/verify 端点

## 4. 边界处理
- [ ] 4.1 添加同 IP 限流
- [ ] 4.2 添加输入校验中间件
