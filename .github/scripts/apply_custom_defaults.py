from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]


def replace_exact(content, old, new, expected_count, label):
    old_count = content.count(old)
    new_count = content.count(new)
    if new_count == expected_count:
        return content, False
    if old_count == expected_count:
        return content.replace(old, new), True
    raise RuntimeError(
        f"{label}: expected {expected_count} old occurrence(s), found {old_count}. "
        "The upstream source may have changed; refusing to patch an unknown layout."
    )


def patch_file(path, replacements, changed_files):
    absolute_path = ROOT / path
    if not absolute_path.is_file():
        raise FileNotFoundError(f"Required source file not found: {path}")

    original = absolute_path.read_text(encoding="utf-8")
    content = original
    labels = []

    for old, new, expected_count, label in replacements:
        content, changed = replace_exact(
            content, old, new, expected_count, f"{path}: {label}"
        )
        if changed:
            labels.append(label)

    if content != original:
        changed_files[path] = content
        print(f"[updated] {path}: {', '.join(labels)}")
    else:
        print(f"[unchanged] {path}: custom defaults already applied")

    return content


def require_text(content, needle, label):
    if needle not in content:
        raise RuntimeError(f"Validation failed: {label}")


def main():
    changed_files = {}

    options_path = "src/decompile/options.rs"
    options = patch_file(
        options_path,
        [
            (
                "mode: ParseMode::Permissive,",
                "mode: ParseMode::Strict,",
                1,
                "strict parser default",
            ),
            (
                "mode: NamingMode::DebugLike,",
                "mode: NamingMode::Heuristic,",
                1,
                "heuristic naming default",
            ),
        ],
        changed_files,
    )

    naming_path = "src/ast/naming/common.rs"
    naming = patch_file(
        naming_path,
        [
            (
                "    #[default]\n    Simple,",
                "    Simple,",
                1,
                "NamingMode default variant",
            ),
            (
                "\n    Heuristic,\n}",
                "\n    #[default]\n    Heuristic,\n}",
                1,
                "NamingMode heuristic default marker",
            ),
            (
                "            mode: NamingMode::Simple,",
                "            mode: NamingMode::Heuristic,",
                1,
                "NamingOptions default",
            ),
        ],
        changed_files,
    )

    generate_path = "src/generate/common.rs"
    generate = patch_file(
        generate_path,
        [
            (
                "    Compact,\n    #[default]\n    Balanced,\n    Aligned,\n    Expanded,",
                "    Compact,\n    Balanced,\n    Aligned,\n    #[default]\n    Expanded,",
                1,
                "Expanded table-style default variant",
            ),
            (
                "            table_style: TableStyle::Balanced,",
                "            table_style: TableStyle::Expanded,",
                1,
                "expanded table-style default",
            ),
            (
                "            comment: true,",
                "            comment: false,",
                1,
                "disable generated comments by default",
            ),
        ],
        changed_files,
    )

    cli_path = "packages/unluac-cli/src/cli/args.rs"
    cli = patch_file(
        cli_path,
        [
            (
                "        options.generate.mode = self.generate_mode.unwrap_or(GenerateMode::Permissive);",
                "        set_if_some(&mut options.generate.mode, self.generate_mode);",
                1,
                "respect core GenerateMode default",
            ),
        ],
        changed_files,
    )

    wasm_path = "packages/unluac-wasm/src/lib.rs"
    wasm = patch_file(
        wasm_path,
        [
            (
                "fn default_wasm_decompile_options() -> DecompileOptions {\n"
                "    let mut options = DecompileOptions::default();\n"
                "    options.generate.mode = GenerateMode::Permissive;\n"
                "    options\n"
                "}",
                "fn default_wasm_decompile_options() -> DecompileOptions {\n"
                "    DecompileOptions::default()\n"
                "}",
                1,
                "remove wasm permissive override",
            ),
        ],
        changed_files,
    )

    web_path = "packages/unluac-web/src/stores/settings.ts"
    web = patch_file(
        web_path,
        [
            (
                "const STORAGE_KEY = 'unluac-settings'",
                "const STORAGE_KEY = 'unluac-settings-v2'",
                1,
                "migrate saved browser settings to new defaults",
            ),
            (
                "mode: 'permissive',",
                "mode: 'strict',",
                2,
                "strict parse and generate defaults",
            ),
            (
                "mode: 'debug-like',",
                "mode: 'heuristic',",
                1,
                "heuristic naming default",
            ),
            (
                "tableStyle: 'balanced',",
                "tableStyle: 'expanded',",
                1,
                "expanded table-style default",
            ),
            (
                "comment: true,",
                "comment: false,",
                1,
                "disable generated comments by default",
            ),
        ],
        changed_files,
    )

    expression_path = ROOT / "src/generate/emit/expr.rs"
    if not expression_path.is_file():
        raise FileNotFoundError("Required source file not found: src/generate/emit/expr.rs")
    expression = expression_path.read_text(encoding="utf-8")
    start = expression.find("TableStyle::Expanded => Doc::concat([")
    end = expression.find("TableStyle::Aligned", start)
    if start < 0 or end < 0:
        raise RuntimeError("Could not locate the Expanded table emitter")
    expanded_block = expression[start:end]
    if not re.search(
        r"Doc::indent\(Doc::concat\(\[\s*Doc::line\(\),\s*Doc::join\(field_docs",
        expanded_block,
        re.DOTALL,
    ):
        raise RuntimeError(
            "Expanded table indentation is not the expected fixed version; "
            "refusing to compile with an unverified layout."
        )
    print("[verified] Expanded table first-entry indentation is already fixed")

    require_text(options, "mode: ParseMode::Strict,", "core parser must default to strict")
    require_text(options, "mode: NamingMode::Heuristic,", "core naming must default to heuristic")
    require_text(
        options,
        "string_decode_mode: StringDecodeMode::Strict,",
        "string decoding must remain strict",
    )
    require_text(naming, "#[default]\n    Heuristic,", "Heuristic must be NamingMode's default")
    require_text(generate, "mode: GenerateMode::Strict,", "core generation must remain strict")
    require_text(generate, "table_style: TableStyle::Expanded,", "core tables must default to Expanded")
    require_text(generate, "comment: false,", "core comments must be disabled by default")
    require_text(
        cli,
        "set_if_some(&mut options.generate.mode, self.generate_mode);",
        "CLI must preserve the core generation default",
    )
    require_text(wasm, "fn default_wasm_decompile_options() -> DecompileOptions {\n    DecompileOptions::default()", "WASM must use core defaults")
    require_text(web, "const STORAGE_KEY = 'unluac-settings-v2'", "web settings key must be migrated")
    require_text(web, "mode: 'strict',", "web parse/generate defaults must be strict")
    require_text(web, "mode: 'heuristic',", "web naming default must be heuristic")
    require_text(web, "tableStyle: 'expanded',", "web tables must default to Expanded")
    require_text(web, "comment: false,", "web comments must be disabled by default")

    for relative_path, content in changed_files.items():
        (ROOT / relative_path).write_text(content, encoding="utf-8", newline="\n")

    if changed_files:
        print(f"Applied temporary defaults to {len(changed_files)} source file(s).")
    else:
        print("All temporary defaults were already applied; no files changed.")
    print("No Git commit or push was created. Changes exist only in this runner workspace.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"[apply_custom_defaults] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
      
