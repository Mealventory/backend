import firebase_admin
from firebase_admin import auth, credentials
from fastapi import HTTPException, status
from app.core.config import settings

_firebase_app = None


def get_firebase_app():
	global _firebase_app
	if _firebase_app is None:
		if settings.FIREBASE_PROJECT_ID:
			cred = credentials.ApplicationDefault()
			_firebase_app = firebase_admin.initialize_app(
				cred, {"projectId": settings.FIREBASE_PROJECT_ID}
			)
		else:
			_firebase_app = firebase_admin.initialize_app()
	return _firebase_app


def verify_firebase_token(token: str) -> dict:
	try:
		get_firebase_app()
		decoded = auth.verify_id_token(token)
		return decoded
	except Exception:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or expired token",
			headers={"WWW-Authenticate": "Bearer"},
		)
