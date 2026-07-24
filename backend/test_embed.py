import os
from fastembed import TextEmbedding
try:
    model = TextEmbedding(model_name='nomic-embed-text')
    print('Success')
except Exception as e:
    print('Error:', e)
