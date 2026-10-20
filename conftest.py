"""
Root pytest configuration and compatibility shims.
Applies safe backwards-compatibility fixes for Python 3.14 / bcrypt >= 4.0 / passlib.
"""
import sys

# Safe compatibility fix for passlib 1.7.4 with modern bcrypt >= 4.0 on Python 3.14
try:
    import bcrypt
    if not hasattr(bcrypt, "__about__"):
        bcrypt.__about__ = type("about", (), {"__version__": bcrypt.__version__})

    import passlib.handlers.bcrypt as pb
    if hasattr(pb, "_BcryptBackend"):
        orig_calc = pb._BcryptBackend._calc_checksum

        def _safe_bcrypt_calc_checksum(self, secret):
            if isinstance(secret, str):
                secret = secret.encode("utf-8")
            if len(secret) > 72:
                secret = secret[:72]
            return orig_calc(self, secret)

        pb._BcryptBackend._calc_checksum = _safe_bcrypt_calc_checksum
except Exception:
    pass
