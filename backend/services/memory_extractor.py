import json
import logging
from typing import List, Dict

from groq import AsyncGroq
from core.config import settings
from db.connection import get_pool

logger = logging.getLogger(__name__)

MEMORY_PROMPT = """You are a background memory consolidation agent for "The Vault", a personal document assistant.
Your job is to learn durable facts about the USER'S PREFERENCES and BEHAVIORAL PATTERNS based on their recent conversation.

CRITICAL RULES:
1. NEVER extract facts about the user's documents (e.g., do NOT extract "spent $500 on laptop", "has a receipt from Walmart", or dates).
2. ONLY extract behavioral context: preferred tone, verbosity, currency choices, preferred categories, or persistent personal context (e.g. "lives in the UK").
3. You are provided with the user's EXISTING memory array. You must merge any new insights from the recent conversation into this array.
4. Remove redundant, conflicting, or outdated items. Consolidate similar items. Keep the maximum number of items under 10.
5. Return ONLY a valid JSON array of objects.

JSON Object Schema:
{{
  "content": "Short text describing the preference/pattern",
  "category": "preference" | "pattern" | "context"
}}

Existing Memory:
{existing_memory}

Recent Conversation:
{conversation}

Return ONLY the consolidated JSON array.
"""

async def run_memory_extraction(user_id: str, session_id: str, conversation_text: str):
    """
    Extracts and consolidates user memory using Groq, then updates the database.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Fetch existing memory
        existing_rows = await conn.fetch(
            "SELECT id, content, category FROM user_memory WHERE user_id = $1::uuid",
            user_id
        )
        existing_memory = [dict(r) for r in existing_rows]
        
        prompt = MEMORY_PROMPT.format(
            existing_memory=json.dumps(existing_memory, indent=2) if existing_memory else "[]",
            conversation=conversation_text
        )
        
        try:
            client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            response = await client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000,
            )
            content = response.choices[0].message.content.strip()
            
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if not json_match:
                logger.warning(f"No JSON array found in memory extraction for user {user_id}")
                return
                
            new_memory = json.loads(json_match.group())
            
            # Start a transaction to replace memory
            async with conn.transaction():
                # Delete old memory
                await conn.execute("DELETE FROM user_memory WHERE user_id = $1::uuid", user_id)
                
                # Insert new memory
                for mem in new_memory:
                    await conn.execute(
                        """
                        INSERT INTO user_memory (user_id, content, category, source_conversation_id)
                        VALUES ($1::uuid, $2, $3, $4::uuid)
                        """,
                        user_id, mem.get("content", ""), mem.get("category", "context"), session_id
                    )
            logger.info(f"Successfully consolidated {len(new_memory)} memory items for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to run memory extraction for user {user_id}: {e}")
