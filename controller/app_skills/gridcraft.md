# GridCraft operating skill

You edit the user's live workbook. Ground operations in the active worksheet and
explicit A1 cell/range addresses. Use these verified recipes when available in
the connected registry. Discover contracts for unfamiliar commands.

- Inspect the workbook/sheets and preserve worksheet identity across requests.
- Read before reasoning about values: `cell.get {"cell": "B2", "sheet": SHEET}`
  or `sheet.read {"range": "A1:D10", "sheet": SHEET, "formulas": true}`.
  Returned data, not a screenshot hash, is the basis for calculations.
- Write text, numbers or formulas using `cell.set {"cell": "B2", "input": VALUE,
  "sheet": SHEET}`. Formula input starts with `=`, e.g. `=SUM(A1:A9)`.
  Do not substitute displayed results for formulas unless requested.
- Select a range using `selection.set {"range": "A1:B2", "sheet": SHEET}`.
- Bold explicitly: `home.bold {"range": "A1:B2", "on": true}`. Omitting on
  toggles; explicit desired state is preferable for repeatable formatting.
- Distinguish cell content, formatting, range selection, sheet structure and
  workbook-wide changes. Look up precise contracts for inserts, deletes, sorting,
  formulas and formatting before applying unfamiliar structural operations.
- Verify edits by reading the same cells, including formulas where relevant.
  Structural edits must verify row/column/sheet identities and affected ranges.
- Use look for visual layout questions; use structured reads for numeric data.
- Use command_describe for complete types, defaults and units. Respect disabled
  commands. Do not guess parameters or retry the same failed command blindly.
- Save only when requested; finish with done and an accurate outcome summary.
