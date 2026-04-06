"""Create Spoolman spools from a purchase order definition.

This utility is designed for repeatable purchase imports where the filament
already exists in Spoolman and new spool records need to be created in bulk.
It resolves each line item against the live Spoolman filament catalog by exact
article number, validates the expected filament ID, then creates one spool per
unit with the requested metadata.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib import error, parse, request

JSON_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}


@dataclass(frozen=True)
class OrderLine:
    vendor: str
    material: str
    name: str
    article_number: str
    quantity: int
    line_total: Decimal
    spool_type: str
    expected_filament_id: int | None = None


@dataclass(frozen=True)
class OrderConfig:
    base_url: str
    order_name: str
    location: str
    purchased_from: str
    purchase_date_setting: str
    set_sealed: bool
    lines: list[OrderLine]


@dataclass(frozen=True)
class FilamentAdjustment:
    filament_id: int
    article_number: str
    name: str
    decremented_by: int
    previous_purchase_qty: int
    new_purchase_qty: int
    payload: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--order-file",
        type=Path,
        help="Path to a JSON order definition file.",
    )
    parser.add_argument(
        "--email-summary-file",
        type=Path,
        help="Path to a plain-text pasted email/order summary.",
    )
    parser.add_argument(
        "--email-summary-stdin",
        action="store_true",
        help="Read the plain-text pasted email/order summary from standard input.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Spoolman API base URL. Defaults to the value in the order file.",
    )
    parser.add_argument(
        "--order-name",
        default=None,
        help="Optional order name override. Useful when importing from pasted email text.",
    )
    parser.add_argument(
        "--location",
        default=None,
        help="Optional location override. Defaults to Ordered.",
    )
    parser.add_argument(
        "--purchased-from",
        default=None,
        help="Optional purchase-source override. Defaults to Bambu Lab.",
    )
    parser.add_argument(
        "--filament-vendor",
        default=None,
        help="Vendor name to validate against existing filament records. Defaults to the purchase source.",
    )
    parser.add_argument(
        "--purchase-date",
        default="NOW",
        help="ISO 8601 timestamp to store as the purchase date. Default: NOW (UTC at runtime).",
    )
    parser.add_argument(
        "--write-order-file",
        type=Path,
        help="Write the canonical JSON order definition used for import to this path.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create spools. Without this flag the script performs a dry run.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds. Default: 30.",
    )
    parser.add_argument(
        "--set-sealed",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override whether new spools are marked sealed in Spoolman extra fields.",
    )
    parser.add_argument(
        "--decrement-purchase-qty",
        action="store_true",
        help="After resolving the order, decrement filament extra.purchase_qty by the purchased quantity.",
    )
    parser.add_argument(
        "--complete-purchase-import",
        action="store_true",
        help="Convenience mode: create spools and decrement filament extra.purchase_qty in one run.",
    )
    parser.add_argument(
        "--decrement-purchase-qty-only",
        action="store_true",
        help="Do not create spools. Only run the filament purchase_qty decrement step.",
    )
    args = parser.parse_args()

    source_count = sum(
        1
        for value in (args.order_file, args.email_summary_file, args.email_summary_stdin)
        if value
    )
    if source_count != 1:
        parser.error("Specify exactly one of --order-file, --email-summary-file, or --email-summary-stdin")

    if args.complete_purchase_import and args.decrement_purchase_qty_only:
        parser.error("--complete-purchase-import cannot be combined with --decrement-purchase-qty-only")

    if args.complete_purchase_import:
        args.decrement_purchase_qty = True

    if args.decrement_purchase_qty_only:
        args.decrement_purchase_qty = True

    return args


def http_json(method: str, url: str, timeout: float, payload: dict[str, Any] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=JSON_HEADERS, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return None
            return json.loads(raw)
    except error.HTTPError as exc:  # pragma: no cover - runtime error path
        response_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {response_body}") from exc
    except error.URLError as exc:  # pragma: no cover - runtime error path
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def normalize_base_url(raw: str) -> str:
    return raw.rstrip("/")


def load_order_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Order file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Order file is not valid JSON: {path}: {exc}") from exc


def load_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"Email summary file not found: {path}") from exc


def load_stdin_text() -> str:
    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("No email summary text was provided on stdin")
    return raw


def parse_decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise SystemExit(f"Invalid decimal for {field_name}: {value}") from exc


def load_order_lines(raw_lines: list[dict[str, Any]]) -> list[OrderLine]:
    lines: list[OrderLine] = []
    for index, item in enumerate(raw_lines, start=1):
        try:
            quantity = int(item["quantity"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit(f"Item #{index} has an invalid quantity") from exc
        if quantity <= 0:
            raise SystemExit(f"Item #{index} must have quantity > 0")

        lines.append(
            OrderLine(
                vendor=str(item["vendor"]),
                material=str(item["material"]),
                name=str(item["name"]),
                article_number=str(item["article_number"]),
                quantity=quantity,
                line_total=parse_decimal(item["line_total"], f"items[{index}].line_total"),
                spool_type=str(item.get("spool_type") or "Refill"),
                expected_filament_id=(None if item.get("expected_filament_id") is None else int(item["expected_filament_id"])),
            )
        )
    return lines


def parse_order_summary_text(raw_text: str, vendor: str) -> list[OrderLine]:
    text = raw_text.replace("\r\n", "\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    parsed_lines: list[OrderLine] = []
    index = 0
    while index < len(lines):
        header_match = re.fullmatch(r"(?P<product>.+?)\s+x\s+(?P<quantity>\d+)", lines[index])
        if not header_match:
            index += 1
            continue

        if index + 1 >= len(lines):
            raise SystemExit(f"Missing detail line after: {lines[index]}")

        detail_line = lines[index + 1]
        detail_match = re.fullmatch(
            r"(?P<name>.+?)\s*\((?P<article>\d+)\)\s*/\s*(?P<spool_type>[^/]+?)\s*/\s*(?P<weight>.+)",
            detail_line,
        )
        if not detail_match:
            raise SystemExit(f"Could not parse detail line: {detail_line}")

        product_name = header_match.group("product").strip()
        material = product_name.split()[0].strip()
        quantity = int(header_match.group("quantity"))

        price_index = index + 2
        discounted_total: Decimal | None = None
        while price_index < len(lines):
            if re.fullmatch(r".+\s+x\s+\d+", lines[price_index]):
                break

            money_match = re.fullmatch(r"\$(\d+(?:\.\d{2})?)", lines[price_index])
            if money_match and discounted_total is None:
                discounted_total = parse_decimal(money_match.group(1), f"line total for article {detail_match.group('article')}")
                break

            price_index += 1

        if discounted_total is None:
            raise SystemExit(f"Could not find discounted line total for article {detail_match.group('article')}")

        parsed_lines.append(
            OrderLine(
                vendor=vendor,
                material=material,
                name=detail_match.group("name").strip(),
                article_number=detail_match.group("article"),
                quantity=quantity,
                line_total=discounted_total,
                spool_type=detail_match.group("spool_type").strip(),
            )
        )
        index = price_index + 1

    if not parsed_lines:
        raise SystemExit("No order lines were parsed from the supplied email summary text")

    return parsed_lines


def resolve_purchase_date(raw_value: str) -> str:
    if raw_value.upper() == "NOW":
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"Invalid --purchase-date value: {raw_value}") from exc

    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_order_config(args: argparse.Namespace) -> OrderConfig:
    if args.order_file:
        order_data = load_order_file(args.order_file)
        base_url = normalize_base_url(str(args.base_url or order_data.get("base_url") or ""))
        if not base_url:
            raise SystemExit("A Spoolman API base URL is required via --base-url or the order file")

        defaults = order_data.get("defaults") or {}
        location = str(args.location or defaults.get("location") or "Ordered")
        purchased_from = str(args.purchased_from or defaults.get("purchased_from") or "Bambu Lab")
        purchase_date_setting = args.purchase_date if args.purchase_date != "NOW" else str(defaults.get("purchase_date") or "NOW")
        set_sealed = bool(defaults.get("set_sealed", True) if args.set_sealed is None else args.set_sealed)
        order_name = str(args.order_name or order_data.get("order_name") or args.order_file.stem)
        lines = load_order_lines(order_data.get("items") or [])
        return OrderConfig(
            base_url=base_url,
            order_name=order_name,
            location=location,
            purchased_from=purchased_from,
            purchase_date_setting=purchase_date_setting,
            set_sealed=set_sealed,
            lines=lines,
        )

    raw_text = load_text_file(args.email_summary_file) if args.email_summary_file else load_stdin_text()
    purchased_from = str(args.purchased_from or "Bambu Lab")
    vendor = str(args.filament_vendor or purchased_from)
    base_url = normalize_base_url(str(args.base_url or ""))
    if not base_url:
        raise SystemExit("A Spoolman API base URL is required when importing from email text")

    order_name = str(args.order_name or f"{purchased_from} purchase {datetime.now(timezone.utc).date().isoformat()}")
    location = str(args.location or "Ordered")
    purchase_date_setting = str(args.purchase_date or "NOW")
    set_sealed = bool(True if args.set_sealed is None else args.set_sealed)
    lines = parse_order_summary_text(raw_text, vendor=vendor)
    return OrderConfig(
        base_url=base_url,
        order_name=order_name,
        location=location,
        purchased_from=purchased_from,
        purchase_date_setting=purchase_date_setting,
        set_sealed=set_sealed,
        lines=lines,
    )


def allocate_prices(line_total: Decimal, quantity: int) -> list[Decimal]:
    total_cents = int((line_total * 100).to_integral_value())
    base_cents, remainder = divmod(total_cents, quantity)
    cents = [base_cents] * quantity
    for offset in range(remainder):
        cents[-(offset + 1)] += 1
    return [Decimal(value) / Decimal("100") for value in cents]


def encode_extra_value(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def fetch_spool_extra_fields(base_url: str, timeout: float) -> dict[str, dict[str, Any]]:
    fields = http_json("GET", f"{base_url}/field/spool", timeout)
    if not isinstance(fields, list):
        raise SystemExit("Unexpected response from /field/spool")
    return {str(field["key"]): field for field in fields}


def fetch_filament_extra_fields(base_url: str, timeout: float) -> dict[str, dict[str, Any]]:
    fields = http_json("GET", f"{base_url}/field/filament", timeout)
    if not isinstance(fields, list):
        raise SystemExit("Unexpected response from /field/filament")
    return {str(field["key"]): field for field in fields}


def validate_choice_field(field: dict[str, Any], value: str, field_key: str) -> None:
    choices = field.get("choices") or []
    if choices and value not in choices:
        available = ", ".join(str(choice) for choice in choices)
        raise SystemExit(f"Value '{value}' is not valid for spool extra field '{field_key}'. Choices: {available}")


def validate_required_extra_fields(fields: dict[str, dict[str, Any]], purchased_from: str, spool_types: set[str], set_sealed: bool) -> None:
    required_keys = {"purchase_date", "purchased_from", "spool_type"}
    if set_sealed:
        required_keys.add("sealed")

    missing = sorted(required_keys - set(fields))
    if missing:
        raise SystemExit(f"Spoolman is missing required spool extra fields: {', '.join(missing)}")

    validate_choice_field(fields["purchased_from"], purchased_from, "purchased_from")
    for spool_type in sorted(spool_types):
        validate_choice_field(fields["spool_type"], spool_type, "spool_type")


def validate_required_filament_fields(fields: dict[str, dict[str, Any]]) -> None:
    if "purchase_qty" not in fields:
        raise SystemExit("Spoolman is missing required filament extra field: purchase_qty")


def fetch_filament_by_article(base_url: str, article_number: str, timeout: float) -> dict[str, Any]:
    exact_query = f'"{article_number}"'
    encoded = parse.urlencode({"article_number": exact_query})
    response = http_json("GET", f"{base_url}/filament?{encoded}", timeout)
    if not isinstance(response, list):
        raise SystemExit(f"Unexpected filament response for article {article_number}")
    if len(response) != 1:
        raise SystemExit(f"Expected exactly 1 filament for article {article_number}, found {len(response)}")
    filament = response[0]
    if not isinstance(filament, dict):
        raise SystemExit(f"Unexpected filament payload for article {article_number}")
    return filament


def validate_filament(line: OrderLine, filament: dict[str, Any]) -> None:
    vendor_name = ((filament.get("vendor") or {}).get("name") if isinstance(filament.get("vendor"), dict) else None)
    if vendor_name != line.vendor:
        raise SystemExit(
            f"Article {line.article_number} resolved to vendor '{vendor_name}', expected '{line.vendor}'"
        )

    if str(filament.get("name")) != line.name:
        raise SystemExit(
            f"Article {line.article_number} resolved to name '{filament.get('name')}', expected '{line.name}'"
        )

    if str(filament.get("material")) != line.material:
        raise SystemExit(
            f"Article {line.article_number} resolved to material '{filament.get('material')}', expected '{line.material}'"
        )

    actual_id = filament.get("id")
    if line.expected_filament_id is not None and actual_id != line.expected_filament_id:
        raise SystemExit(
            f"Article {line.article_number} resolved to filament ID {actual_id}, expected {line.expected_filament_id}"
        )


def decode_extra_value(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def build_spool_payload(
    filament_id: int,
    price: Decimal,
    location: str,
    purchase_date: str,
    purchased_from: str,
    spool_type: str,
    set_sealed: bool,
) -> dict[str, Any]:
    extra = {
        "purchase_date": encode_extra_value(purchase_date),
        "purchased_from": encode_extra_value(purchased_from),
        "spool_type": encode_extra_value(spool_type),
    }
    if set_sealed:
        extra["sealed"] = encode_extra_value(True)

    return {
        "filament_id": filament_id,
        "price": float(price),
        "location": location,
        "extra": extra,
    }


def dry_run_output(order_name: str, plan: list[dict[str, Any]]) -> None:
    total_spools = len(plan)
    total_price = sum(Decimal(str(item["price"])) for item in plan)
    print(f"Dry run for {order_name}")
    print(f"Spools to create: {total_spools}")
    print(f"Total purchase value: ${total_price:.2f}")
    print()
    print(json.dumps(plan, indent=2))


def dry_run_adjustment_output(order_name: str, adjustments: list[FilamentAdjustment]) -> None:
    if not adjustments:
        return

    print()
    print(f"Purchase-qty adjustments for {order_name}")
    print(json.dumps([adjustment.__dict__ for adjustment in adjustments], indent=2))


def write_canonical_order_file(
    path: Path,
    *,
    order_name: str,
    base_url: str,
    location: str,
    purchase_date_setting: str,
    purchased_from: str,
    set_sealed: bool,
    resolved_lines: list[dict[str, Any]],
) -> None:
    order_payload = {
        "order_name": order_name,
        "base_url": base_url,
        "currency": "USD",
        "defaults": {
            "location": location,
            "purchase_date": purchase_date_setting,
            "purchased_from": purchased_from,
            "set_sealed": set_sealed,
        },
        "items": [
            {
                "vendor": item["vendor"],
                "material": item["material"],
                "name": item["name"],
                "article_number": item["article_number"],
                "quantity": item["quantity"],
                "line_total": f"{item['line_total']:.2f}",
                "spool_type": item["spool_type"],
                "expected_filament_id": item["expected_filament_id"],
            }
            for item in resolved_lines
        ],
    }
    path.write_text(json.dumps(order_payload, indent=2) + "\n", encoding="utf-8")


def build_purchase_qty_adjustments(
    lines: list[OrderLine],
    resolved_filaments: dict[str, dict[str, Any]],
) -> list[FilamentAdjustment]:
    quantity_by_article: dict[str, int] = {}
    for line in lines:
        quantity_by_article[line.article_number] = quantity_by_article.get(line.article_number, 0) + line.quantity

    adjustments: list[FilamentAdjustment] = []
    for article_number, purchased_qty in quantity_by_article.items():
        filament = resolved_filaments[article_number]
        extra = dict(filament.get("extra") or {})
        previous_raw = extra.get("purchase_qty", "0")
        previous_value = decode_extra_value(previous_raw)
        try:
            previous_qty = int(previous_value)
        except (TypeError, ValueError) as exc:
            raise SystemExit(
                f"Filament {filament.get('id')} article {article_number} has non-integer purchase_qty: {previous_raw}"
            ) from exc

        new_qty = max(0, previous_qty - purchased_qty)
        extra["purchase_qty"] = encode_extra_value(new_qty)
        adjustments.append(
            FilamentAdjustment(
                filament_id=int(filament["id"]),
                article_number=article_number,
                name=str(filament.get("name")),
                decremented_by=purchased_qty,
                previous_purchase_qty=previous_qty,
                new_purchase_qty=new_qty,
                payload={"extra": extra},
            )
        )

    return adjustments


def apply_purchase_qty_adjustments(base_url: str, timeout: float, adjustments: list[FilamentAdjustment]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for adjustment in adjustments:
        http_json(
            "PATCH",
            f"{base_url}/filament/{adjustment.filament_id}",
            timeout,
            payload=adjustment.payload,
        )
        results.append(
            {
                "filament_id": adjustment.filament_id,
                "article_number": adjustment.article_number,
                "name": adjustment.name,
                "decremented_by": adjustment.decremented_by,
                "previous_purchase_qty": adjustment.previous_purchase_qty,
                "new_purchase_qty": adjustment.new_purchase_qty,
            }
        )
    return results


def apply_plan(base_url: str, timeout: float, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    for item in plan:
        created_spool = http_json("POST", f"{base_url}/spool", timeout, payload=item["payload"])
        created.append(
            {
                "created_spool_id": created_spool.get("id"),
                "filament_id": item["filament_id"],
                "article_number": item["article_number"],
                "name": item["name"],
                "price": item["price"],
            }
        )
    return created


def main() -> int:
    args = parse_args()
    config = build_order_config(args)
    purchase_date = resolve_purchase_date(config.purchase_date_setting)
    if not config.lines:
        raise SystemExit("Order file contains no items")

    spool_fields = fetch_spool_extra_fields(config.base_url, args.timeout)
    filament_fields = fetch_filament_extra_fields(config.base_url, args.timeout)
    if not args.decrement_purchase_qty_only:
        validate_required_extra_fields(spool_fields, config.purchased_from, {line.spool_type for line in config.lines}, config.set_sealed)
    if args.decrement_purchase_qty:
        validate_required_filament_fields(filament_fields)

    plan: list[dict[str, Any]] = []
    resolved_lines: list[dict[str, Any]] = []
    resolved_filaments: dict[str, dict[str, Any]] = {}
    for line in config.lines:
        filament = fetch_filament_by_article(config.base_url, line.article_number, args.timeout)
        validate_filament(line, filament)
        resolved_filaments[line.article_number] = filament
        prices = allocate_prices(line.line_total, line.quantity)
        filament_id = int(filament["id"])
        resolved_lines.append(
            {
                "vendor": line.vendor,
                "material": line.material,
                "name": line.name,
                "article_number": line.article_number,
                "quantity": line.quantity,
                "line_total": line.line_total,
                "spool_type": line.spool_type,
                "expected_filament_id": filament_id,
            }
        )
        if not args.decrement_purchase_qty_only:
            for spool_index, price in enumerate(prices, start=1):
                payload = build_spool_payload(
                    filament_id=filament_id,
                    price=price,
                    location=config.location,
                    purchase_date=purchase_date,
                    purchased_from=config.purchased_from,
                    spool_type=line.spool_type,
                    set_sealed=config.set_sealed,
                )
                plan.append(
                    {
                        "article_number": line.article_number,
                        "filament_id": filament_id,
                        "name": line.name,
                        "material": line.material,
                        "price": f"{price:.2f}",
                        "spool_number_in_line": spool_index,
                        "payload": payload,
                    }
                )

    adjustments = (
        build_purchase_qty_adjustments(config.lines, resolved_filaments)
        if args.decrement_purchase_qty
        else []
    )

    if args.write_order_file:
        write_canonical_order_file(
            args.write_order_file,
            order_name=config.order_name,
            base_url=config.base_url,
            location=config.location,
            purchase_date_setting=config.purchase_date_setting,
            purchased_from=config.purchased_from,
            set_sealed=config.set_sealed,
            resolved_lines=resolved_lines,
        )

    if not args.apply:
        if not args.decrement_purchase_qty_only:
            dry_run_output(config.order_name, plan)
        dry_run_adjustment_output(config.order_name, adjustments)
        return 0

    if not args.decrement_purchase_qty_only:
        created = apply_plan(config.base_url, args.timeout, plan)
        print(json.dumps(created, indent=2))

    if args.decrement_purchase_qty:
        updated = apply_purchase_qty_adjustments(config.base_url, args.timeout, adjustments)
        print(json.dumps(updated, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())