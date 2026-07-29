# Deployment

Production deployment target:

- Ubuntu server;
- Nginx as public HTTPS reverse proxy;
- Gunicorn as Python WSGI server;
- Flask application under `/opt/peredacha`;
- systemd service/socket for Gunicorn;
- Let's Encrypt certificates for HTTPS.

Recommended deployment flow:

```bash
cd /opt/peredacha
git pull

python3 -m venv venv
./venv/bin/pip install -r requirements.txt

sudo cp deploy/nginx-rate-limit.conf /etc/nginx/conf.d/peredacha-rate-limit.conf
sudo cp deploy/nginx-akvilon-peredacha.conf /etc/nginx/sites-available/peredacha.conf
sudo ln -sf /etc/nginx/sites-available/peredacha.conf /etc/nginx/sites-enabled/peredacha.conf
sudo nginx -t
sudo systemctl reload nginx

sudo cp deploy/gunicorn.service /etc/systemd/system/gunicorn.service
sudo cp deploy/gunicorn.socket /etc/systemd/system/gunicorn.socket
sudo systemctl daemon-reload
sudo systemctl restart gunicorn.socket gunicorn.service
```

Gunicorn should run as an unprivileged user, currently `www-data` in the deployment config.

Nginx should be the only public entry point for the Flask application. Direct Flask/Gunicorn ports such as `5000` or `8080` should not be exposed to the internet.

Database recommendation:

- current test stage may use SQLite;
- production should use PostgreSQL bound to `127.0.0.1` or a private network only;
- PostgreSQL port `5432` must not be publicly accessible.

