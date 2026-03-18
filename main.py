from fastapi import FastAPI
import api.test as test

app = FastAPI()

app.include_router(test.router)