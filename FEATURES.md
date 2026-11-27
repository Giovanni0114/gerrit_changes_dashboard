## Gerrit HTTP connection configuration

Add optional per-instance `http_*` settings for future Gerrit REST API clients:
an explicit base URL, optional basic-auth credentials, request timeout, and TLS
verification. Parse them into a typed immutable value on `GerritInstance` with
strict startup validation and safe defaults.

This feature adds configuration infrastructure only. It makes no HTTP requests,
does not replace SSH operations, and does not change the `ci_errors` plugin.

Full spec in `spec/features/026-gerrit-http-config/spec.md`.

---

## Navigation and selecting using arrows

If the arrow is used when index is expected:
  - symbol `*` appears next to the first index in list of changes
  - arrows `up` and `down` navigates this symbol on the list of chanegs, symbol
  `*` should move.
  - it should rotate, meaning when it's on the first change (on top of a list)
  and arrow `up` is pressed, it should move to the last one. (ofc also in other way)
  - when `<space>` is pressed, the change should be marked as **selected**.
  - selecting a already selected change unselects it
  - selected change should be makred with bolding the index number
  - when pressing `<enter>` all selected changes should be passed for
  operatons, as it would if selected with notation
  - pressing `<esc>` unselects all changes and abort the operaton, as normally would
  - changes should never be selected outside of chosing index input

---

## Add spinner and countdown to header

Currently header shows just time of refreshed, and this is often misleading. I
want to add some sort of rich `Spinner` to indicate when operations are running
in the background. 
