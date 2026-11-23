from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle


class LoginThrottle(ScopedRateThrottle):
    scope = "login"


class VerifyOtpThrottle(ScopedRateThrottle):
    scope = "verify_otp"


class ResendOtpThrottle(ScopedRateThrottle):
    scope = "resend_otp"


class SignupThrottle(ScopedRateThrottle):
    scope = "signup"


class PasswordResetThrottle(ScopedRateThrottle):
    scope = "password_reset"
