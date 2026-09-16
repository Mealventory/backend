from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
	id: str
	email: EmailStr | None = None

	model_config = {"from_attributes": True}
