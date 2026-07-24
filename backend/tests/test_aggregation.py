import pytest
import pytest_asyncio
from agents.vault_agent import generate_answer_node

@pytest.mark.asyncio
async def test_aggregation_formatting():
    # We will test the generate_answer_node handling of sql_result
    
    sql_result = {
        "total": 1250.50,
        "count": 5,
        "currency": "USD",
        "category": "electronics",
        "date_from": "2025-01-01",
        "date_to": "2025-12-31",
        "docs": [
            {"name": "BestBuy_Laptop.pdf", "amount": 1000.0, "currency": "USD", "date": "2025-03-15"},
            {"name": "Mouse.pdf", "amount": 250.50, "currency": "USD", "date": "2025-04-10"}
        ]
    }
    
    result = await generate_answer_node({
        "question": "How much did I spend on electronics in 2025?",
        "session_id": "test-session",
        "user_id": "test-user",
        "conn": None,
        "history": [],
        "query_type": "aggregation",
        "chunks": [],
        "sql_result": sql_result,
        "answer": "",
        "sources": [],
        "context_truncated": False,
    })
    
    answer = result["answer"]
    
    assert "1250.5" in answer or "1,250.50" in answer, "The LLM failed to include the exact SQL total in the answer."
    assert "BestBuy_Laptop.pdf" in answer, "The LLM failed to cite the contributing documents."
