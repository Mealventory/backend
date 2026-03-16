from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
	email: EmailStr


class UserOut(BaseModel):
	id: str
	email: str

	model_config = {"from_attributes": True}
