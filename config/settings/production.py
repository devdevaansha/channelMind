from .base import *  # noqa

DEBUG = False
CONN_MAX_AGE = 0  # Neon handles connection pooling on its side
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
