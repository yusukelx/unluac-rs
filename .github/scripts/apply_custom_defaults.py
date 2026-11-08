from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def replace_count(content, old, new, expected, label):
    old_count = content.count(old)
    new_count = content.count(new)

    if old_count == expected:
        return content.replace(old, new), True

    if old_count == 0 and new_count == expected:
        return content, False

    raise RuntimeError(
        f"{label}: expected {expected} occurrence(s), "
        f"found {old_count} old and {new_count} updated."
    )


def require(content, value, label):
    if value not in content:
        raise RuntimeError(f"Verification failed: {label}")


def read_file(relative):
    path = ROOT / relative

    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {relative}")

    return path.read_text(encoding="utf-8")


def patch_file(relative, rules):
    content = read_file(relative)

    for old, new, expected, label in rules:
        content, _ = replace_count(
            content,
            old,
            new,
            expected,
            label,
        )

    return content


def verify_expanded_indent(expression):
    start = expression.find("TableStyle::Expanded => Doc::concat([")
    end = expression.find(
        "TableStyle::Aligned => unreachable!",
        start,
    )

    if start < 0 or end < 0:
        raise RuntimeError("Could not locate Expanded table emitter")

    block = expression[start:end]

    required = [
        "Doc::indent(Doc::concat([",
        "Doc::line(),",
        "Doc::join(field_docs,",
    ]

    positions = [block.find(value) for value in required]

    if any(position < 0 for position in positions):
        raise RuntimeError(
            "Expanded table indentation is not the expected fixed version."
        )

    if positions != sorted(positions):
        raise RuntimeError("Expanded table indentation is incorrect.")

    print("[verified] Expanded table indentation")


def main():
    changed_files = {}

    decompile = patch_file(
        "src/decompile/options.rs",
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
    )
    changed_files["src/decompile/options.rs"] = decompile

    naming = patch_file(
        "src/ast/naming/common.rs",
        [
            (
                "    #[default]\n"
                "    Simple,\n"
                "    /// 在通用策略上利用表达式形状、字段用途和调用线索推断名字。\n"
                "    Heuristic,",
                "    Simple,\n"
                "    /// 在通用策略上利用表达式形状、字段用途和调用线索推断名字。\n"
                "    #[default]\n"
                "    Heuristic,",
                1,
                "NamingMode default variant",
            ),
            (
                "            mode: NamingMode::Simple,",
                "            mode: NamingMode::Heuristic,",
                1,
                "NamingOptions default",
            ),
        ],
    )
    changed_files["src/ast/naming/common.rs"] = naming

    generate = patch_file(
        "src/generate/common.rs",
        [
            (
                "    Compact,\n"
                "    #[default]\n"
                "    Balanced,\n"
                "    Aligned,\n"
                "    Expanded,",
                "    Compact,\n"
                "    Balanced,\n"
                "    Aligned,\n"
                "    #[default]\n"
                "    Expanded,",
                1,
                "TableStyle default variant",
            ),
            (
                "            table_style: TableStyle::Balanced,",
                "            table_style: TableStyle::Expanded,",
                1,
                "expanded table default",
            ),
            (
                "            comment: true,",
                "            comment: false,",
                1,
                "disable generated comments",
            ),
        ],
    )
    changed_files["src/generate/common.rs"] = generate

    cli = patch_file(
        "packages/unluac-cli/src/cli/args.rs",
        [
            (
                "        options.generate.mode = self.generate_mode.unwrap_or(GenerateMode::Permissive);",
                "        set_if_some(&mut options.generate.mode, self.generate_mode);",
                1,
                "preserve core GenerateMode default",
            ),
        ],
    )
    changed_files["packages/unluac-cli/src/cli/args.rs"] = cli

    wasm = patch_file(
        "packages/unluac-wasm/src/lib.rs",
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
                "remove WASM permissive override",
            ),
        ],
    )
    changed_files["packages/unluac-wasm/src/lib.rs"] = wasm

    web = patch_file(
        "packages/unluac-web/src/stores/settings.ts",
        [
            (
                "const STORAGE_KEY = 'unluac-settings'",
                "const STORAGE_KEY = 'unluac-settings-v2'",
                1,
                "migrate saved browser settings",
            ),
            (
                "mode: 'permissive',",
                "mode: 'strict',",
                2,
                "strict web defaults",
            ),
            (
                "mode: 'debug-like',",
                "mode: 'heuristic',",
                1,
                "heuristic web naming",
            ),
            (
                "tableStyle: 'balanced',",
                "tableStyle: 'expanded',",
                1,
                "expanded web tables",
            ),
            (
                "comment: true,",
                "comment: false,",
                1,
                "disable web comments",
            ),
        ],
    )
    changed_files["packages/unluac-web/src/stores/settings.ts"] = web

    parser = read_file("src/parser/options.rs")
    expression = read_file("src/generate/emit/expr.rs")

    require(
        parser,
        "#[default]\n    Strict,",
        "parser strict enum default",
    )
    require(
        decompile,
        "mode: ParseMode::Strict,",
        "pipeline strict parser default",
    )
    require(
        decompile,
        "string_decode_mode: StringDecodeMode::Strict,",
        "strict string decoding",
    )
    require(
        naming,
        "#[default]\n    Heuristic,",
        "heuristic naming enum default",
    )
    require(
        decompile,
        "mode: NamingMode::Heuristic,",
        "pipeline heuristic naming default",
    )
    require(
        naming,
        "debug_like_include_function: true,",
        "debug-like function naming option",
    )
    require(
        generate,
        "mode: GenerateMode::Strict,",
        "strict generation default",
    )
    require(
        generate,
        "table_style: TableStyle::Expanded,",
        "expanded table default",
    )
    require(
        generate,
        "#[default]\n    Expanded,",
        "expanded table enum default",
    )
    require(
        generate,
        "comment: false,",
        "generated comments disabled",
    )
    require(
        cli,
        "set_if_some(&mut options.generate.mode, self.generate_mode);",
        "CLI respects core generation defaults",
    )
    require(
        wasm,
        "fn default_wasm_decompile_options() -> DecompileOptions {\n"
        "    DecompileOptions::default()\n}",
        "WASM respects core defaults",
    )
    require(
        web,
        "const STORAGE_KEY = 'unluac-settings-v2'",
        "web settings migration",
    )
    require(
        web,
        "mode: 'strict',",
        "web strict defaults",
    )
    require(
        web,
        "mode: 'heuristic',",
        "web heuristic default",
    )
    require(
        web,
        "tableStyle: 'expanded',",
        "web expanded table default",
    )
    require(
        web,
        "comment: false,",
        "web comments disabled",
    )

    verify_expanded_indent(expression)

    changed = []

    for relative, content in changed_files.items():
        path = ROOT / relative
        original = path.read_text(encoding="utf-8")

        if content != original:
            path.write_text(content, encoding="utf-8")
            changed.append(relative)

    if changed:
        print(f"Applied custom defaults to {len(changed)} file(s):")

        for relative in changed:
            print(f"  - {relative}")
    else:
        print("All custom defaults are already applied.")

    print("No Git commit or push was created.")
    print("Changes exist only in the current runner workspace.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"[apply_custom_defaults] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
