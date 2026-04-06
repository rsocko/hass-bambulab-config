# Spoolman Purchase Import

This workflow turns a purchase confirmation into one new Spoolman spool record per physical spool while reusing the filament records that already exist in the catalog.

## Files

- Script: `tools/spoolman/create_spools_from_purchase.py`
- Example order: `tools/spoolman/orders/bambu_lab_order_2026-04-05.json`
- Future source option: pasted plain-text email/order summary via `--email-summary-file` or `--email-summary-stdin`

## Purchase Inventory: 2026-04-05

| Article | Filament ID | Name | Material | Qty | Line Total | Per-Spool Prices |
| --- | ---: | --- | --- | ---: | ---: | --- |
| 10101 | 5 | Black | PLA | 4 | $51.97 | $12.99, $12.99, $12.99, $13.00 |
| 10601 | 2 | Blue | PLA | 1 | $12.99 | $12.99 |
| 10502 | 4 | Mistletoe Green | PLA | 1 | $12.99 | $12.99 |
| 10102 | 19 | Silver | PLA | 1 | $12.99 | $12.99 |
| 10205 | 59 | Maroon Red | PLA | 1 | $12.99 | $12.99 |
| 11101 | 8 | Matte Charcoal | PLA | 3 | $38.98 | $12.99, $12.99, $13.00 |
| 11102 | 12 | Matte Ash Gray | PLA | 1 | $12.99 | $12.99 |

Total spools: 12

Total paid: $155.90

## Matching Logic

The importer uses the live Spoolman API and applies the following checks for each line item:

1. Search `GET /filament` by exact `article_number` using a quoted query so partial matches do not slip through.
2. Require exactly one result.
3. Validate that the resolved filament's vendor, material, and name match the order definition.
4. Validate that the resolved filament ID matches the expected ID recorded in the order file.

This keeps the import tied to the actual Spoolman catalog and fails fast if a filament was renamed, duplicated, or remapped.

## Price Allocation Logic

Each order line stores the discounted line total, not the original unit price.

When a line has multiple spools, the script:

1. Converts the discounted line total to cents.
2. Splits it evenly across the quantity.
3. Floors to whole cents.
4. Distributes any leftover pennies to the last spools in that line so the created spool prices add back up to the exact amount paid.

Examples:

- `51.97 / 4` becomes `12.99, 12.99, 12.99, 13.00`
- `38.98 / 3` becomes `12.99, 12.99, 13.00`

## Fields Set On Each New Spool

- `location`: `Ordered`
- `price`: discounted per-spool purchase price
- `extra.purchase_date`: runtime timestamp in UTC unless explicitly overridden
- `extra.purchased_from`: `Bambu Lab`
- `extra.spool_type`: `Refill`
- `extra.sealed`: `true` by default for newly purchased spools

`purchase_date`, `purchased_from`, `spool_type`, and `sealed` are written using Spoolman's JSON-encoded extra field format.

## Optional Filament Purchase-Qty Decrement

The script can also decrement filament-level `extra.purchase_qty` by the quantity you just bought.

Rules:

- The decrement is applied once per filament line item quantity.
- If multiple lines ever resolve to the same filament, quantities are summed before patching.
- The value is clamped at `0`, so it will never go negative.
- Filament extra fields are patched by merging the current `extra` object and only changing `purchase_qty`, because Spoolman's filament PATCH replaces the full `extra` payload when supplied.

## Usage

There are now three supported execution modes:

- Create only: create new spool records and leave filament `purchase_qty` unchanged.
- Complete purchase import: create new spool records and decrement filament `purchase_qty` in the same run.
- Decrement only: adjust filament `purchase_qty` without creating any spool records.

Dry run:

```powershell
python tools/spoolman/create_spools_from_purchase.py --order-file tools/spoolman/orders/bambu_lab_order_2026-04-05.json
```

Dry run from a pasted email text file:

```powershell
python tools/spoolman/create_spools_from_purchase.py --email-summary-file order-email.txt --base-url http://spoolman.socko.us/api/v1
```

Dry run from clipboard/stdin and also write a canonical JSON order file:

```powershell
Get-Clipboard | python tools/spoolman/create_spools_from_purchase.py --email-summary-stdin --base-url http://spoolman.socko.us/api/v1 --write-order-file tools/spoolman/orders/bambu_lab_next_order.json
```

Apply the import:

```powershell
python tools/spoolman/create_spools_from_purchase.py --order-file tools/spoolman/orders/bambu_lab_order_2026-04-05.json --apply
```

Apply the complete purchase import convenience mode:

```powershell
python tools/spoolman/create_spools_from_purchase.py --order-file tools/spoolman/orders/bambu_lab_order_2026-04-05.json --complete-purchase-import --apply
```

Apply the import and also decrement `purchase_qty` with the explicit separate flag:

```powershell
python tools/spoolman/create_spools_from_purchase.py --order-file tools/spoolman/orders/bambu_lab_order_2026-04-05.json --decrement-purchase-qty --apply
```

Only decrement `purchase_qty` without creating any spools:

```powershell
python tools/spoolman/create_spools_from_purchase.py --order-file tools/spoolman/orders/bambu_lab_order_2026-04-05.json --decrement-purchase-qty-only --apply
```

Apply directly from clipboard/stdin:

```powershell
Get-Clipboard | python tools/spoolman/create_spools_from_purchase.py --email-summary-stdin --base-url http://spoolman.socko.us/api/v1 --apply
```

Override the purchase timestamp:

```powershell
python tools/spoolman/create_spools_from_purchase.py --order-file tools/spoolman/orders/bambu_lab_order_2026-04-05.json --purchase-date 2026-04-05T18:00:00Z --apply
```

## Repeat For Future Orders

1. Copy the order-summary text from the email.
2. Either paste it into a text file and use `--email-summary-file`, or pipe the clipboard with `Get-Clipboard | ... --email-summary-stdin`.
3. Run a dry run first and confirm the resolved filament IDs and allocated per-spool prices.
4. Optionally save the resolved canonical JSON with `--write-order-file` so the exact import plan is preserved in the repo.
5. Run again with `--apply` once the plan looks correct.

## Expected Email Format

The parser currently expects the Bambu Lab order-summary pattern shown below:

```text
PLA Basic x 4
Black (10101) / Refill / 1kg
Filament Bulk Sale -$27.99
$51.97
$79.96
```

Important parsing behavior:

- The first `Product x Qty` line starts a new order item.
- The next line must contain `Name (Article) / Spool Type / Weight`.
- Discount lines such as `Filament Bulk Sale -$27.99` are ignored.
- The first positive dollar amount after the detail line is treated as the discounted line total.
- The struck/original price line is ignored.

## Notes

- The script uses the base URL from the order file by default but also accepts `--base-url`.
- If your Spoolman extra field choices change, the script validates them before creating anything.
- The parser derives material from the first token of the product line, so `PLA Basic` and `PLA Matte` both validate against material `PLA`.
- `--write-order-file` is the safest repeatable handoff because it captures the resolved filament IDs after validation.
- `--complete-purchase-import` is the convenience flag for the normal all-in-one workflow.
- `--decrement-purchase-qty-only` is the recovery path to use if spools were already created and you only want to adjust the filament reorder counts afterward.