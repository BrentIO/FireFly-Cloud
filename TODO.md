# FireFly-Cloud To-Do

## Backlog

- [ ] **Optimistic delete status** — When a user deletes a firmware record, the UI sends a delete request to S3, which is asynchronous. The table row remains visible and stale during the delay. As soon as the user confirms deletion, the record's `release_status` should be updated to `DELETING` in the UI (optimistically, before the S3 call completes) so the row reflects the pending state immediately and disappears from filtered views that exclude `DELETING` records.
