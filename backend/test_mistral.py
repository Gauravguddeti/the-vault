import mistralai
from mistralai import Mistral
print(dir(Mistral))
print(dir(Mistral(api_key='fake').embeddings))
