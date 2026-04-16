import json
import asyncio
import httpx
from ggbot.runtime.model_interaction import parse_plan_items

def test_parsing():
    plan_text = """
    1. [ ] Search for info (web_search)
    2. [x] Fetch content (web_fetch)
    3. [ ] Summarize
    """
    items = parse_plan_items(plan_text)
    print("Parsed items:")
    print(json.dumps(items, indent=2))

if __name__ == "__main__":
    test_parsing()
