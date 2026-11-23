def create_trigger(trigger_name: str, table: str, timing: str,
                   event: str, body: str) -> str:
    return (
        f"CREATE TRIGGER {trigger_name}\n"
        f"{timing} {event} ON {table}\n"
        f"BEGIN\n{body}\nEND;"
    )


def drop_trigger(trigger_name: str) -> str:
    return f"DROP TRIGGER IF EXISTS {trigger_name};"


def same_landlord_trigger(trigger_name: str, table: str, local_field: str,
                          reference_table: str) -> str:
    body = (
        "SELECT CASE WHEN NEW.landlord_id IS NULL "
        "OR EXISTS (SELECT 1 FROM " + reference_table +
        " WHERE id = NEW." + local_field +
        " AND landlord_id != NEW.landlord_id) "
        "THEN RAISE(ABORT, 'cross-landlord reference') END;"
    )
    return create_trigger(
        trigger_name,
        table,
        "BEFORE",
        "INSERT",
        body,
    )


def append_only_trigger(trigger_name: str, table: str,
                        operation: str) -> str:
    body = "RAISE(ABORT, 'append-only record');"
    return create_trigger(
        trigger_name,
        table,
        "BEFORE",
        operation,
        body,
    )
