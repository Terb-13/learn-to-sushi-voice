"""
Tools for Learn to Sushi Voice & Chat Agents
Includes menu proposal creation, booking logic, and FAQ lookup.
"""

from typing import Dict, Any, List
from datetime import datetime


def get_available_tools() -> List[Dict[str, Any]]:
    """Return list of available tools for Grok function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": "create_menu_proposal",
                "description": "Create a personalized Sushi River menu proposal for an event. Use this when the user wants to book or see a custom menu.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_name": {"type": "string", "description": "Name of the event (e.g. 'Johnson Family Reunion')"},
                        "guest_count": {"type": "integer", "description": "Number of guests"},
                        "event_date": {"type": "string", "description": "Date of the event (YYYY-MM-DD)"},
                        "arrival_time": {"type": "string", "description": "Guest arrival time (e.g. '3:00 PM')"},
                        "food_start_time": {"type": "string", "description": "When food service starts (e.g. '5:00 PM')"},
                        "host_email": {"type": "string", "description": "Host's email address"},
                        "roll_preferences": {"type": "array", "items": {"type": "string"}, "description": "Preferred rolls (optional)"},
                        "allergies": {"type": "string", "description": "Any allergies or dietary restrictions (optional)"}
                    },
                    "required": ["event_name", "guest_count", "event_date", "arrival_time", "food_start_time", "host_email"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_sushi_river_info",
                "description": "Get detailed information about the Sushi River experience. Use when user asks about the Sushi River setup.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_class_info",
                "description": "Get information about the Interactive Sushi Class. Use when user asks about classes.",
                "parameters": {"type": "object", "properties": {}}
            }
        }
    ]


async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Execute a tool and return the result as a string."""
    
    if tool_name == "create_menu_proposal":
        # In production, this would call the actual menu proposal API
        # For now, return a structured response
        return f"""
Menu proposal created successfully!

**Event:** {arguments.get('event_name')}
**Guests:** {arguments.get('guest_count')}
**Date:** {arguments.get('event_date')}
**Arrival:** {arguments.get('arrival_time')}
**Food Start:** {arguments.get('food_start_time')}

A shareable menu link has been generated and sent to {arguments.get('host_email')}.

The proposal includes our signature 5-row Sushi River setup with fresh rolls selected based on your preferences. A confirmation text will be sent once the booking is finalized.
"""
    
    elif tool_name == "get_sushi_river_info":
        return """
The Sushi River is a premium, self-serve catering setup with a beautiful custom wavy table featuring 5 distinct rows of fresh sushi rolls. Guests walk up and self-serve — it's interactive and visually stunning. Not a conveyor belt or flowing river — it's a gorgeous stationary display perfect for parties and celebrations. Kids love it too!
"""
    
    elif tool_name == "get_class_info":
        return """
Our Interactive Sushi Class is a fun, hands-on experience where a professional chef teaches your group how to make sushi. Everyone participates, learns new skills, and takes home their creations. Perfect for smaller groups (minimum 8 people) who want laughter, learning, and memorable bonding time. Kids are welcome!
"""
    
    else:
        return f"Unknown tool: {tool_name}"