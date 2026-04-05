from tools.bambuddy.migrate_archive_notes_format import (
    archive_needs_notes_migration,
    normalize_archive_notes,
    transform_payload,
)


def test_transform_payload_compacts_legacy_keys_and_codes() -> None:
    payload = {
        "status": "partial",
        "Filaments": [
            {
                "name": "Black",
                "weight": 33.3,
                "tray": None,
                "s": 10,
                "f": 14,
                "h": "#000000",
                "ambiguity": "multiple archived AMS trays matched type+color",
            }
        ],
        "source": "archived_filament_slots",
        "reason": "diagnostic",
        "ambiguities": [{"reason": "redundant"}],
    }

    assert transform_payload(payload) == {
        "status": "partial",
        "F": [{"n": "Black", "w": 33.3, "t": None, "s": 10, "f": 14, "h": "#000000", "am": "a_tc"}],
        "src": "afs",
        "reason": "diagnostic",
    }


def test_normalize_archive_notes_rewrites_marker_and_preserves_prefix() -> None:
    notes = (
        "[RECOVERY_AUDIT_V1]\n{\"recovered_from_archive_id\":191}\n\n"
        "[HA_ENRICHMENT_V1]\n"
        '{"status":"complete","Filaments":[{"name":"Black","weight":33.3,"tray":null,"s":10,"f":14,"h":"#000000"}],"source":"archived_filament_slots"}'
    )

    assert normalize_archive_notes(notes) == (
        "[RECOVERY_AUDIT_V1]\n{\"recovered_from_archive_id\":191}\n\n"
        '[HA]{"status":"complete","F":[{"n":"Black","w":33.3,"t":null,"s":10,"f":14,"h":"#000000"}],"src":"afs"}'
    )


def test_archive_needs_notes_migration_only_flags_legacy_marker() -> None:
    assert archive_needs_notes_migration('[HA_ENRICHMENT_V1]{"status":"complete"}') is True
    assert archive_needs_notes_migration('[HA]{"status":"complete"}') is False