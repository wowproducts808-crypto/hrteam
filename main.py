from fastapi import FastAPI, Request, Depends, Form, status, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from models import *
from database import SessionLocal, engine, get_db
import bcrypt
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import logging
from typing import Optional
from datetime import datetime, timedelta
import json
import os  # ← Добавьте эту строку


logging.basicConfig(level=logging.INFO)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="!secret")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

Base.metadata.create_all(bind=engine)

# ОБНОВЛЕНО: Динамическое ценообразование
PRICE_MULTIPLIER = 0.7  # 70% от средней зарплаты
MIN_POSTING_PRICE = 3000.0  # Минимальная стоимость размещения

def calculate_posting_price(salary_min: int, salary_max: int, multiplier: float = PRICE_MULTIPLIER) -> float:
    """
    Рассчитывает стоимость размещения вакансии на основе средней зарплаты
    Формула: ((salary_min + salary_max) / 2) * multiplier
    """
    if salary_min < 0 or salary_max < 0:
        return MIN_POSTING_PRICE
    
    if salary_min == 0 and salary_max == 0:
        return MIN_POSTING_PRICE
    
    average_salary = (salary_min + salary_max) / 2
    calculated_price = average_salary * multiplier
    
    return max(calculated_price, MIN_POSTING_PRICE)

def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, user_id: str):
    return db.query(User).filter(User.id == user_id).first()

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = get_user_by_id(db, user_id)
    if user:
        print(f"[DEBUG] get_current_user: {user.name}, user_type: {user.user_type}, value: {getattr(user.user_type, 'value', None)}")
    return user

def get_required_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    print(f"[DEBUG] get_required_user: {user.name}, user_type: {user.user_type}, value: {getattr(user.user_type, 'value', None)}")
    return user

def get_admin_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_required_user(request, db)
    if user.user_type.value != 'admin':
        raise HTTPException(status_code=403, detail="Доступ только для администраторов")
    return user

def get_recruiter_avg_rating(db: Session, recruiter_id: str):
    ratings = db.query(RecruiterRating).filter(RecruiterRating.recruiter_id == recruiter_id).all()
    if ratings:
        return round(sum(r.overall_rating for r in ratings) / len(ratings), 1)
    return None

def get_recruiter_ratings_count(db: Session, recruiter_id: str):
    return db.query(RecruiterRating).filter(RecruiterRating.recruiter_id == recruiter_id).count()

def get_unread_notifications_count(db: Session, user_id: str):
    return db.query(Notification).filter(Notification.user_id == user_id, Notification.is_read == False).count()

def create_notification(db: Session, user_id: str, notification_type: NotificationType, title: str, message: str, related_job_id: str = None, related_user_id: str = None, related_application_id: str = None, related_payment_id: str = None):
    notification = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        related_job_id=related_job_id,
        related_user_id=related_user_id,
        related_application_id=related_application_id,
        related_payment_id=related_payment_id
    )
    db.add(notification)
    db.commit()

def calculate_job_analytics(db: Session, job: Job):
    """Рассчитать аналитику по вакансии"""
    if job.status == JobStatus.COMPLETED and not job.avg_time_to_fill:
        days_to_fill = (datetime.utcnow() - job.created_at).days
        job.avg_time_to_fill = days_to_fill
        job.filled_at = datetime.utcnow()
        db.commit()

def auto_update_job_status(db: Session, job: Job):
    """Автоматическое обновление статуса вакансии"""
    applications_count = db.query(Application).filter(Application.job_id == job.id).count()
    selected_count = db.query(Application).filter(
        Application.job_id == job.id, 
        Application.status.in_([ApplicationStatus.SELECTED, ApplicationStatus.WORKING])
    ).count()
    completed_count = db.query(Application).filter(
        Application.job_id == job.id, 
        Application.status == ApplicationStatus.COMPLETED
    ).count()
    
    old_status = job.status
    
    if completed_count > 0 and job.status != JobStatus.COMPLETED:
        job.status = JobStatus.COMPLETED
        job.status_reason = "Найден подходящий кандидат"
        calculate_job_analytics(db, job)
    elif selected_count > 0 and job.status == JobStatus.OPEN:
        job.status = JobStatus.IN_PROGRESS
        job.status_reason = "Начата работа с рекрутерами"
    elif applications_count >= job.max_applications and job.status == JobStatus.OPEN:
        job.status = JobStatus.IN_PROGRESS
        job.status_reason = "Достигнут лимит откликов"
    
    if old_status != job.status:
        db.commit()
        
        applications = db.query(Application).filter(Application.job_id == job.id).all()
        for app in applications:
            create_notification(
                db,
                app.recruiter_id,
                NotificationType.JOB_STATUS_CHANGE,
                f"Изменен статус вакансии '{job.title}'",
                f"Статус изменен с '{old_status.value}' на '{job.status.value}'. Причина: {job.status_reason}",
                related_job_id=job.id
            )

def get_job_analytics_data(db: Session, employer_id: str):
    """Получить аналитику по вакансиям работодателя"""
    jobs = db.query(Job).filter(Job.employer_id == employer_id).all()
    
    total_jobs = len(jobs)
    completed_jobs = len([j for j in jobs if j.status == JobStatus.COMPLETED])
    avg_time_to_fill = None
    success_rate = 0
    
    if completed_jobs > 0:
        success_rate = round((completed_jobs / total_jobs) * 100, 1)
        filled_jobs = [j for j in jobs if j.avg_time_to_fill]
        if filled_jobs:
            avg_time_to_fill = round(sum(j.avg_time_to_fill for j in filled_jobs) / len(filled_jobs), 1)
    
    return {
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "avg_time_to_fill": avg_time_to_fill,
        "success_rate": success_rate,
        "open_jobs": len([j for j in jobs if j.status == JobStatus.OPEN]),
        "in_progress_jobs": len([j for j in jobs if j.status == JobStatus.IN_PROGRESS])
    }

# Создание дефолтного админа при запуске
@app.on_event("startup")
async def create_default_admin():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.user_type == UserType.ADMIN).first()
        if not admin:
            admin = User(
                email="admin@hrteam.kz",
                name="Администратор",
                hashed_password=get_password_hash("admin123"),
                user_type=UserType.ADMIN,
                company="HRteam",
                location="Алматы"
            )
            db.add(admin)
            db.commit()
            print("✅ Создан администратор: admin@hrteam.kz / admin123")
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
def index(request: Request, current_user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    unread_count = 0
    if current_user:
        unread_count = get_unread_notifications_count(db, current_user.id)
        print(f"[DEBUG] Index: User {current_user.name}, type: {current_user.user_type}, value: {getattr(current_user.user_type, 'value', None)}")
    
    total_jobs = db.query(Job).filter(Job.status == JobStatus.OPEN).count()
    total_recruiters = db.query(User).filter(User.user_type == UserType.RECRUITER).count()
    total_employers = db.query(User).filter(User.user_type == UserType.EMPLOYER).count()
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "current_user": current_user, 
        "unread_count": unread_count,
        "total_jobs": total_jobs,
        "total_recruiters": total_recruiters,
        "total_employers": total_employers
    })

@app.get("/register", response_class=HTMLResponse)
def get_register(request: Request, current_user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    unread_count = 0
    if current_user:
        unread_count = get_unread_notifications_count(db, current_user.id)
    return templates.TemplateResponse("register.html", {"request": request, "current_user": current_user, "unread_count": unread_count})

@app.post("/register")
def post_register(
    request: Request,
    email: str = Form(...),
    name: str = Form(...),
    password: str = Form(...),
    user_type: UserType = Form(...),
    db: Session = Depends(get_db)
):
    if get_user_by_email(db, email):
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email уже зарегистрирован.", "current_user": None, "unread_count": 0})
    
    if user_type == UserType.ADMIN:
        current_user = get_current_user(request, db)
        if not current_user or current_user.user_type != UserType.ADMIN:
            return templates.TemplateResponse("register.html", {"request": request, "error": "Только администратор может создавать админов.", "current_user": current_user, "unread_count": 0})
    
    user = User(
        email=email,
        name=name,
        hashed_password=get_password_hash(password),
        user_type=user_type
    )
    db.add(user)
    db.commit()
    print(f"[DEBUG] Регистрация: {user.name} — {user.user_type} — {getattr(user.user_type, 'value', None)}")
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/login", response_class=HTMLResponse)
def get_login(request: Request, current_user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    unread_count = 0
    if current_user:
        unread_count = get_unread_notifications_count(db, current_user.id)
    return templates.TemplateResponse("login.html", {"request": request, "current_user": current_user, "unread_count": unread_count})

@app.post("/login")
def post_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный email или пароль.", "current_user": None, "unread_count": 0})
    
    user.last_login = datetime.utcnow()
    db.commit()
    
    request.session["user_id"] = user.id
    print(f"[DEBUG] Вход: {user.email} ({user.user_type}, {getattr(user.user_type, 'value', None)})")
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/faq", response_class=HTMLResponse)
def faq(request: Request, current_user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    unread_count = 0
    if current_user:
        unread_count = get_unread_notifications_count(db, current_user.id)
    return templates.TemplateResponse("faq.html", {"request": request, "current_user": current_user, "unread_count": unread_count})

@app.get("/profile", response_class=HTMLResponse)
def get_profile(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    unread_count = get_unread_notifications_count(db, current_user.id)
    
    completed_jobs = []
    if current_user.user_type == UserType.RECRUITER:
        completed_applications = db.query(Application).filter(
            Application.recruiter_id == current_user.id,
            Application.status == ApplicationStatus.COMPLETED
        ).all()
        completed_jobs = [app.job for app in completed_applications]
    elif current_user.user_type == UserType.EMPLOYER:
        completed_jobs = db.query(Job).filter(
            Job.employer_id == current_user.id, 
            Job.status == JobStatus.COMPLETED
        ).all()
    
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "current_user": current_user,
        "unread_count": unread_count,
        "completed_jobs": completed_jobs
    })

@app.post("/profile")
def post_profile(
    request: Request,
    name: str = Form(...),
    experience: str = Form(""),
    specialization: str = Form(""),
    portfolio_url: str = Form(""),
    resume_url: str = Form(""),
    company: str = Form(""),
    location: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user)
):
    user = db.query(User).filter(User.id == current_user.id).first()
    user.name = name
    user.experience = experience
    user.specialization = specialization
    user.portfolio_url = portfolio_url
    user.resume_url = resume_url
    user.company = company
    user.location = location
    user.phone = phone
    
    db.commit()
    return RedirectResponse("/profile", status_code=status.HTTP_303_SEE_OTHER)

# ======================
# АДМИН ПАНЕЛЬ
# ======================

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    unread_count = get_unread_notifications_count(db, current_user.id)
    
    total_users = db.query(User).count()
    total_jobs = db.query(Job).count()
    pending_jobs = db.query(Job).filter(Job.status == JobStatus.PENDING).count()
    total_payments = db.query(Payment).filter(Payment.status == PaymentStatus.PAID).count()
    total_revenue = db.query(func.sum(Payment.amount)).filter(Payment.status == PaymentStatus.PAID).scalar() or 0
    
    pending_jobs_list = db.query(Job).filter(Job.status == JobStatus.PENDING).order_by(Job.created_at.desc()).limit(10).all()
    
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "current_user": current_user,
        "unread_count": unread_count,
        "total_users": total_users,
        "total_jobs": total_jobs,
        "pending_jobs": pending_jobs,
        "total_payments": total_payments,
        "total_revenue": total_revenue,
        "pending_jobs_list": pending_jobs_list
    })

@app.get("/admin/jobs", response_class=HTMLResponse)
def admin_jobs(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    unread_count = get_unread_notifications_count(db, current_user.id)
    
    status_filter = request.query_params.get("status", "")
    query = db.query(Job).join(User, Job.employer_id == User.id)
    
    if status_filter:
        query = query.filter(Job.status == status_filter)
    
    jobs = query.order_by(Job.created_at.desc()).all()
    
    return templates.TemplateResponse("admin/jobs.html", {
        "request": request,
        "current_user": current_user,
        "unread_count": unread_count,
        "jobs": jobs,
        "status_filter": status_filter
    })

@app.post("/admin/jobs/{job_id}/moderate")
def moderate_job(
    job_id: str,
    action: str = Form(...),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    
    if action == "approve":
        job.status = JobStatus.OPEN
        job.moderator_id = current_user.id
        job.moderated_at = datetime.utcnow()
        job.moderation_comment = comment or "Вакансия одобрена"
        
        create_notification(
            db,
            job.employer_id,
            NotificationType.JOB_APPROVED,
            f"Вакансия '{job.title}' одобрена!",
            f"Ваша вакансия прошла модерацию и опубликована на платформе.",
            related_job_id=job.id
        )
        
    elif action == "reject":
        job.status = JobStatus.REJECTED
        job.moderator_id = current_user.id
        job.moderated_at = datetime.utcnow()
        job.moderation_comment = comment or "Вакансия отклонена"
        
        create_notification(
            db,
            job.employer_id,
            NotificationType.JOB_REJECTED,
            f"Вакансия '{job.title}' отклонена",
            f"Ваша вакансия не прошла модерацию. Причина: {comment}",
            related_job_id=job.id
        )
    
    db.commit()
    return RedirectResponse("/admin/jobs", status_code=status.HTTP_303_SEE_OTHER)

# ======================
# СОЗДАНИЕ ВАКАНСИЙ С ДИНАМИЧЕСКОЙ ЦЕНОЙ
# ======================

@app.get("/jobs/new", response_class=HTMLResponse)
def get_new_job(request: Request, current_user: User = Depends(get_required_user), db: Session = Depends(get_db)):
    if current_user.user_type.value != 'employer':
        raise HTTPException(status_code=403, detail="Доступ запрещен. Создавать вакансии могут только работодатели.")
    
    unread_count = get_unread_notifications_count(db, current_user.id)
    return templates.TemplateResponse("new_job.html", {
        "request": request, 
        "current_user": current_user, 
        "unread_count": unread_count,
        "job_price": "рассчитывается автоматически",
        "min_price": MIN_POSTING_PRICE
    })

@app.post("/jobs/new")
def post_new_job(
    request: Request,
    title: str = Form(...),
    short_description: str = Form(...),
    description: str = Form(...),
    requirements: str = Form(""),
    benefits: str = Form(""),
    location: str = Form(""),
    employment_type: str = Form("full-time"),
    experience_level: str = Form("middle"),
    salary_min: str = Form(...),
    salary_max: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user)
):
    if current_user.user_type.value != 'employer':
        raise HTTPException(status_code=403, detail="Доступ запрещен.")

    try:
        # ОБНОВЛЕНО: Парсим зарплаты
        min_salary = int(salary_min) if salary_min.isdigit() else 0
        max_salary = int(salary_max) if salary_max.isdigit() else 0
        
        # НОВОЕ: Рассчитываем динамическую стоимость размещения
        posting_price = calculate_posting_price(min_salary, max_salary)
        
        print(f"[DEBUG] Зарплата: {min_salary}-{max_salary} ₸, Стоимость размещения: {posting_price} ₸")
        
        # Создаем вакансию в статусе DRAFT
        job = Job(
            employer_id=current_user.id,
            title=title,
            short_description=short_description,
            description=description,
            requirements=requirements,
            benefits=benefits,
            location=location,
            employment_type=employment_type,
            experience_level=experience_level,
            salary_min=min_salary,
            salary_max=max_salary,
            status=JobStatus.DRAFT,
            status_reason="Ожидает оплаты",
            max_applications=3
        )
        db.add(job)
        db.commit()
        
        # ОБНОВЛЕНО: Создаем платеж с динамической стоимостью
        payment = Payment(
            job_id=job.id,
            employer_id=current_user.id,
            amount=posting_price,
            currency="KZT",
            status=PaymentStatus.PENDING
        )
        db.add(payment)
        db.commit()
        
        # Перенаправляем на страницу оплаты
        return RedirectResponse(f"/jobs/{job.id}/payment", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Ошибка создания вакансии: {e}")
        unread_count = get_unread_notifications_count(db, current_user.id)
        return templates.TemplateResponse("new_job.html", {
            "request": request, 
            "error": f"Ошибка при создании вакансии: {str(e)}", 
            "current_user": current_user,
            "unread_count": unread_count,
            "job_price": "рассчитывается автоматически",
            "min_price": MIN_POSTING_PRICE
        })

@app.get("/jobs/{job_id}/payment", response_class=HTMLResponse)
def get_job_payment(job_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    job = db.query(Job).filter(Job.id == job_id, Job.employer_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    
    payment = db.query(Payment).filter(Payment.job_id == job_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Платеж не найден")
    
    unread_count = get_unread_notifications_count(db, current_user.id)
    
    return templates.TemplateResponse("payment.html", {
        "request": request,
        "current_user": current_user,
        "unread_count": unread_count,
        "job": job,
        "payment": payment
    })

@app.post("/jobs/{job_id}/payment")
def process_job_payment(
    job_id: str,
    payment_method: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user)
):
    job = db.query(Job).filter(Job.id == job_id, Job.employer_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    
    payment = db.query(Payment).filter(Payment.job_id == job_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Платеж не найден")
    
    payment.status = PaymentStatus.PAID
    payment.payment_method = payment_method
    payment.paid_at = datetime.utcnow()
    payment.transaction_id = f"TXN_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    job.status = JobStatus.PENDING
    job.status_reason = "Ожидает модерации"
    
    db.commit()
    
    create_notification(
        db,
        current_user.id,
        NotificationType.PAYMENT_SUCCESS,
        "Оплата успешно обработана",
        f"Вакансия '{job.title}' оплачена и отправлена на модерацию.",
        related_job_id=job.id,
        related_payment_id=payment.id
    )
    
    admins = db.query(User).filter(User.user_type == UserType.ADMIN).all()
    for admin in admins:
        create_notification(
            db,
            admin.id,
            NotificationType.NEW_JOB,
            "Новая вакансия на модерацию",
            f"Работодатель {current_user.name} создал вакансию '{job.title}' и ожидает модерации.",
            related_job_id=job.id,
            related_user_id=current_user.id
        )
    
    return RedirectResponse("/my/jobs?payment_success=1", status_code=status.HTTP_303_SEE_OTHER)

# СПИСОК ВАКАНСИЙ
@app.get("/jobs", response_class=HTMLResponse)
def list_jobs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
    q: Optional[str] = Query(""),
    salary_min: Optional[str] = Query(""),
    salary_max: Optional[str] = Query(""),
    status: Optional[str] = Query("")
):
    unread_count = 0
    if current_user:
        unread_count = get_unread_notifications_count(db, current_user.id)
    
    # ОБНОВЛЕННАЯ ЛОГИКА: Показываем вакансии с менее 3 выбранными рекрутерами
    if current_user and current_user.user_type == UserType.ADMIN:
        query = db.query(Job)
        if status and status in ["draft", "pending", "open", "paused", "in_progress", "completed", "archived", "rejected"]:
            query = query.filter(Job.status == JobStatus(status))
    else:
        # Подзапрос для подсчета выбранных рекрутеров
        selected_subq = db.query(
            Application.job_id,
            func.count(Application.id).label('selected_count')
        ).filter(
            Application.status.in_([ApplicationStatus.SELECTED, ApplicationStatus.WORKING])
        ).group_by(Application.job_id).subquery()
        
        # Показываем вакансии: OPEN ИЛИ с менее чем 3 выбранными рекрутерами
        query = db.query(Job).outerjoin(
            selected_subq, Job.id == selected_subq.c.job_id
        ).filter(
            or_(
                Job.status == JobStatus.OPEN,
                and_(
                    Job.status == JobStatus.IN_PROGRESS,
                    or_(
                        selected_subq.c.selected_count < 3,
                        selected_subq.c.selected_count == None
                    )
                )
            )
        )

    if q and q.strip():
        search = f"%{q}%"
        query = query.filter(Job.title.ilike(search) | Job.description.ilike(search))
    
    if salary_min and salary_min.isdigit():
        query = query.filter(Job.salary_min >= int(salary_min))
    
    if salary_max and salary_max.isdigit():
        query = query.filter(Job.salary_max <= int(salary_max))

    jobs = query.order_by(Job.created_at.desc()).all()

    jobs_with_status = []
    for job in jobs:
        job.views_count += 1
        
        user_applied = False
        applications_count = db.query(Application).filter(Application.job_id == job.id).count()
        applications_left = max(0, job.max_applications - applications_count)
        
        # НОВОЕ: Подсчитываем выбранных рекрутеров
        selected_recruiters_count = db.query(Application).filter(
            Application.job_id == job.id,
            Application.status.in_([ApplicationStatus.SELECTED, ApplicationStatus.WORKING])
        ).count()
        
        # НОВОЕ: Максимум рекрутеров для вакансии
        max_recruiters = 3
        available_recruiter_slots = max(0, max_recruiters - selected_recruiters_count)
        
        # Загружаем всех выбранных рекрутеров
        selected_applications = db.query(Application).filter(
            Application.job_id == job.id,
            Application.status.in_([ApplicationStatus.SELECTED, ApplicationStatus.WORKING])
        ).all()
        
        selected_recruiters = [app.recruiter for app in selected_applications]
        
        if current_user and current_user.user_type == UserType.RECRUITER:
            user_applied = db.query(Application).filter(
                Application.job_id == job.id,
                Application.recruiter_id == current_user.id
            ).first() is not None
        
        # ОБНОВЛЕННОЕ УСЛОВИЕ: можно откликаться, если есть места и меньше 3 выбранных рекрутеров
        can_apply = (
            applications_left > 0 and 
            job.status == JobStatus.OPEN and 
            not user_applied and
            selected_recruiters_count < max_recruiters
        )
        
        jobs_with_status.append({
            "job": job,
            "user_applied": user_applied,
            "applications_count": applications_count,
            "applications_left": applications_left,
            "can_apply": can_apply,
            "selected_recruiters": selected_recruiters,           # НОВОЕ
            "selected_recruiters_count": selected_recruiters_count, # НОВОЕ
            "max_recruiters": max_recruiters,                    # НОВОЕ
            "available_recruiter_slots": available_recruiter_slots # НОВОЕ
        })
    
    db.commit()

    return templates.TemplateResponse("jobs.html", {
        "request": request,
        "jobs_with_status": jobs_with_status,
        "current_user": current_user,
        "unread_count": unread_count,
        "q": q,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "status": status
    })


@app.get("/jobs/{job_id}/apply", response_class=HTMLResponse)
def get_apply(job_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    if current_user.user_type.value != 'recruiter':
        raise HTTPException(status_code=403, detail="Доступ запрещен. Откликаться могут только рекрутеры.")
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return RedirectResponse("/jobs", status_code=status.HTTP_404_NOT_FOUND)
    
    if job.status != JobStatus.OPEN:
        return RedirectResponse(f"/jobs/{job_id}?error=job_not_open", status_code=status.HTTP_303_SEE_OTHER)
    
    applications_count = db.query(Application).filter(Application.job_id == job_id).count()
    
    if applications_count >= job.max_applications:
        return RedirectResponse(f"/jobs/{job_id}?error=max_applications", status_code=status.HTTP_303_SEE_OTHER)
    
    unread_count = get_unread_notifications_count(db, current_user.id)
    return templates.TemplateResponse("apply.html", {
        "request": request, 
        "job": job, 
        "current_user": current_user, 
        "unread_count": unread_count
    })

@app.post("/jobs/{job_id}/apply")
def post_apply(
    job_id: str,
    request: Request,
    cover_letter: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user)
):
    if current_user.user_type.value != 'recruiter':
        raise HTTPException(status_code=403, detail="Доступ запрещен. Откликаться могут только рекрутеры.")
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return RedirectResponse("/jobs", status_code=status.HTTP_404_NOT_FOUND)
    
    if job.status != JobStatus.OPEN:
        return RedirectResponse(f"/jobs/{job_id}?error=job_not_open", status_code=status.HTTP_303_SEE_OTHER)
    
    applications_count = db.query(Application).filter(Application.job_id == job_id).count()
    
    if applications_count >= job.max_applications:
        return RedirectResponse(f"/jobs/{job_id}?error=max_applications", status_code=status.HTTP_303_SEE_OTHER)
    
    existing_application = db.query(Application).filter(
        Application.job_id == job_id,
        Application.recruiter_id == current_user.id
    ).first()
    
    if existing_application:
        unread_count = get_unread_notifications_count(db, current_user.id)
        return templates.TemplateResponse("apply.html", {
            "request": request,
            "job": job,
            "current_user": current_user,
            "unread_count": unread_count,
            "error": "Вы уже откликнулись на эту вакансию!"
        })
    
    application = Application(
        job_id=job_id,
        recruiter_id=current_user.id,
        cover_letter=cover_letter,
        status=ApplicationStatus.PENDING
    )
    db.add(application)
    db.commit()
    
    auto_update_job_status(db, job)
    
    create_notification(
        db,
        job.employer_id,
        NotificationType.NEW_APPLICATION,
        f"Новый отклик на '{job.title}'",
        f"Рекрутер {current_user.name} откликнулся на вашу вакансию",
        related_job_id=job_id,
        related_user_id=current_user.id,
        related_application_id=application.id
    )
    
    return RedirectResponse(f"/jobs/{job_id}?applied=success", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(
    job_id: str, 
    request: Request, 
    db: Session = Depends(get_db), 
    current_user: Optional[User] = Depends(get_current_user)
):
    unread_count = 0
    if current_user:
        unread_count = get_unread_notifications_count(db, current_user.id)
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return RedirectResponse("/jobs", status_code=status.HTTP_404_NOT_FOUND)
    
    if job.status in [JobStatus.DRAFT, JobStatus.PENDING, JobStatus.REJECTED]:
        if not current_user or (current_user.user_type != UserType.ADMIN and current_user.id != job.employer_id):
            return RedirectResponse("/jobs", status_code=status.HTTP_404_NOT_FOUND)
    
    applications_count = db.query(Application).filter(Application.job_id == job_id).count()
    applications_left = max(0, job.max_applications - applications_count)
    
    user_applied = False
    if current_user and current_user.user_type == UserType.RECRUITER:
        user_applied = db.query(Application).filter(
            Application.job_id == job_id,
            Application.recruiter_id == current_user.id
        ).first() is not None
    
    can_apply = applications_left > 0 and job.status == JobStatus.OPEN and not user_applied
    
    return templates.TemplateResponse("job_detail.html", {
        "request": request,
        "job": job,
        "current_user": current_user,
        "unread_count": unread_count,
        "applications_count": applications_count,
        "applications_left": applications_left,
        "user_applied": user_applied,
        "can_apply": can_apply
    })

# УПРАВЛЕНИЕ ВАКАНСИЯМИ РАБОТОДАТЕЛЕМ
@app.get("/my/jobs", response_class=HTMLResponse)
def my_jobs(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    if current_user.user_type.value != 'employer':
        raise HTTPException(status_code=403, detail="Доступ запрещен. Доступно только работодателям.")
    
    unread_count = get_unread_notifications_count(db, current_user.id)
    jobs = db.query(Job).filter(Job.employer_id == current_user.id).order_by(Job.created_at.desc()).all()
    
    jobs_data = []
    for job in jobs:
        applications = db.query(Application).filter(Application.job_id == job.id).all()
        apps_data = []
        for app in applications:
            avg_rating = get_recruiter_avg_rating(db, app.recruiter_id)
            ratings_count = get_recruiter_ratings_count(db, app.recruiter_id)
            apps_data.append({
                "app": app, 
                "avg_rating": avg_rating, 
                "ratings_count": ratings_count
            })
        jobs_data.append({"job": job, "applications": apps_data})
    
    analytics = get_job_analytics_data(db, current_user.id)
    
    return templates.TemplateResponse("my_jobs.html", {
        "request": request, 
        "jobs_data": jobs_data, 
        "current_user": current_user, 
        "unread_count": unread_count,
        "analytics": analytics
    })

@app.post("/jobs/{job_id}/status")
def change_job_status(
    job_id: str,
    new_status: JobStatus = Form(...),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user)
):
    job = db.query(Job).filter(Job.id == job_id, Job.employer_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    
    old_status = job.status
    job.status = new_status
    job.status_reason = reason if reason else f"Изменено работодателем"
    
    if new_status == JobStatus.COMPLETED:
        calculate_job_analytics(db, job)
    
    db.commit()
    
    applications = db.query(Application).filter(Application.job_id == job_id).all()
    for app in applications:
        create_notification(
            db,
            app.recruiter_id,
            NotificationType.JOB_STATUS_CHANGE,
            f"Изменен статус вакансии '{job.title}'",
            f"Статус изменен с '{old_status.value}' на '{new_status.value}'. Причина: {job.status_reason}",
            related_job_id=job_id,
            related_user_id=current_user.id
        )
    
    return RedirectResponse("/my/jobs", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/applications/{application_id}/status")
def change_application_status(
    application_id: str,
    new_status: ApplicationStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user)
):
    print(f"[DEBUG] Получен запрос на изменение статуса: application_id={application_id}, new_status={new_status}")
    
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Отклик не найден")

    job = db.query(Job).filter(Job.id == application.job_id, Job.employer_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=403, detail="Доступ запрещен")

    # Проверяем лимит выбранных рекрутеров
    if new_status in [ApplicationStatus.SELECTED, ApplicationStatus.WORKING]:
        selected_count = db.query(Application).filter(
            Application.job_id == job.id,
            Application.status.in_([ApplicationStatus.SELECTED, ApplicationStatus.WORKING]),
            Application.id != application_id  # исключаем текущую заявку
        ).count()
        
        if selected_count >= 3:
            print(f"[ERROR] Достигнут лимит в 3 рекрутера для вакансии {job.id}")
            raise HTTPException(status_code=400, detail="Достигнут максимальный лимит в 3 рекрутера")

    old_status = application.status
    print(f"[DEBUG] Изменение статуса заявки {application_id}: {old_status} -> {new_status}")
    
    application.status = new_status
    
    # ОБНОВЛЕННАЯ ЛОГИКА: Завершаем вакансию только когда выбрано 3 рекрутера
    selected_count_after = db.query(Application).filter(
        Application.job_id == job.id,
        Application.status.in_([ApplicationStatus.SELECTED, ApplicationStatus.WORKING])
    ).count()
    
    if selected_count_after >= 3 and job.status != JobStatus.COMPLETED:
        job.status = JobStatus.COMPLETED
        job.status_reason = "Найдены все 3 рекрутера"
        calculate_job_analytics(db, job)
        print(f"[DEBUG] Вакансия {job.id} завершена - найдены все 3 рекрутера")
    elif selected_count_after > 0 and job.status == JobStatus.OPEN:
        job.status = JobStatus.IN_PROGRESS
        job.status_reason = f"Выбрано {selected_count_after} из 3 рекрутеров"
        print(f"[DEBUG] Вакансия {job.id} в процессе - выбрано {selected_count_after}/3")
    
    try:
        db.commit()
        print(f"[SUCCESS] Статус успешно изменен: {application.status}")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Ошибка при сохранении: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при сохранении изменений")
    
    # Уведомление рекрутера
    status_messages = {
        ApplicationStatus.PENDING: "на рассмотрении",
        ApplicationStatus.SELECTED: "выбран для работы",
        ApplicationStatus.WORKING: "работает над вакансией", 
        ApplicationStatus.COMPLETED: "успешно завершил работу",
        ApplicationStatus.REJECTED: "отклонен"
    }
    
    create_notification(
        db,
        application.recruiter_id,
        NotificationType.APPLICATION_STATUS_CHANGE,
        f"Изменен статус вашего отклика",
        f"Ваш отклик на вакансию '{job.title}' {status_messages[new_status]}",
        related_job_id=job.id,
        related_user_id=current_user.id,
        related_application_id=application_id
    )
    
    return RedirectResponse("/my/jobs", status_code=status.HTTP_303_SEE_OTHER)



@app.post("/applications/{application_id}/status")
def change_application_status(
    application_id: str,
    new_status: ApplicationStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user)
):
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Отклик не найден")
    
    job = db.query(Job).filter(Job.id == application.job_id, Job.employer_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    old_status = application.status
    application.status = new_status
    
    if new_status == ApplicationStatus.COMPLETED:
        job.winner_application_id = application_id
        if job.status != JobStatus.COMPLETED:
            job.status = JobStatus.COMPLETED
            job.status_reason = "Найден подходящий кандидат"
            calculate_job_analytics(db, job)
    
    db.commit()
    
    auto_update_job_status(db, job)
    
    status_messages = {
        ApplicationStatus.PENDING: "на рассмотрении",
        ApplicationStatus.SELECTED: "выбран для работы",
        ApplicationStatus.WORKING: "работает над вакансией", 
        ApplicationStatus.COMPLETED: "успешно завершил работу",
        ApplicationStatus.REJECTED: "отклонен"
    }
    
    create_notification(
        db,
        application.recruiter_id,
        NotificationType.APPLICATION_STATUS_CHANGE,
        f"Изменен статус вашего отклика",
        f"Ваш отклик на вакансию '{job.title}' {status_messages[new_status]}",
        related_job_id=job.id,
        related_user_id=current_user.id,
        related_application_id=application_id
    )
    
    return RedirectResponse("/my/jobs", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/my/applications", response_class=HTMLResponse)
def my_applications(
    request: Request, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_required_user),
    status: Optional[str] = Query(""),
    order: Optional[str] = Query("desc")
):
    if current_user.user_type.value != 'recruiter':
        raise HTTPException(status_code=403, detail="Доступ запрещен. Доступно только рекрутерам.")
    
    unread_count = get_unread_notifications_count(db, current_user.id)
    
    query = db.query(Application).filter(Application.recruiter_id == current_user.id).join(Job)
    
    if status and status in ["pending", "selected", "working", "completed", "rejected"]:
        query = query.filter(Application.status == ApplicationStatus(status))
    
    if order == "asc":
        applications = query.order_by(Application.created_at.asc()).all()
    else:
        applications = query.order_by(Application.created_at.desc()).all()
    
    total_applications = len(applications)
    pending_applications = len([app for app in applications if app.status == ApplicationStatus.PENDING])
    selected_applications = len([app for app in applications if app.status == ApplicationStatus.SELECTED])
    working_applications = len([app for app in applications if app.status == ApplicationStatus.WORKING])
    completed_applications = len([app for app in applications if app.status == ApplicationStatus.COMPLETED])
    rejected_applications = len([app for app in applications if app.status == ApplicationStatus.REJECTED])
    
    return templates.TemplateResponse("my_applications.html", {
        "request": request,
        "applications": applications,
        "current_user": current_user,
        "unread_count": unread_count,
        "status": status,
        "order": order,
        "total_applications": total_applications,
        "pending_applications": pending_applications,
        "selected_applications": selected_applications,
        "working_applications": working_applications,
        "completed_applications": completed_applications,
        "rejected_applications": rejected_applications
    })

@app.get("/messages", response_class=HTMLResponse)
def messages(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    unread_count = get_unread_notifications_count(db, current_user.id)
    messages_sent = db.query(Message).filter(Message.sender_id == current_user.id).order_by(Message.created_at.desc()).all()
    messages_received = db.query(Message).filter(Message.receiver_id == current_user.id).order_by(Message.created_at.desc()).all()
    
    users = db.query(User).filter(User.id != current_user.id).all()
    
    return templates.TemplateResponse("messages.html", {
        "request": request, 
        "messages_sent": messages_sent, 
        "messages_received": messages_received, 
        "current_user": current_user,
        "users": users,
        "unread_count": unread_count
    })

@app.post("/messages/send")
def send_message(
    request: Request,
    receiver_id: str = Form(...),
    content: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user)
):
    receiver = db.query(User).filter(User.id == receiver_id).first()
    if not receiver:
        return RedirectResponse("/messages?error=user_not_found", status_code=status.HTTP_303_SEE_OTHER)
    
    message = Message(sender_id=current_user.id, receiver_id=receiver_id, content=content)
    db.add(message)
    db.commit()
    
    create_notification(
        db,
        receiver_id,
        NotificationType.NEW_MESSAGE,
        f"Новое сообщение от {current_user.name}",
        f"Получено сообщение: {content[:50]}{'...' if len(content) > 50 else ''}",
        related_user_id=current_user.id
    )
    
    return RedirectResponse("/messages", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/messages/to/{user_id}", response_class=HTMLResponse)
def message_to_user(user_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    recipient = db.query(User).filter(User.id == user_id).first()
    if not recipient:
        return RedirectResponse("/messages", status_code=status.HTTP_404_NOT_FOUND)
    
    unread_count = get_unread_notifications_count(db, current_user.id)
    return templates.TemplateResponse("send_message.html", {
        "request": request,
        "recipient": recipient,
        "current_user": current_user,
        "unread_count": unread_count
    })

@app.get("/notifications", response_class=HTMLResponse)
def notifications(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    unread_count = get_unread_notifications_count(db, current_user.id)
    notifications = db.query(Notification).filter(Notification.user_id == current_user.id).order_by(Notification.created_at.desc()).all()
    
    return templates.TemplateResponse("notifications.html", {
        "request": request,
        "notifications": notifications,
        "current_user": current_user,
        "unread_count": unread_count
    })

@app.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    notification = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == current_user.id).first()
    if notification:
        notification.is_read = True
        db.commit()
    return RedirectResponse("/notifications", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/notifications/read-all")
def mark_all_notifications_read(db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    db.query(Notification).filter(Notification.user_id == current_user.id, Notification.is_read == False).update({"is_read": True})
    db.commit()
    return RedirectResponse("/notifications", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/rate_recruiter/{recruiter_id}", response_class=HTMLResponse)
def get_rate_recruiter(recruiter_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    if current_user.user_type.value != 'employer':
        raise HTTPException(status_code=403, detail="Доступ запрещен. Оценивать могут только работодатели.")
    
    recruiter = db.query(User).filter(User.id == recruiter_id, User.user_type == UserType.RECRUITER).first()
    if not recruiter:
        return RedirectResponse("/", status_code=status.HTTP_404_NOT_FOUND)
    
    unread_count = get_unread_notifications_count(db, current_user.id)
    existing_rating = db.query(RecruiterRating).filter(
        RecruiterRating.recruiter_id == recruiter_id,
        RecruiterRating.employer_id == current_user.id
    ).first()
    
    return templates.TemplateResponse("rate_recruiter.html", {
        "request": request, 
        "recruiter": recruiter, 
        "current_user": current_user,
        "existing_rating": existing_rating,
        "unread_count": unread_count
    })

@app.post("/rate_recruiter/{recruiter_id}")
def post_rate_recruiter(
    recruiter_id: str,
    request: Request,
    rating: float = Form(...),
    comment: str = Form(""),
    job_id: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user)
):
    if current_user.user_type.value != 'employer':
        raise HTTPException(status_code=403, detail="Доступ запрещен. Оценивать могут только работодатели.")
    
    recruiter = db.query(User).filter(User.id == recruiter_id, User.user_type == UserType.RECRUITER).first()
    if not recruiter:
        return RedirectResponse("/", status_code=status.HTTP_404_NOT_FOUND)
    
    existing_rating = db.query(RecruiterRating).filter(
        RecruiterRating.recruiter_id == recruiter_id,
        RecruiterRating.employer_id == current_user.id
    ).first()
    
    if existing_rating:
        existing_rating.overall_rating = rating
        existing_rating.comment = comment
        if job_id:
            existing_rating.job_id = job_id
    else:
        new_rating = RecruiterRating(
            recruiter_id=recruiter_id,
            employer_id=current_user.id,
            job_id=job_id,
            overall_rating=rating,
            comment=comment
        )
        db.add(new_rating)
    
    db.commit()
    
    create_notification(
        db,
        recruiter_id,
        NotificationType.NEW_RATING,
        f"Новая оценка от {current_user.name}",
        f"Вы получили оценку {rating}/5.0 от работодателя {current_user.name}",
        related_user_id=current_user.id
    )
    
    return RedirectResponse("/my/jobs", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/recruiter/{recruiter_id}", response_class=HTMLResponse)
def recruiter_profile(recruiter_id: str, request: Request, db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user)):
    recruiter = db.query(User).filter(User.id == recruiter_id, User.user_type == UserType.RECRUITER).first()
    if not recruiter:
        return RedirectResponse("/", status_code=status.HTTP_404_NOT_FOUND)
    
    unread_count = 0
    if current_user:
        unread_count = get_unread_notifications_count(db, current_user.id)
    
    ratings = db.query(RecruiterRating).filter(RecruiterRating.recruiter_id == recruiter_id).order_by(RecruiterRating.created_at.desc()).all()
    avg_rating = get_recruiter_avg_rating(db, recruiter_id)
    ratings_count = len(ratings)
    
    return templates.TemplateResponse("recruiter_profile.html", {
        "request": request,
        "recruiter": recruiter,
        "ratings": ratings,
        "avg_rating": avg_rating,
        "ratings_count": ratings_count,
        "current_user": current_user,
        "unread_count": unread_count
    })

@app.get("/top-recruiters", response_class=HTMLResponse)
def top_recruiters(request: Request, db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user)):
    unread_count = 0
    if current_user:
        unread_count = get_unread_notifications_count(db, current_user.id)
    
    recruiters = db.query(User).filter(User.user_type == UserType.RECRUITER).all()
    
    recruiter_stats = []
    for rec in recruiters:
        ratings = db.query(RecruiterRating).filter(RecruiterRating.recruiter_id == rec.id).all()
        if ratings:
            avg_rating = round(sum(r.overall_rating for r in ratings) / len(ratings), 1)
            completed_projects = len([r for r in ratings if r.job_id])
            recruiter_stats.append({
                "recruiter": rec,
                "avg_rating": avg_rating,
                "ratings_count": len(ratings),
                "completed_projects": completed_projects
            })
    
    top_recruiters_list = sorted(recruiter_stats, key=lambda x: (-x["avg_rating"], -x["ratings_count"]))[:10]
    
    return templates.TemplateResponse("top_recruiters.html", {
        "request": request,
        "top_recruiters": top_recruiters_list,
        "current_user": current_user,
        "unread_count": unread_count
    })

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
