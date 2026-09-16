# Authentication and RBAC

RCA Agent supports optional local authentication backed by MySQL. Authentication is disabled by default so existing installations can upgrade without being locked out.

## Roles

| Role | Read data | Run RCA / diagnostics | Test connections | Change Applications / Connections | Manage users |
| --- | --- | --- | --- | --- | --- |
| Admin | Yes | Yes | Yes | Yes | Yes |
| Investigator | Yes | Yes | Yes | No | No |
| Read-only | Yes | No | No | No | No |

Server-side middleware enforces these permissions. UI visibility is only a convenience and is not the security boundary.

The Grafana webhook remains an integration endpoint and does not use a human user session. It should be exposed only through the intended ingress/network path; a dedicated webhook secret can be added independently.

## Helm

Authentication remains off unless explicitly enabled:

```yaml
auth:
  enabled: true
  bootstrapAdminUsername: admin
  sessionTtlSeconds: 28800
  cookieSecure: true
```

When the chart manages its bootstrap Secret, it generates and preserves:

- a dedicated Fernet session key (`rca-auth-key`);
- a random first-admin password (`bootstrap-admin-password`).

On the first authenticated start, RCA Agent creates the bootstrap administrator only when the `users` table is empty. Once any user exists, bootstrap credentials are ignored.

To retrieve the generated bootstrap password, first identify the chart Secret, then read only that key. For the default release name:

```bash
kubectl -n rca-agent get secret rca-agent-bootstrap \
  -o jsonpath='{.data.bootstrap-admin-password}' | base64 -d; echo
```

If `secrets.existingSecret` is configured, that Secret must contain the keys selected by `secrets.keys.authKey` and `secrets.keys.bootstrapAdminPassword` before authentication is enabled.

Use `auth.cookieSecure: true` when RCA Agent is served over HTTPS. Keep it false only for an HTTP-only local/lab deployment.

## Docker Compose

Generate a dedicated authentication Fernet key separately from `RCA_MASTER_KEY`:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Then set in `.env.docker`:

```dotenv
AUTH_ENABLED=true
RCA_AUTH_KEY=<generated-fernet-key>
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=<strong-initial-password>
AUTH_SESSION_TTL_SECONDS=28800
AUTH_COOKIE_SECURE=false
```

`RCA_MASTER_KEY` encrypts provider credentials stored in MySQL. `RCA_AUTH_KEY` protects login session tokens. They must be different keys.

## Sessions

Successful login creates an HttpOnly `rca_session` cookie using `SameSite=Lax`. API clients may alternatively send the same session token as:

```text
Authorization: Bearer <session-token>
```

The token stores only the user ID. RCA Agent reloads the user from MySQL on every authenticated request, so disabling a user or changing their role takes effect without waiting for the session token to expire.

## User administration

Admins can manage users from the **Users** page in the web UI or through:

- `GET /api/v1/auth/users`
- `POST /api/v1/auth/users`
- `PATCH /api/v1/auth/users/{id}`
- `DELETE /api/v1/auth/users/{id}`

RCA Agent prevents deleting, disabling, or demoting the last enabled administrator.
