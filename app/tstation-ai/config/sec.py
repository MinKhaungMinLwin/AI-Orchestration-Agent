from config.env import settings
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)

def get_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    if not credentials:
        raise HTTPException(status_code=403, detail="Forbidden")

    token = credentials.credentials
    if token == settings.API_SECRET_KEY:
        return token
    raise HTTPException(status_code=403, detail="Forbidden")
