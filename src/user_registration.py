"""
用户注册与验证功能

OpenSpec: add-user-registration
"""
import re
import hashlib
import uuid
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class User:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    email: str = ""
    password_hash: str = ""
    status: str = "pending"  # pending | active | disabled
    created_at: float = field(default_factory=time.time)
    verified_at: Optional[float] = None


class UserRepository:
    """User 持久层（Mock 实现，真实场景替换为 DB）"""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}  # id -> User
        self._by_email: dict[str, User] = {}  # email -> User

    def save(self, user: User) -> None:
        self._users[user.id] = user
        self._by_email[user.email.lower()] = user

    def find_by_id(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    def find_by_email(self, email: str) -> Optional[User]:
        return self._by_email.get(email.lower())


class VerificationTokenStore:
    """验证 token 存储（Mock 实现，真实场景替换为 Redis/DB）"""

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[str, float]] = {}  # token -> (user_id, expires_at)

    def create(self, user_id: str, ttl_seconds: int = 86400) -> str:
        raw = f"{user_id}:{uuid.uuid4()}:{time.time()}"
        token = hashlib.sha256(raw.encode()).hexdigest()
        self._tokens[token] = (user_id, time.time() + ttl_seconds)
        return token

    def consume(self, token: str) -> Optional[str]:
        entry = self._tokens.pop(token, None)
        if entry is None:
            return None
        user_id, expires_at = entry
        if time.time() > expires_at:
            return None
        return user_id


class EmailService:
    """邮件服务（Mock 实现）"""

    def send_verification_email(self, email: str, token: str) -> bool:
        # Mock: 总是返回 True
        return True


class RegisterService:
    """用户注册服务"""

    PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")

    def __init__(
        self,
        repo: UserRepository,
        email_service: EmailService,
        token_store: VerificationTokenStore,
    ) -> None:
        self._repo = repo
        self._email_service = email_service
        self._token_store = token_store

    def register(self, email: str, password: str) -> User:
        if not self._is_valid_email(email):
            raise ValueError("邮箱格式无效")

        if self._repo.find_by_email(email) is not None:
            raise ValueError("该邮箱已注册")

        if not self.PASSWORD_PATTERN.match(password):
            raise ValueError("密码至少8位，需包含大小写字母和数字（例：MyPass123）")

        user = User(email=email.lower(), password_hash=hashlib.sha256(password.encode()).hexdigest())
        self._repo.save(user)

        token = self._token_store.create(user.id)
        self._email_service.send_verification_email(user.email, token)

        return user

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email))


class VerifyService:
    """邮箱验证服务"""

    def __init__(self, repo: UserRepository, token_store: VerificationTokenStore) -> None:
        self._repo = repo
        self._token_store = token_store

    def verify(self, token: str) -> User:
        user_id = self._token_store.consume(token)
        if user_id is None:
            raise ValueError("验证链接无效或已过期")

        user = self._repo.find_by_id(user_id)
        if user is None:
            raise ValueError("用户不存在")

        user.status = "active"
        user.verified_at = time.time()
        return user
