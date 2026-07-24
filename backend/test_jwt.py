import os
from jose import jwt

secret = os.environ.get('NEXTAUTH_SECRET', 'mysecret')
# Encode like frontend (though frontend uses HS256 directly on the string bytes)
token = jwt.encode({"userId": "123", "email": "test@test.com"}, secret, algorithm="HS256")
print("Generated:", token)

# Decode like backend
decoded = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})
print("Decoded:", decoded)
