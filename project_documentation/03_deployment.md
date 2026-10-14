# Deployment

Production deployment target:

- Ubuntu server;
- Nginx as public HTTPS reverse proxy;
- Gunicorn as Python WSGI server;
- Flask application under `/opt/peredacha`;
- user-level systemd service for Gunicorn;
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

mkdir -p ~/.config/systemd/user
cp deploy/gunicorn.service ~/.config/systemd/user/gunicorn.service
systemctl --user daemon-reload
systemctl --user enable --now gunicorn.service
```

Gunicorn runs as the ordinary user who installed the user-level service. It listens only on `127.0.0.1:8000`.

Nginx should be the only public entry point for the Flask application. Direct Flask/Gunicorn ports such as `5000` or `8080` should not be exposed to the internet.

Database recommendation:

- current test stage may use SQLite;
- production should use MariaDB bound to `127.0.0.1` or a private network only;
- MariaDB port `3306` must not be publicly accessible.
