# Security audit summary

Security audit date: 2026-07-29.

Main verified application protections:

- Flask DEBUG defaults to disabled;
- production refuses missing or known placeholder `SECRET_KEY`;
- CSRF protection is enabled;
- cookies are configured with HttpOnly and SameSite;
- secure cookies are documented for production HTTPS;
- security headers are set by Flask;
- user-controlled HTML is escaped in server-rendered pages;
- SQLAlchemy ORM is used for normal database access;
- upload extension and magic-byte validation exists;
- login rate limiting and account lockout exist;
- security events are logged without storing passwords;
- role and project-level access checks are covered by tests.

Main infrastructure risks found from public checks:

- PostgreSQL port `5432` was reachable from the internet;
- ports `5000` and `8080` were reachable from the internet;
- live Nginx exposed version information;
- full server-side audit requires working SSH access.

Security changes prepared in the project:

- trusted reverse proxy support through `ProxyFix`;
- hardened production `.env.example`;
- hardened Nginx deployment template;
- Nginx rate-limit snippet;
- hardened Gunicorn systemd unit;
- regression tests for the security-related configuration.

Full audit file in the project root:

```text
SECURITY_AUDIT_2026-07-29.md
```

