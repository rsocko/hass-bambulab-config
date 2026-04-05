from tools.bambuddy.migrate_archive_tag_format import (
    archive_needs_migration,
    normalize_archive_tags,
)


def test_normalize_archive_tags_rewrites_legacy_system_tags() -> None:
    result = normalize_archive_tags(
        "Hueforge,Filament:14,Spool:10,ha_enriched:true",
        "",
    )

    assert result == "Hueforge,f:14,s:10"


def test_normalize_archive_tags_preserves_user_tags_and_deduplicates() -> None:
    result = normalize_archive_tags(
        "Hueforge,Filament:14,Spool:10,Hueforge,f:14,s:10",
        "",
    )

    assert result == "Hueforge,f:14,s:10"


def test_normalize_archive_tags_rebuilds_missing_short_tags_from_payload() -> None:
    notes = (
        "Operator note\n\n"
        '[HA]{"status":"complete","F":[{"f":14,"s":10},{"f":15,"s":10}]}'
    )

    result = normalize_archive_tags("Hueforge", notes)

    assert result == "Hueforge,f:14,s:10,f:15"


def test_archive_needs_migration_only_flags_legacy_tags() -> None:
    assert archive_needs_migration("Hueforge,Filament:14,Spool:10") is True
    assert archive_needs_migration("Hueforge,ha_enriched:true") is True
    assert archive_needs_migration("Hueforge,f:14,s:10") is False