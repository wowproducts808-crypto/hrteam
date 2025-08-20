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
    skills = Column(Text)  # JSON список навыков
    certifications = Column(Text)
    languages = Column(String)  # JSON список языков
    hourly_rate = Column(Float)
    availability = Column(String)  # full-time, part-time, freelance
    
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
    profile_completion = Column(Integer, default=0)  # процент заполненности профиля
    
    # Настройки уведомлений
    email_notifications = Column(Boolean, default=True)
    sms_notifications = Column(Boolean, default=False)
    push_notifications = Column(Boolean, default=True)
    newsletter_subscription = Column(Boolean, default=True)
    
    # Даты
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime)  # soft delete

    # Relationships
    jobs = relationship("Job", back_populates="employer", foreign_keys="Job.employer_id")
    recruiter_applications = relationship("Application", back_populates="recruiter")
    sent_messages = relationship("Message", back_populates="sender", foreign_keys="Message.sender_id")
    received_messages = relationship("Message", back_populates="receiver", foreign_keys="Message.receiver_id")
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
    slug = Column(String, unique=True)  # для SEO-дружественных URL
    description = Column(Text, nullable=False)
    short_description = Column(String)
    requirements = Column(Text)
    benefits = Column(Text)
    responsibilities = Column(Text)
    
    # Локация и тип работы
    location = Column(String)
    remote_work = Column(Boolean, default=False)
    employment_type = Column(String, default="full-time")  # full-time, part-time, contract, freelance
    experience_level = Column(String)  # junior, middle, senior, lead
    
    # Зарплата
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    salary_currency = Column(String, default="тенге")
    salary_type = Column(String, default="monthly")  # monthly, hourly, project
    salary_negotiable = Column(Boolean, default=False)
    
    # Дополнительная информация
    category = Column(String)  # IT, Marketing, Sales, etc.
    tags = Column(Text)  # JSON список тегов
    urgency = Column(String, default="normal")  # urgent, normal, low
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
    
    # Скидки и налоги (опционально)
    discount_amount = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    processing_fee = Column(Float, default=0.0)
    
    # Статус и метод оплаты
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_method = Column(String)  # card, bank_transfer, mobile, etc.
    payment_provider = Column(String)  # stripe, paypal, kaspi, etc.
    
    # Данные транзакции
    transaction_id = Column(String, unique=True)
    payment_system_id = Column(String)  # ID в системе провайдера
    payment_data = Column(Text)  # JSON с дополнительными данными
    
    # Даты
    paid_at = Column(DateTime)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Дополнительные поля для отчетности
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
    
    # Дополнительные поля
    portfolio_urls = Column(Text)  # JSON список ссылок
    attachments = Column(Text)  # JSON список файлов
    questionnaire_answers = Column(Text)  # JSON ответы на вопросы
    
    # Статус и оценка
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING)
    rating = Column(Float)  # оценка от работодателя
    employer_notes = Column(Text)
    recruiter_notes = Column(Text)
    
    # Процесс отбора
    interview_scheduled = Column(DateTime)
    interview_completed = Column(Boolean, default=False)
    test_results = Column(Text)  # JSON результаты тестов
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

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_id = Column(String, ForeignKey("users.id"))
    receiver_id = Column(String, ForeignKey("users.id"))
    
    # Основная информация
    subject = Column(String)
    content = Column(Text, nullable=False)
    message_type = Column(String, default="text")  # text, html, system
    
    # Статус
    is_read = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    is_important = Column(Boolean, default=False)
    
    # Дополнительные поля
    attachments = Column(Text)  # JSON список файлов
    related_job_id = Column(String, ForeignKey("jobs.id"))
    related_application_id = Column(String, ForeignKey("applications.id"))
    
    # Даты
    read_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)

    # Relationships
    sender = relationship("User", back_populates="sent_messages", foreign_keys=[sender_id])
    receiver = relationship("User", back_populates="received_messages", foreign_keys=[receiver_id])

class RecruiterRating(Base):
    __tablename__ = "recruiter_ratings"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    recruiter_id = Column(String, ForeignKey("users.id"))
    employer_id = Column(String, ForeignKey("users.id"))
    job_id = Column(String, ForeignKey("jobs.id"))
    
    # Оценка
    overall_rating = Column(Float, nullable=False)  # общая оценка 1-5
    communication_rating = Column(Float)  # коммуникация
    quality_rating = Column(Float)  # качество работы
    timeliness_rating = Column(Float)  # своевременность
    professionalism_rating = Column(Float)  # профессионализм
    
    # Комментарии
    comment = Column(Text)
    pros = Column(Text)  # плюсы
    cons = Column(Text)  # минусы
    
    # Рекомендации
    would_hire_again = Column(Boolean)
    would_recommend = Column(Boolean)
    
    # Дополнительная информация
    project_duration = Column(Integer)  # в днях
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
    data = Column(Text)  # JSON дополнительные данные
    action_url = Column(String)  # ссылка для действия
    image_url = Column(String)  # картинка для уведомления
    
    # Статус
    is_read = Column(Boolean, default=False)
    is_sent = Column(Boolean, default=False)  # отправлено ли уведомление
    channel = Column(String, default="app")  # app, email, sms, push
    
    # Связанные объекты
    related_job_id = Column(String)
    related_user_id = Column(String)
    related_application_id = Column(String)
    related_payment_id = Column(String)
    related_message_id = Column(String)
    
    # Даты
    scheduled_for = Column(DateTime)  # запланировано на
    sent_at = Column(DateTime)
    read_at = Column(DateTime)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="notifications", foreign_keys=[user_id])
