"""
用户注册功能 TDD 测试（基于 OpenSpec specs/registration/spec.md）
"""
import pytest
import time
from src.user_registration import (
    RegisterService,
    VerifyService,
    UserRepository,
    EmailService,
    VerificationTokenStore,
    User,
)


class TestEmailRegistration:
    """对应 specs/registration/spec.md: Email Registration"""

    @pytest.fixture
    def repo(self) -> UserRepository:
        return UserRepository()

    @pytest.fixture
    def email_service(self) -> EmailService:
        return EmailService()

    @pytest.fixture
    def token_store(self) -> VerificationTokenStore:
        return VerificationTokenStore()

    @pytest.fixture
    def register_service(
        self, repo: UserRepository, email_service: EmailService, token_store: VerificationTokenStore
    ) -> RegisterService:
        return RegisterService(repo, email_service, token_store)

    @pytest.fixture
    def verify_service(
        self, repo: UserRepository, token_store: VerificationTokenStore
    ) -> VerifyService:
        return VerifyService(repo, token_store)

    # --- Scenario: Successful registration ---
    def test_successful_registration_creates_pending_user(
        self, register_service: RegisterService, repo: UserRepository
    ) -> None:
        """WHEN user submits valid email and password,
        THEN a new user is created with status 'pending'."""
        user = register_service.register("test@example.com", "Password123")

        assert user.status == "pending"
        assert user.email == "test@example.com"
        assert user.verified_at is None
        # 通过公共接口验证：能从 repo 查到
        saved = repo.find_by_email("test@example.com")
        assert saved is not None
        assert saved.id == user.id

    # --- Scenario: Duplicate email ---
    def test_duplicate_email_returns_error(
        self, register_service: RegisterService
    ) -> None:
        """WHEN user submits an email that is already registered,
        THEN the system raises ValueError."""
        register_service.register("dup@example.com", "Pass1234")

        with pytest.raises(ValueError, match="该邮箱已注册"):
            register_service.register("dup@example.com", "Pass1234")

    # --- Scenario: Invalid email format ---
    @pytest.mark.parametrize("bad_email", ["notanemail", "@missing.com", "no@domain"])
    def test_invalid_email_returns_error(
        self, register_service: RegisterService, bad_email: str
    ) -> None:
        """WHEN user submits invalid email format,
        THEN the system raises ValueError."""
        with pytest.raises(ValueError, match="邮箱格式无效"):
            register_service.register(bad_email, "Pass1234")

    # --- Scenario: Weak password ---
    @pytest.mark.parametrize("weak_password", ["short1A", "nouppercase1", "NOLOWERCASE1", "NoDigitsABC"])
    def test_weak_password_returns_error(
        self, register_service: RegisterService, weak_password: str
    ) -> None:
        """WHEN user submits a weak password,
        THEN the system raises ValueError."""
        with pytest.raises(ValueError, match="密码至少8位，需包含大小写字母和数字（例：MyPass123）"):
            register_service.register("test@example.com", weak_password)


class TestEmailVerification:
    """对应 specs/registration/spec.md: Email Verification"""

    @pytest.fixture
    def repo(self) -> UserRepository:
        repo = UserRepository()
        user = User(email="verify@example.com", password_hash="abc123", status="pending")
        repo.save(user)
        return repo

    @pytest.fixture
    def token_store(self, repo: UserRepository) -> VerificationTokenStore:
        ts = VerificationTokenStore()
        user = repo.find_by_email("verify@example.com")
        ts._tokens["test-token"] = (user.id, time.time() + 86400)  # type: ignore[index]
        return ts

    @pytest.fixture
    def verify_service(
        self, repo: UserRepository, token_store: VerificationTokenStore
    ) -> VerifyService:
        return VerifyService(repo, token_store)

    # --- Scenario: Valid verification token ---
    def test_valid_token_activates_user(
        self, verify_service: VerifyService, repo: UserRepository
    ) -> None:
        """WHEN user clicks a valid verification link,
        THEN user status changes to 'active'."""
        user = verify_service.verify("test-token")

        assert user.status == "active"
        assert user.verified_at is not None

    # --- Scenario: Expired verification token ---
    def test_expired_token_returns_error(
        self, verify_service: VerifyService
    ) -> None:
        """WHEN user clicks an expired verification link,
        THEN the system raises ValueError."""
        with pytest.raises(ValueError, match="验证链接无效或已过期"):
            verify_service.verify("nonexistent-token")
