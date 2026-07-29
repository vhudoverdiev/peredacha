# Peredacha CRM overview

Peredacha CRM is a web application for managing premises handover workflows.

Main functions:

- loading object data from Excel files;
- storing apartments, commercial premises, owners and phone contacts;
- managing remarks, statuses and responsible employees;
- assigning tasks to workers;
- tracking materials and write-offs;
- managing glass measurements and glass orders;
- generating Excel exports and working documents;
- keeping logs of synchronization, deletion actions and security events.

Current project stack:

- Ubuntu on Selectel VDS;
- Python;
- Flask;
- SQLAlchemy;
- Flask-Login;
- Flask-WTF CSRF protection;
- Gunicorn;
- Nginx;
- Let's Encrypt HTTPS;
- SQLite in the current test stage, with PostgreSQL recommended for production.

Current test server configuration:

- Ubuntu 24.04 LTS 64-bit;
- Selectel VDS, Moscow region;
- 2 vCPU;
- 2 GB RAM;
- 40 GB disk;
- public IP shown in the Selectel panel: `135.106.176.36`.

For the test stage, the expected access is approximately 10 users. This is enough to verify login under personal accounts, task assignment, remarks, statuses, Excel import/export, materials, measurements and reports.

