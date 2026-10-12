# Flow: Agent Edit Verify

> Last updated by: swaibian-architect-no-reviews, 2026-10-11

```mermaid
flowchart TD
    A[craft_snapshot] --> B[craft_run / act]
    B --> C[craft_look]
    C --> D[craft_assert]
    D -->|pass| E[craft_record]
    D -->|fail| F[craft_restore]
    F --> B
```

| Step | Description |
|:-----|:------------|
| Snapshot | File-level checkpoint before destructive work |
| Act | Guarded command execution |
| Look | Unified render of the result |
| Assert | Structural (default) / visual postconditions |
| Record | Claim + evidence, rejects unbacked "measured" claims |
| Restore | Rollback path on assertion failure |

Populated by the TC's last implementation issue.
