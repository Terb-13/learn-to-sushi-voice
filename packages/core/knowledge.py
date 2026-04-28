"""
Knowledge Base Retrieval for Learn to Sushi
Handles RAG from Supabase knowledge_base and faq_entries tables.
"""

import os
from typing import List, Dict, Any, Optional
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase: Optional[Client] = None

def get_supabase_client() -> Client:
    global supabase
    if supabase is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Missing Supabase credentials")
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase


async def get_knowledge_context(query: str, limit: int = 5) -> str:
    """
    Retrieve relevant knowledge from Supabase for RAG.
    Returns formatted context string.
    """
    try:
        client = get_supabase_client()
    except Exception as e:
        print(f"Supabase unavailable for knowledge: {e}")
        return "No specific knowledge found. Answer based on general brand guidelines."

    # Search knowledge_base table (approved corrections + brand guideline)
    try:
        response = client.table("knowledge_base").select(
            "original_question, corrected_answer, category"
        ).eq("status", "approved").limit(limit).execute()
        
        knowledge_rows = response.data if response.data else []
    except Exception as e:
        print(f"Knowledge base query error: {e}")
        knowledge_rows = []
    
    # Search faq_entries table
    try:
        faq_response = client.table("faq_entries").select(
            "question, answer, category"
        ).eq("status", "approved").limit(limit).execute()
        
        faq_rows = faq_response.data if faq_response.data else []
    except Exception as e:
        print(f"FAQ query error: {e}")
        faq_rows = []
    
    try:
        context_parts: List[str] = []
        for row in knowledge_rows:
            context_parts.append(
                f"Q: {row.get('original_question', '')}\nA: {row.get('corrected_answer', '')}"
            )
        for row in faq_rows:
            context_parts.append(
                f"FAQ: {row.get('question', '')}\n{row.get('answer', '')}"
            )
        if not context_parts:
            return "No specific knowledge found. Answer based on general brand guidelines."
        return "\n\n".join(context_parts[:limit])
    except Exception as e:
        print(f"Knowledge formatting error: {e}")
        return "No specific knowledge found. Answer based on general brand guidelines."


async def log_conversation_turn(
    session_id: str,
    user_message: str,
    assistant_message: str,
    channel: str = "web"
) -> Optional[str]:
    """Log a conversation turn to Supabase for analytics and learning."""
    client = get_supabase_client()
    
    try:
        response = client.table("conversations").insert({
            "session_id": session_id,
            "channel": channel,
            "messages": [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message}
            ]
        }).execute()
        
        return response.data[0]["id"] if response.data else None
    except Exception as e:
        print(f"Failed to log conversation: {e}")
        return None