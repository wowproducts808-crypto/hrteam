from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List
from models import UserType, JobStatus

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    user_type: UserType

class UserRead(BaseModel):
    id: str
    email: EmailStr
    name: str
    user_type: UserType
    created_at: datetime

    class Config:
        orm_mode = True

class JobCreate(BaseModel):
    title: str
    description: str
    salary_min: int
    salary_max: int

class JobRead(BaseModel):
    id: str
    employer_id: str
    title: str
    description: str
    salary_min: int
    salary_max: int
    status: JobStatus
    created_at: datetime

    class Config:
        orm_mode = True

class ApplicationCreate(BaseModel):
    cover_letter: str

class ApplicationRead(BaseModel):
    id: str
    job_id: str
    recruiter_id: str
    cover_letter: str
    created_at: datetime

    class Config:
        orm_mode = True

class MessageCreate(BaseModel):
    receiver_id: str
    content: str

class MessageRead(BaseModel):
    id: str
    sender_id: str
    receiver_id: str
    content: str
    created_at: datetime

    class Config:
        orm_mode = True
