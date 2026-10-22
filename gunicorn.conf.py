"""Gunicorn loads this file from the project working directory by default."""

accesslog = '-'
errorlog = '-'
capture_output = True
# Do not include query strings, request headers, cookies or submitted data.
access_log_format = '%(t)s status=%(s)s method=%(m)s path=%(U)s duration=%(L)s pid=%(p)s request_id=%({x-request-id}o)s'
