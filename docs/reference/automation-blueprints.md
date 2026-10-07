# Automation blueprints

Automation blueprints are reusable scheduled-work templates. Open the TUI and use `/blueprint <name>` to choose one, supply its required fields, and confirm before a cron job is created. Existing jobs can be inspected with `/cron`.

To author a blueprint, add a `metadata.freeide.blueprint` block to a skill's `SKILL.md`. The key is a compatibility identifier in the current runtime. See [Creating Skills](../developer-guide/creating-skills.md) for the schema.
