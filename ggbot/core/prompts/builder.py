from __future__ import annotations

from .types import PromptContext, PromptProfile, RenderedPrompt


def _render_template(template: str, context: PromptContext) -> str:
    tool_names = sorted({name for name in context.tool_names if name})
    tool_list = "\n".join(f"- {name}" for name in tool_names) if tool_names else "- (none)"

    out = template
    out = out.replace("{mode}", context.mode)
    out = out.replace("{workspace_root}", str(context.workspace_root))
    out = out.replace("{tool_list}", tool_list)
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
