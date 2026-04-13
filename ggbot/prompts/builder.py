from __future__ import annotations

from datetime import datetime

from .types import PromptContext, PromptProfile, RenderedPrompt


def _render_template(template: str, context: PromptContext) -> str:
    # Generate detailed tool documentation
    if context.tool_specs:
        tool_sections = []
        for spec in sorted(context.tool_specs, key=lambda s: s.name):
            # Build parameter description
            params_desc = []
            parameters = spec.parameters.get("properties", {})
            required = set(spec.parameters.get("required", []))

            for param_name, param_schema in sorted(parameters.items()):
                param_type = param_schema.get("type", "any")
                param_desc = param_schema.get("description", "")
                required_mark = " (required)" if param_name in required else ""
                param_line = f"    • {param_name}: {param_type}{required_mark}"
                if param_desc:
                    param_line += f" - {param_desc}"
                params_desc.append(param_line)

            # Build tool section
            section = f"- {spec.name}: {spec.description}"
            if params_desc:
                section += "\n" + "\n".join(params_desc)
            tool_sections.append(section)

        tool_docs = "\n".join(tool_sections)
    else:
        tool_docs = "- (no tools available)"

    # Simple tool list for backward compatibility
    tool_names = sorted({spec.name for spec in context.tool_specs if spec.name})
    simple_tool_list = "\n".join(f"- {name}" for name in tool_names) if tool_names else "- (none)"

    # Get current date and time for dynamic variables
    now = datetime.now()

    # Date format variables
    date_vars = {
        # Current date and time
        "{current_date}": now.strftime("%Y-%m-%d"),
        "{current_time}": now.strftime("%H:%M:%S"),
        "{current_datetime}": now.strftime("%Y-%m-%d %H:%M:%S"),
        "{current_datetime_iso}": now.isoformat(),
        "{current_year}": str(now.year),
        "{current_month}": str(now.month),
        "{current_month_name}": now.strftime("%B"),
        "{current_day}": str(now.day),
        "{current_weekday}": now.strftime("%A"),
        "{current_weekday_short}": now.strftime("%a"),

        # Timezone info
        "{timezone}": str(now.astimezone().tzinfo) if now.astimezone().tzinfo else "local",

        # Quarter and week info
        "{current_quarter}": str((now.month - 1) // 3 + 1),
        "{current_week_number}": str(now.isocalendar()[1]),
        "{day_of_year}": str(now.timetuple().tm_yday),

        # Human readable formats
        "{date_human}": now.strftime("%B %d, %Y"),
        "{date_human_full}": now.strftime("%A, %B %d, %Y"),
        "{time_12h}": now.strftime("%I:%M %p"),
        "{time_24h}": now.strftime("%H:%M"),
    }

    out = template
    out = out.replace("{mode}", context.mode)
    out = out.replace("{workspace_root}", str(context.workspace_root))
    out = out.replace("{tool_list}", simple_tool_list)  # backward compatibility
    out = out.replace("{tool_docs}", tool_docs)  # new detailed documentation

    # Replace date variables
    for var, value in date_vars.items():
        out = out.replace(var, value)

    return out


class PromptBuilder:
    def render(self, *, profile: PromptProfile, context: PromptContext) -> RenderedPrompt:
        rendered_sections: list[str] = []
        used_layers: list[str] = []

        for layer in profile.layers:
            if not layer.enabled:
                continue
            text = _render_template(layer.template, context).strip()
            if not text:
                continue
            used_layers.append(layer.name)
            rendered_sections.append(text)

        content = "\n\n".join(rendered_sections).strip()
        return RenderedPrompt(
            profile_name=profile.name,
            layer_names=used_layers,
            content=content,
        )
