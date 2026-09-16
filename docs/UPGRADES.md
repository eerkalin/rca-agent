# Upgrade and database compatibility policy

RCA Agent treats the MySQL schema as a versioned part of the application. Existing installations must be upgradeable without manually creating tables or columns.

## Rules

1. **Alembic is the only schema change mechanism.**
   Every table, column, index, foreign key or schema-level change must be represented by a new migration in `backend/migrations/versions/`.

2. **Deployments migrate before the API starts.**
   The Helm chart migration initContainer and Docker Compose migration container run:

   ```bash
   alembic upgrade head
   ```

   The API starts only after migrations complete successfully.

3. **The backend verifies schema compatibility at startup.**
   The running database revision must match the Alembic head shipped with the image. A stale or unmigrated database causes startup to fail with a clear revision mismatch instead of allowing partially working code.

4. **Schema changes are expand-first.**
   Prefer additive changes before destructive changes:

   - add the new column/table/key;
   - migrate or backfill existing data;
   - make new code understand old and new representations when necessary;
   - switch writes to the new representation;
   - remove legacy fields only in a later release after rollback compatibility is no longer required.

5. **JSON configuration is versioned data too.**
   Changes such as `namespace` -> `namespaces`, provider identifiers or tool configuration keys require data migration and/or a compatibility reader. Existing Applications must not require manual reconfiguration after an upgrade.

6. **Secrets and persistent data survive Helm upgrades.**
   Helm upgrades must reuse the existing bootstrap Secret and MySQL PVC. An image upgrade must not rotate the RCA master key, database password or delete persistent data.

7. **Rollback safety is considered before destructive migrations.**
   A migration should not immediately make the database unreadable by the previous application image. Destructive cleanup is deferred to a later release whenever practical.

8. **Risky migrations require a backup plan.**
   Before type rewrites, large backfills, destructive cleanup or other irreversible changes, document a MySQL backup/restore procedure and expected migration duration.

## CI coverage

CI validates two paths:

### Fresh installation

```text
empty MySQL
  -> alembic upgrade head
  -> schema revision check
  -> application import
```

### Upgrade from the previous supported schema

```text
previous Alembic revision
  -> confirm backend detects schema as stale
  -> alembic upgrade head
  -> confirm schema matches current head
```

When a new migration is added, the `upgrade-compatibility` CI job must be updated so its starting revision represents the previous supported release schema.

## Release checklist for schema changes

- create a new Alembic revision; never rewrite an already released revision;
- define explicit `down_revision` so the migration chain remains linear unless branching is intentional;
- include data backfill where required;
- preserve legacy reads during the transition when rollback matters;
- add migration tests for existing data, not just empty tables;
- confirm `alembic upgrade head` succeeds from the previous release revision;
- confirm the current backend rejects a deliberately stale schema;
- document any backup requirement or non-trivial migration duration;
- do not remove legacy schema/config until the agreed deprecation window has passed.

## Operational upgrade flow

For Helm deployments the expected flow is:

```text
helm upgrade
  -> existing MySQL PVC remains mounted
  -> existing bootstrap Secret is reused
  -> migration initContainer waits for MySQL
  -> alembic upgrade head
  -> RCA Agent starts
  -> startup schema guard verifies DB == packaged Alembic head
```

If migration fails, the new API Pod must not become ready. Investigate and fix the migration instead of manually altering production tables.
