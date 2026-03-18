import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

print("SUPABASE_URL =", SUPABASE_URL)
print("SUPABASE_KEY exists =", SUPABASE_KEY is not None)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)