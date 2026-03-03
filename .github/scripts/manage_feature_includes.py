import argparse
import re
from pathlib import Path


def parse_candidates(candidates_arg: str):
    candidates = []
    for item in candidates_arg.split(','):
        item = item.strip()
        if not item:
            continue
        feature, include_path = item.split(':', 1)
        key = f"{feature}_loader"
        include_line_inline = f"    {key}: !include {include_path}\n"
        include_line_include_file = f"{key}: !include {include_path}\n"
        candidates.append((feature, include_path, include_line_inline, include_line_include_file))
    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument(
        "--mode",
        required=True,
        choices=["check", "auto_update", "include_file_check", "include_file_auto_update"],
    )
    args = parser.parse_args()

    src = Path(args.source)
    dst = Path(args.output)

    text = src.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    candidates = parse_candidates(args.candidates)

    existing = []
    missing = []
    for feature, include_path, include_line_inline, include_line_include_file in candidates:
        if include_path in text:
            existing.append(feature)
        else:
            missing.append((feature, include_path, include_line_inline, include_line_include_file))

    unsupported_reason = ""
    added = []

    if args.mode == "include_file_auto_update" and missing:
        updated_lines = lines[:]
        if updated_lines and not updated_lines[-1].endswith("\n"):
            updated_lines[-1] = updated_lines[-1] + "\n"
        for feature, include_path, include_line_inline, include_line_include_file in missing:
            updated_lines.append(include_line_include_file)
            added.append(feature)
        lines = updated_lines

    elif args.mode == "auto_update" and missing:
        home_idx = None
        for idx, line in enumerate(lines):
            if re.match(r"^homeassistant:\s*$", line.rstrip("\n")):
                home_idx = idx
                break

        if home_idx is None:
            unsupported_reason = "No 'homeassistant:' root key found."
        else:
            block_end = len(lines)
            for idx in range(home_idx + 1, len(lines)):
                raw = lines[idx]
                if raw.strip() == "" or raw.lstrip().startswith("#"):
                    continue
                if len(raw) - len(raw.lstrip(" ")) <= 0:
                    block_end = idx
                    break

            packages_idx = None
            packages_is_include = False
            for idx in range(home_idx + 1, block_end):
                raw = lines[idx]
                if re.match(r"^\s{2}packages:\s*$", raw.rstrip("\n")):
                    packages_idx = idx
                    break
                if re.match(r"^\s{2}packages:\s*!include", raw.rstrip("\n")):
                    packages_idx = idx
                    packages_is_include = True
                    break

            if packages_idx is None:
                unsupported_reason = "No '  packages:' mapping block found under homeassistant."
            elif packages_is_include:
                unsupported_reason = "'homeassistant.packages' uses !include; auto_update of inline entries is disabled."
            else:
                insert_at = block_end
                for idx in range(packages_idx + 1, block_end):
                    raw = lines[idx]
                    if raw.strip() == "" or raw.lstrip().startswith("#"):
                        continue
                    indent = len(raw) - len(raw.lstrip(" "))
                    if indent <= 2:
                        insert_at = idx
                        break

                to_add = []
                for feature, include_path, include_line_inline, include_line_include_file in missing:
                    to_add.append(include_line_inline)
                    added.append(feature)

                lines[insert_at:insert_at] = to_add

    updated_text = "".join(lines)
    dst.write_text(updated_text, encoding="utf-8")

    print("EXISTING=" + ",".join(existing))
    print("MISSING=" + ",".join(feature for feature, *_ in missing))
    print("ADDED=" + ",".join(added))
    print("CHANGED=" + ("true" if text != updated_text else "false"))
    print("UNSUPPORTED=" + unsupported_reason)


if __name__ == "__main__":
    main()
