import asyncio
from typing import List

async def _embed_mistral(texts: List[str]) -> List[List[float]]:
    from mistralai import Mistral
    client = Mistral(api_key='fake')
    try:
        response = await client.embeddings.create_async(
            model='mistral-embed',
            inputs=texts,
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        print('Error:', e)
        return []

asyncio.run(_embed_mistral(['hello']))
