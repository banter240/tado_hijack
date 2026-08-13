"""Validate translation coverage against the Home Assistant action schema."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVICES_FILE = ROOT / "custom_components" / "tado_hijack" / "services.yaml"
TRANSLATIONS_DIR = ROOT / "custom_components" / "tado_hijack" / "translations"
LANGUAGES = ("en", "de", "cs")
PLACEHOLDER_PATTERN = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")
SERVICE_FIELDS_INDENT = 2
FIELD_INDENT = 4


def _load_translation(language: str) -> dict[str, Any]:
    with (TRANSLATIONS_DIR / f"{language}.json").open(encoding="utf-8") as file:
        data: dict[str, Any] = json.load(file)
    return data


def _leaf_values(value: dict[str, Any], prefix: str = "") -> Iterator[tuple[str, str]]:
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            yield from _leaf_values(item, path)
        elif isinstance(item, str):
            yield path, item


def _parse_service_schema() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    services: dict[str, set[str]] = {}
    selectors: dict[str, set[str]] = {}
    current_service: str | None = None
    current_selector: str | None = None
    in_fields = False
    in_options = False

    for raw_line in SERVICES_FILE.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip())

        if indent == 0 and re.fullmatch(r"[a-z][a-z0-9_]*:", stripped):
            current_service = stripped[:-1]
            services[current_service] = set()
            current_selector = None
            in_fields = False
            in_options = False
            continue

        if current_service is None:
            continue

        if indent == SERVICE_FIELDS_INDENT and stripped == "fields:":
            in_fields = True
            continue

        if in_fields and indent == FIELD_INDENT:
            match = re.fullmatch(r"([a-z][a-z0-9_]*):(?:\s+[&*][a-z0-9_]+)?", stripped)
            if match:
                services[current_service].add(match.group(1))

        if stripped.startswith("translation_key:"):
            current_selector = stripped.split(":", maxsplit=1)[1].strip()
            selectors.setdefault(current_selector, set())
            in_options = False
            continue

        if current_selector is not None and stripped == "options:":
            in_options = True
            continue

        if in_options and current_selector is not None and stripped.startswith("- "):
            selectors[current_selector].add(stripped[2:].strip("\"'"))
        elif in_options and stripped and not stripped.startswith("#"):
            in_options = False

    return services, selectors


def _validate_leaf_parity(
    translations: dict[str, dict[str, Any]], errors: list[str]
) -> None:
    reference = dict(_leaf_values(translations["en"]))
    reference_keys = set(reference)

    for language in LANGUAGES[1:]:
        localized = dict(_leaf_values(translations[language]))
        localized_keys = set(localized)
        for key in sorted(reference_keys - localized_keys):
            errors.append(f"{language}: missing translation key {key}")
        for key in sorted(localized_keys - reference_keys):
            errors.append(f"{language}: unexpected translation key {key}")
        for key in sorted(reference_keys & localized_keys):
            expected = set(PLACEHOLDER_PATTERN.findall(reference[key]))
            actual = set(PLACEHOLDER_PATTERN.findall(localized[key]))
            if actual != expected:
                errors.append(
                    f"{language}: placeholder mismatch for {key}: "
                    f"expected {sorted(expected)}, got {sorted(actual)}"
                )


def _validate_services(
    translations: dict[str, dict[str, Any]],
    schema: dict[str, set[str]],
    errors: list[str],
) -> None:
    expected_services = set(schema)
    for language in LANGUAGES:
        localized_services = translations[language].get("services", {})
        actual_services = set(localized_services)
        for service in sorted(expected_services - actual_services):
            errors.append(f"{language}: missing action translation services.{service}")
        for service in sorted(actual_services - expected_services):
            errors.append(f"{language}: obsolete action translation services.{service}")

        for service in sorted(expected_services & actual_services):
            localized = localized_services[service]
            for metadata_key in ("name", "description"):
                if not localized.get(metadata_key):
                    errors.append(
                        f"{language}: missing services.{service}.{metadata_key}"
                    )

            localized_fields = localized.get("fields", {})
            expected_fields = schema[service]
            actual_fields = set(localized_fields)
            for field in sorted(expected_fields - actual_fields):
                errors.append(f"{language}: missing services.{service}.fields.{field}")
            for field in sorted(actual_fields - expected_fields):
                errors.append(f"{language}: obsolete services.{service}.fields.{field}")
            for field in sorted(expected_fields & actual_fields):
                for metadata_key in ("name", "description"):
                    if not localized_fields[field].get(metadata_key):
                        errors.append(
                            f"{language}: missing services.{service}.fields."
                            f"{field}.{metadata_key}"
                        )


def _validate_selectors(
    translations: dict[str, dict[str, Any]],
    schema: dict[str, set[str]],
    errors: list[str],
) -> None:
    for language in LANGUAGES:
        localized_selectors = translations[language].get("selector", {})
        for selector, expected_options in schema.items():
            options = localized_selectors.get(selector, {}).get("options")
            if not isinstance(options, dict):
                errors.append(f"{language}: missing selector.{selector}.options")
                continue

            actual_options = set(options)
            for option in sorted(expected_options - actual_options):
                errors.append(
                    f"{language}: missing selector.{selector}.options.{option}"
                )
            for option in sorted(actual_options - expected_options):
                errors.append(
                    f"{language}: unexpected selector.{selector}.options.{option}"
                )
            for option in sorted(expected_options & actual_options):
                if not options[option].strip():
                    errors.append(
                        f"{language}: empty selector.{selector}.options.{option}"
                    )


def main() -> int:
    """Run all translation checks and return a process exit code."""
    translations = {language: _load_translation(language) for language in LANGUAGES}
    services, selectors = _parse_service_schema()
    errors: list[str] = []

    _validate_leaf_parity(translations, errors)
    _validate_services(translations, services, errors)
    _validate_selectors(translations, selectors, errors)

    if errors:
        print("Translation validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Translation validation passed for "
        f"{len(LANGUAGES)} languages, {len(services)} actions, and "
        f"{len(selectors)} translated selectors."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
