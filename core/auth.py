from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL or SUPABASE_ANON_KEY is missing")

security = HTTPBearer()
supabase_auth = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials

    try:
        response = supabase_auth.auth.get_user(token)
        user = response.user

        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        return user
    except HTTPException:
        raise
    except Exception as e:
        print("AUTH ERROR:", str(e))
        raise HTTPException(status_code=401, detail="Invalid or expired token")