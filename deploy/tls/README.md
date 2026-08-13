# TLS material

Place the deployment certificate files here on the host:

- `fullchain.pem`
- `privkey.pem`

They are mounted read-only into Nginx and are ignored by Git. Use certificates issued for `APP_DOMAIN` by your ACME/certificate-management workflow. Never commit a private key to the repository.
