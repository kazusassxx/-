## ADDED Requirements

### Requirement: Email Registration
The system SHALL allow a user to register with a valid email and password.

#### Scenario: Successful registration
- **WHEN** user submits valid email and password
- **THEN** a new user record is created with `status: pending` and a verification email is sent

#### Scenario: Duplicate email
- **WHEN** user submits an email that is already registered
- **THEN** the system returns 409 Conflict with message "Registration failed"

#### Scenario: Invalid email format
- **WHEN** user submits an email that does not match standard email format
- **THEN** the system returns 400 Bad Request with message "Invalid email format"

#### Scenario: Weak password
- **WHEN** user submits a password shorter than 8 characters or missing required character types
- **THEN** the system returns 400 Bad Request with message "Password must be at least 8 characters with uppercase, lowercase, and number"

### Requirement: Email Verification
The system SHALL activate a user account upon successful email verification.

#### Scenario: Valid verification token
- **WHEN** user clicks a valid verification link
- **THEN** user status changes to `active`

#### Scenario: Expired verification token
- **WHEN** user clicks an expired verification link (>24h)
- **THEN** the system returns "Verification link expired" and offers re-send
