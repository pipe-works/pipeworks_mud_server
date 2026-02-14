Admin Web UI Deployment (mTLS)
==============================

This guide explains how to expose the admin Web UI securely using mutual TLS (mTLS).
It assumes you already have a running PipeWorks MUD API server and Nginx on the host.

Overview
--------

- The admin UI is served by the same FastAPI app as the public API.
- The admin UI uses same-origin requests, so CORS is not required for admin access.
- mTLS ensures only clients with a valid certificate can access the admin domain.
- The public API domain should block `/admin` to prevent bypassing mTLS.

Path Conventions
----------------

This guide uses generic path placeholders. Replace with your distro-specific paths.

- ``<NGINX_CONF_DIR>``: Nginx config root (example: ``/etc/nginx``)
- ``<NGINX_SITES_AVAILABLE>``: site configs (example: ``/etc/nginx/sites-available``)
- ``<NGINX_SITES_ENABLED>``: enabled sites (example: ``/etc/nginx/sites-enabled``)
- ``<SYSTEMD_UNIT_DIR>``: systemd units (example: ``/etc/systemd/system``)
- ``<APP_ROOT>``: repo root on server (example: ``/opt/pipeworks_mud_server``)

Prerequisites
-------------

- A DNS record for ``admin.<your-domain>`` pointing at your server.
- Nginx installed and running.
- Certbot installed for TLS certificates.
- Admin UI enabled in the app (default is ``/admin`` on the API server).

Step 1: Create an Internal CA and Client Certificates
-----------------------------------------------------

Create a local CA and issue client certs. Run on the server:

.. code-block:: bash

   sudo mkdir -p <NGINX_CONF_DIR>/mtls
   cd <NGINX_CONF_DIR>/mtls

   # CA
   sudo openssl genrsa -out ca.key 4096
   sudo openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
     -out ca.crt -subj "/CN=PipeWorks Admin CA"

   # Client cert (desktop)
   sudo openssl genrsa -out admin-desktop.key 2048
   sudo openssl req -new -key admin-desktop.key -out admin-desktop.csr \
     -subj "/CN=admin-desktop"
   sudo openssl x509 -req -in admin-desktop.csr -CA ca.crt -CAkey ca.key \
     -CAcreateserial -out admin-desktop.crt -days 825 -sha256

   # Client cert (laptop)
   sudo openssl genrsa -out admin-laptop.key 2048
   sudo openssl req -new -key admin-laptop.key -out admin-laptop.csr \
     -subj "/CN=admin-laptop"
   sudo openssl x509 -req -in admin-laptop.csr -CA ca.crt -CAkey ca.key \
     -CAcreateserial -out admin-laptop.crt -days 825 -sha256

   # Export P12 bundles for browser import
   sudo openssl pkcs12 -export -out admin-desktop.p12 \
     -inkey admin-desktop.key -in admin-desktop.crt -certfile ca.crt
   sudo openssl pkcs12 -export -out admin-laptop.p12 \
     -inkey admin-laptop.key -in admin-laptop.crt -certfile ca.crt

Keep ``ca.key`` private. If it is compromised, revoke and reissue all certs.

Step 2: Install Client Certificates
-----------------------------------

macOS (Chrome/Safari):

- Import the ``.p12`` into the **login** keychain via Keychain Access.
- Restart the browser if it does not prompt for a certificate.

Firefox:

- Settings → Privacy & Security → Certificates → View Certificates → Import.

Windows:

- Double-click the ``.p12`` and import into the **Current User** certificate store.

Linux (Chrome/Chromium):

- Import the ``.p12`` into the NSS database for your profile.

Step 3: Obtain TLS Certificate for the Admin Domain
---------------------------------------------------

Issue a TLS cert for ``admin.<your-domain>``.

If your new vhost references a cert that does not exist yet, use standalone mode:

.. code-block:: bash

   sudo systemctl stop nginx
   sudo certbot certonly --standalone -d admin.<your-domain>
   sudo systemctl start nginx

Otherwise, you can use the Nginx plugin:

.. code-block:: bash

   sudo certbot --nginx -d admin.<your-domain>

Step 4: Configure the Admin Vhost (mTLS)
----------------------------------------

Create ``<NGINX_SITES_AVAILABLE>/admin.<your-domain>``:

.. code-block:: nginx

   server {
       server_name admin.<your-domain>;
       http2 on;

       access_log /var/log/nginx/admin.<your-domain>.access.log combined;
       error_log  /var/log/nginx/admin.<your-domain>.error.log warn;

       listen 443 ssl;
       ssl_certificate /etc/letsencrypt/live/admin.<your-domain>/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/admin.<your-domain>/privkey.pem;
       include /etc/letsencrypt/options-ssl-nginx.conf;
       ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

       ssl_client_certificate <NGINX_CONF_DIR>/mtls/ca.crt;
       ssl_verify_client on;

       add_header X-Content-Type-Options "nosniff" always;
       add_header X-Frame-Options "DENY" always;
       add_header X-XSS-Protection "1; mode=block" always;
       add_header Referrer-Policy "strict-origin-when-cross-origin" always;
       add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
       server_tokens off;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_http_version 1.1;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_set_header X-Forwarded-Host $host;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_connect_timeout 60s;
           proxy_send_timeout 60s;
           proxy_read_timeout 60s;
       }
   }

   server {
       listen 80;
       listen [::]:80;
       server_name admin.<your-domain>;

       if ($host = admin.<your-domain>) {
           return 301 https://$host$request_uri;
       }

       return 404;
   }

Enable the site and reload Nginx:

.. code-block:: bash

   sudo ln -s <NGINX_SITES_AVAILABLE>/admin.<your-domain> <NGINX_SITES_ENABLED>/admin.<your-domain>
   sudo nginx -t
   sudo systemctl reload nginx

Step 5: Block /admin on the Public API Domain
---------------------------------------------

Add a block near the top of your API vhost:

.. code-block:: nginx

   location ^~ /admin {
       return 404;
   }

This prevents access to admin endpoints on the public API domain.

Step 6: Bind the API Backend to Localhost
-----------------------------------------

Option A: systemd overrides (recommended):

.. code-block:: ini

   [Service]
   Environment=MUD_HOST=127.0.0.1
   Environment=MUD_PORT=8000

Restart the service:

.. code-block:: bash

   sudo systemctl daemon-reload
   sudo systemctl restart pipeworks-api.service

Option B: edit ``config/server.ini``:

.. code-block:: ini

   [server]
   host = 127.0.0.1
   port = 8000

Step 7: Validate
----------------

Without a client cert (should fail):

.. code-block:: bash

   curl -vk https://admin.<your-domain>/admin

With a client cert (should succeed):

.. code-block:: bash

   curl --cert ~/Downloads/admin-desktop.p12:EXPORT_PASSWORD --cert-type P12 -I \
     https://admin.<your-domain>/admin

Public API domain should block admin:

.. code-block:: bash

   curl -I https://api.<your-domain>/admin

Renewal and Rotation
--------------------

- Let’s Encrypt certificates renew automatically via Certbot.
- Client certs should be rotated periodically or on device loss.
- If the CA private key is compromised, reissue the CA and all client certs.

Troubleshooting
---------------

Common issues:

- ``400 No required SSL certificate was sent`` means the browser did not provide a client cert.
- ``curl`` works but browser does not prompt: restart the browser or clear certificate selection.
- Certbot fails when a vhost references a non-existent cert: use standalone mode with Nginx stopped.
