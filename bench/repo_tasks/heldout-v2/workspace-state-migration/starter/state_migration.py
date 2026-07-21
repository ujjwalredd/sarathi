def migrate_workspace_state(state):
    if state.get("version") == 3:
        return state
    migrated = state.copy()
    migrated["version"] = 3
    if "name" in migrated:
        migrated["profile"] = {"display_name": migrated.pop("name")}
    migrated["channels"] = ["email"] if migrated.pop("notify", False) else []
    migrated.setdefault("labels", [])
    migrated.setdefault("revision", 0)
    return migrated
