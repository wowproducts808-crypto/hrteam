import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Enum, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class UserType(enum.Enum):
    EMPLOYER = "employer"
    RECRUITER = "recruiter"
    ADMIN = "admin"

class JobStatus(enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    OPEN = "open"
    PAUSED = "paused"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    REJECTED = "rejected"

class ApplicationStatus(enum.Enum):
    PENDING = "pending"
    SELECTED = "selected"
    WORKING = "working"
    COMPLETED = "completed"
    REJECTED = "rejected"

class PaymentStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"

class NotificationType(enum.Enum):
    NEW_APPLICATION = "new_application"
    NEW_JOB = "new_job"
    NEW_MESSAGE = "new_message"
    JOB_STATUS_CHANGE = "job_status_change"
    APPLICATION_STATUS_CHANGE = "application_status_change"
    NEW_RATING = "new_rating"
    JOB_APPROVED = "job_approved"
    JOB_REJECTED = "job_rejected"
    PAYMENT_SUCCESS = "payment_success"

class MessageType(enum.Enum):
    TEXT = "text"
    FILE = "file"
    SYSTEM = "system"
    IMAGE = "image"
    DOCUMENT = "document"

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    user_type = Column(Enum(UserType), nullable=False)
    
    # Дополнительная информация профиля
    first_name = Column(String)
    last_name = Column(String)
    phone = Column(String)
    location = Column(String)
    bio = Column(Text)
    avatar_url = Column(String)
    
    # Для рекрутеров
    experience = Column(Text)
    specialization = Column(String)
    portfolio_url = Column(String)
    resume_url = Column(String)
    skills = Column(Text)
    certifications = Column(Text)
    languages = Column(String)
    hourly_rate = Column(Float)
    availability = Column(String)
    
    # Для работодателей
    company = Column(String)
    company_size = Column(String)
    industry = Column(String)
    website = Column(String)
    company_description = Column(Text)
    tax_id = Column(String)
    
    # Системные поля
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    phone_verified = Column(Boolean, default=False)
    verification_token = Column(String)
    reset_password_token = Column(String)
    reset_password_expires = Column(DateTime)
    last_login = Column(DateTime)
    last_activity = Column(DateTime)
    login_count = Column(Integer, default=0)
    profile_completion = Column(Integer, default=0)
    
    # Настройки уведомлений
    email_notifications = Column(Boolean, default=True)
    sms_notifications = Column(Boolean, default=False)
    push_notifications = Column(Boolean, default=True)
    newsletter_subscription = Column(Boolean, default=True)
    
    # Даты
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime)

    # Relationships
    jobs = relationship("Job", back_populates="employer", foreign_keys="Job.employer_id")
    recruiter_applications = relationship("Application", back_populates="recruiter")
    sent_messages = relationship("Message", back_populates="sender", foreign_keys="Message.sender_id")
    received_messages = relationship("Message", back_populates="recipient", foreign_keys="Message.recipient_id")
    recruiter_ratings = relationship("RecruiterRating", back_populates="recruiter", foreign_keys="RecruiterRating.recruiter_id")
    employer_ratings = relationship("RecruiterRating", back_populates="employer", foreign_keys="RecruiterRating.employer_id")
    notifications = relationship("Notification", back_populates="user", foreign_keys="Notification.user_id")
    payments = relationship("Payment", back_populates="employer")

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    employer_id = Column(String, ForeignKey("users.id"))
    moderator_id = Column(String, ForeignKey("users.id"), nullable=True)
    
    # Основная информация
    title = Column(String, nullable=False)
    slug = Column(String, unique=True)
    description = Column(Text, nullable=False)
    short_description = Column(String)
    requirements = Column(Text)
    benefits = Column(Text)
    responsibilities = Column(Text)
    
    # Локация и тип работы
    location = Column(String)
    remote_work = Column(Boolean, default=False)
    employment_type = Column(String, default="full-time")
    experience_level = Column(String)
    
    # Зарплата
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    salary_currency = Column(String, default="тенге")
    salary_type = Column(String, default="monthly")
    salary_negotiable = Column(Boolean, default=False)
    
    # Дополнительная информация
    category = Column(String)
    tags = Column(Text)
    urgency = Column(String, default="normal")
    deadline = Column(DateTime)
    
    # Настройки вакансии
    max_applications = Column(Integer, default=3)
    auto_reject_after_days = Column(Integer, default=30)
    featured = Column(Boolean, default=False)
    premium = Column(Boolean, default=False)
    
    # Статус и модерация
    status = Column(Enum(JobStatus), default=JobStatus.DRAFT)
    status_reason = Column(String)
    rejection_reason = Column(String)
    moderated_at = Column(DateTime)
    moderation_comment = Column(Text)
    
    # Аналитика
    views_count = Column(Integer, default=0)
    applications_count = Column(Integer, default=0)
    clicks_count = Column(Integer, default=0)
    avg_time_to_fill = Column(Integer)
    winner_application_id = Column(String)
    
    # SEO
    meta_title = Column(String)
    meta_description = Column(String)
    meta_keywords = Column(String)
    
    # Даты
    published_at = Column(DateTime)
    expires_at = Column(DateTime)
    filled_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime)

    # Relationships
    employer = relationship("User", back_populates="jobs", foreign_keys=[employer_id])
    moderator = relationship("User", foreign_keys=[moderator_id])
    applications = relationship("Application", back_populates="job")
    payment = relationship("Payment", back_populates="job", uselist=False)

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"))
    employer_id = Column(String, ForeignKey("users.id"))
    
    # Основная информация о платеже
    amount = Column(Float, nullable=False)
    currency = Column(String, default="KZT")
    description = Column(String)
    
    # Скидки и налоги
    discount_amount = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    processing_fee = Column(Float, default=0.0)
    
    # Статус и метод оплаты
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_method = Column(String)
    payment_provider = Column(String)
    
    # Данные транзакции
    transaction_id = Column(String, unique=True)
    payment_system_id = Column(String)
    payment_data = Column(Text)
    
    # Даты
    paid_at = Column(DateTime)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Дополнительные поля
    invoice_number = Column(String, unique=True)
    receipt_url = Column(String)
    refund_reason = Column(String)
    refunded_at = Column(DateTime)

    # Relationships
    job = relationship("Job", back_populates="payment")
    employer = relationship("User", back_populates="payments")

class Application(Base):
    __tablename__ = "applications"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"))
    recruiter_id = Column(String, ForeignKey("users.id"))
    
    # Основная информация
    cover_letter = Column(Text)
    expected_salary = Column(Integer)
    available_from = Column(DateTime)
    expected_start_date = Column(DateTime)
    
    # Дополнительные поля
    portfolio_urls = Column(Text)
    attachments = Column(Text)
    questionnaire_answers = Column(Text)
    
    # Статус и оценка
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING)
    rating = Column(Float)
    employer_notes = Column(Text)
    recruiter_notes = Column(Text)
    
    # Процесс отбора
    interview_scheduled = Column(DateTime)
    interview_completed = Column(Boolean, default=False)
    test_results = Column(Text)
    background_check = Column(Boolean)
    references_checked = Column(Boolean)
    
    # Даты
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reviewed_at = Column(DateTime)
    hired_at = Column(DateTime)

    # Relationships
    job = relationship("Job", back_populates="applications")
    recruiter = relationship("User", back_populates="recruiter_applications")
    messages = relationship("Message", back_populates="related_application")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_id = Column(String, ForeignKey("users.id"), nullable=False)
    recipient_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    # Ключевое поле для системы чата - связь с заявкой
    related_application_id = Column(String, ForeignKey("applications.id"), nullable=True)
    
    # Основная информация
    content = Column(Text, nullable=False)
    message_type = Column(Enum(MessageType), default=MessageType.TEXT)
    
    # Статус
    is_read = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    
    # Дополнительные поля для чата
    attachments = Column(Text)
    
    # Даты
    created_at = Column(DateTime, default=datetime.utcnow)
    read_at = Column(DateTime)

    # Relationships
    sender = relationship("User", back_populates="sent_messages", foreign_keys=[sender_id])
    recipient = relationship("User", back_populates="received_messages", foreign_keys=[recipient_id])
    related_application = relationship("Application", back_populates="messages", foreign_keys=[related_application_id])

class ChatFile(Base):
    __tablename__ = "chat_files"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String, ForeignKey("messages.id"), nullable=False)
    
    # Информация о файле
    original_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)
    file_type = Column(String)
    mime_type = Column(String)
    
    # Статус загрузки
    is_uploaded = Column(Boolean, default=False)
    
    # Даты
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    message = relationship("Message", backref="files")

class RecruiterRating(Base):
    __tablename__ = "recruiter_ratings"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    recruiter_id = Column(String, ForeignKey("users.id"))
    employer_id = Column(String, ForeignKey("users.id"))
    job_id = Column(String, ForeignKey("jobs.id"))
    
    # Оценка
    overall_rating = Column(Float, nullable=False)
    communication_rating = Column(Float)
    quality_rating = Column(Float)
    timeliness_rating = Column(Float)
    professionalism_rating = Column(Float)
    
    # Комментарии
    comment = Column(Text)
    pros = Column(Text)
    cons = Column(Text)
    
    # Рекомендации
    would_hire_again = Column(Boolean)
    would_recommend = Column(Boolean)
    
    # Дополнительная информация
    project_duration = Column(Integer)
    project_budget = Column(Float)
    
    # Даты
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    recruiter = relationship("User", back_populates="recruiter_ratings", foreign_keys=[recruiter_id])
    employer = relationship("User", back_populates="employer_ratings", foreign_keys=[employer_id])

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    
    # Основная информация
    type = Column(Enum(NotificationType), nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    
    # Дополнительные данные
    data = Column(Text)
    action_url = Column(String)
    image_url = Column(String)
    
    # Статус
    is_read = Column(Boolean, default=False)
    is_sent = Column(Boolean, default=False)
    channel = Column(String, default="app")
    
    # Связанные объекты
    related_job_id = Column(String)
    related_user_id = Column(String)
    related_application_id = Column(String)
    related_payment_id = Column(String)
    related_message_id = Column(String)
    
    # Даты
    scheduled_for = Column(DateTime)
    sent_at = Column(DateTime)
    read_at = Column(DateTime)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="notifications", foreign_keys=[user_id])