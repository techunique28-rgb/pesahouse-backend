# Accounts implementation: current progress

This document records what is present in the repository today to support a code
review. It describes the implementation, not a claim that every flow has been
validated in a running environment or is production-ready.

## What is in place

- The active Django app is `accounts` (plural). It is installed in
  `pesahouse/settings/base.py`, owns the configured `AUTH_USER_MODEL`, and
  mounts its API routes under `/api/v1/`.
- The account identity is a UUID-backed custom user, authenticated by phone
  number and password. Phone numbers are parsed using Uganda as the default
  region and saved in E.164 format. Email is stripped and lower-cased.
- Tenant signup and landlord signup both validate passwords and create users
  with phone verification initially false. Landlord signup also creates the
  landlord's root organization, owner staff assignment, default join code,
  and audit record in a database transaction.
- Signup verification, password reset, account claiming, and token/session
  management are represented in the API. OTP creation and delivery are
  delegated to the notification task pipeline.
- JWT authentication is the REST framework default. Access tokens last 15
  minutes, refresh tokens last 7 days, refresh rotation is enabled, and rotated
  tokens are blacklisted.
- Development settings use SQLite, local-memory cache, eager Celery tasks, and
  console email. Production settings require a secret, hosts, PostgreSQL,
  Redis, Celery, SMTP, and object-storage configuration.

## Account model and shared rules

`accounts.models.User` stores:

- `phone_e164` as the required unique login identifier;
- optional email, full name, phone/email verification flags, active/admin
  flags, preferred notification channel, and WhatsApp opt-in;
- `created_at` and `deleted_at` timestamps. Deletion requests currently mark
  the account inactive and set `deleted_at`; they do not physically remove it.

The database constraints require a leading `+` on stored phone numbers and
lower-case email. Non-deleted accounts cannot share a non-null email. `save()`
normalizes phone and email on every ordinary model save. `UserManager` handles
password hashing and provides the superuser defaults.

Password validators are configured globally in `base.py`. Signup and
password-change services explicitly invoke them. Login requires a valid
password, an active account, and a verified phone number. Five failed login
attempts for a normalized phone number set a 15-minute cache lock; a successful
login clears the failure counter.

## API routes and behavior

All routes below are prefixed with `/api/v1`. Unless noted otherwise, the
global REST permission is `IsAuthenticated`.

| Route | Access | Current behavior |
| --- | --- | --- |
| `GET /health/` | Public | Returns `{"status": "ok"}`. |
| `POST /accounts/signup/tenant/` | Public; signup-throttled | Validates signup fields/password, creates an unverified user, queues signup verification, and returns a generic success detail. |
| `POST /accounts/signup/landlord/` | Public; signup-throttled | Creates the user, landlord/root unit, owner role assignment, join code, audit record, then queues signup verification. Returns user and landlord IDs. Requires the RBAC permission catalog to have been seeded. |
| `POST /accounts/verify-otp/` | Public; OTP-throttled | Accepts a purpose, phone, and six-digit code. Successful signup/login/claim-purpose verification marks the phone verified. |
| `POST /accounts/resend-otp/` | Public; resend-throttled | Looks up the phone, applies a resend lock, and asks notifications to send the requested purpose. Its response is intentionally generic for unknown phones. |
| `POST /accounts/login/` | Public; login-throttled | Returns access and refresh JWTs after password, active-account, and verified-phone checks. |
| `POST /accounts/token/refresh/` | Public | Uses SimpleJWT's refresh endpoint and configured refresh rotation/blacklisting. |
| `POST /accounts/logout/` | Authenticated | Blacklists the supplied refresh token. |
| `POST /accounts/logout-all/` | Authenticated | Attempts to blacklist every outstanding refresh token for the current user. |
| `GET/PATCH /accounts/me/` | Authenticated | Reads or partially updates the serializer's profile fields. ID, phone, and verification flags are read-only here. |
| `GET /accounts/contexts/` | Authenticated | Lists the user's active staff and pending/active tenant contexts, with landlord IDs/names. |
| `POST /accounts/password/reset/request/` | Public; reset-throttled | Queues a reset code if a matching account exists; response does not disclose account existence. |
| `POST /accounts/password/reset/confirm/` | Public | Verifies reset code, changes password, and attempts to revoke outstanding refresh tokens. |
| `POST /accounts/password/change/` | Authenticated | Checks the old password, validates and changes the new password, revokes refresh tokens, and queues a password-changed notice. |
| `POST /accounts/claim/` | Authenticated by the global default | Verifies a claim code and sets the password/phone-verification flag. |
| `POST /accounts/email/send-code/` | Authenticated | Requests email verification if the user has an email address. |
| `POST /accounts/email/verify/` | Authenticated | Verifies an email code and sets `is_email_verified`. |
| `POST /accounts/phone/change/request/` | Authenticated | Stores a pending normalized phone for five minutes and requests verification. |
| `POST /accounts/phone/change/confirm/` | Authenticated | Verifies the code and replaces the account phone. |
| `GET/DELETE /accounts/sessions/` | Authenticated | Lists outstanding refresh tokens or attempts to revoke the token selected by query parameter `id`. |
| `POST /accounts/delete-request/` | Authenticated | Refuses deletion when the caller has an active owner assignment; otherwise soft-disables the user. |

The login, verify-OTP, resend-OTP, signup, and password-reset endpoints have
configured rates. API documentation is exposed at `/api/v1/docs/`; the schema
is at `/api/v1/schema/`.

## OTP and notification flow

The account view/service calls `notify()` after a database commit where
appropriate. The notification service writes a log and schedules
`send_notification`. The task creates a six-digit code, puts an HMAC of it (and
an attempt count) in cache, renders the purpose-specific message, then tries
the configured channel. In production, SMS and WhatsApp have provider fallback
paths; email uses the email channel. In debug mode, delivery is directed to the
console. The raw OTP is not stored in the account database.

OTP cache entries use purpose and user ID as their key and expire after five
minutes. Verification increments failed attempts, rejects after the configured
five-attempt limit, and uses constant-time digest comparison. The resend lock
is 60 seconds. Notification sends also have configured per-recipient/hour and
per-user/day limits.

One important detail for future changes: `accounts.otp.issue_otp()` sets the
resend lock only. The notification task is what actually creates the OTP
payload. Accordingly, the OTP purpose passed to notification delivery must
match the purpose later used by `verify_otp()`.

## Review notes and known gaps

These are concrete code-path observations to prioritize during review:

1. **Email and phone-change OTP purposes do not match.** Email send stores/looks
   up `OTP_EMAIL` but calls `notify("OTP_SIGNUP", ...)`. Phone change stores/
   verifies `OTP_PHONE_CHANGE` but calls `notify("OTP_LOGIN", ...)`. The
   notification task generates the code under the notified purpose, so these
   verification flows cannot validate the code they send.
2. **Login OTP is configured but not implemented in the login flow.**
   `OPTIONAL_LOGIN_OTP` is read from settings, and `OTP_LOGIN` templates exist,
   but `login_user()` issues tokens immediately after the password and verified
   phone checks; it does not consult the setting or require an OTP.
3. **Password policy is inconsistent.** Signup and authenticated password
   change call Django password validators. Password-reset confirmation and
   account claim set a password without explicitly validating it.
4. **Some failure paths are hidden.** Landlord signup catches `Exception` in
   addition to expected validation errors and returns a 400; session revocation
   and `logout_all()` suppress token-blacklist errors. Review whether failures
   should be logged or surfaced rather than returning success-shaped responses.
5. **Account state and session invalidation need review.** Reset and normal
   password change attempt to revoke refresh tokens, but claim does not. The
   sessions DELETE endpoint returns “Session revoked” even if the supplied ID
   does not belong to the user or token blacklisting fails.
6. **Profile email edits do not reset verification.** `MeSerializer` permits
   email changes while `is_email_verified` is read-only. Confirm whether an
   address change should clear the verification flag and require re-verification.
7. **The claim route is not public under current defaults.** It does not set
   `AllowAny`, so the global `IsAuthenticated` permission applies. Confirm this
   is intended for invited/unclaimed accounts.
8. **There are no account-app migration files in the current tree.** Confirm
   migration history exists where deployment expects it and that a fresh
   database can be initialized repeatably.
9. **There are two similarly named packages.** `accounts` is the installed app
   and the package whose URLs are included. The separate `account` package has
   placeholder views/tests and is not included in the shown project settings or
   root URL configuration; confirm whether it is stale or intentionally
   reserved.

## Current verification status

The repository includes focused signup-security tests in
`accounts/tests/test_signup_security.py` and OTP/template tests under
`notifications/tests/`. I attempted to run the account and notification tests
and Django's system check, but both commands stopped during Django startup
because the active virtual environment does not have Celery installed
(`ModuleNotFoundError: No module named 'celery'`). Therefore this document
records a source inspection only; it does not claim that tests or system checks
pass.
