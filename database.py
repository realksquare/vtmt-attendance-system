"""
Database module using SQLAlchemy ORM for SQLite storage.
Handles Students, Encrypted Face Templates, Timetable Slots, Hourly Attendance, Unknown Faces,
Staff Members (PIN Auth), and Staff Activity Logs.
"""

from datetime import datetime, date, time
from typing import List, Optional, Tuple
import numpy as np

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, Time, LargeBinary, ForeignKey, create_engine
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from config import DATABASE_URL, INSIGHTFACE_MODEL_NAME, DEFAULT_TIMETABLE_SLOTS
from encrypt import get_or_create_key, encrypt_embedding, decrypt_embedding

Base = declarative_base()


class Student(Base):
    __tablename__ = "students"

    student_id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    department = Column(String(100), nullable=False)
    year = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    templates = relationship("FaceTemplate", back_populates="student", cascade="all, delete-orphan")
    hourly_attendance = relationship("HourlyAttendance", back_populates="student", cascade="all, delete-orphan")


class FaceTemplate(Base):
    __tablename__ = "face_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(50), ForeignKey("students.student_id"), nullable=False)
    encrypted_embedding = Column(LargeBinary, nullable=False)
    nonce = Column(LargeBinary, nullable=False)
    tag = Column(LargeBinary, nullable=False)
    model_version = Column(String(50), default=INSIGHTFACE_MODEL_NAME)
    created_at = Column(DateTime, default=datetime.now)

    student = relationship("Student", back_populates="templates")


class TimetableSlot(Base):
    __tablename__ = "timetable_slots"

    slot_id = Column(String(50), primary_key=True)
    start_time = Column(String(10), nullable=False)  # HH:MM
    end_time = Column(String(10), nullable=False)    # HH:MM
    subject = Column(String(100), nullable=False)
    department = Column(String(100), default="All")
    year = Column(String(20), default="All")
    staff_id = Column(String(50), nullable=True)


class HourlyAttendance(Base):
    __tablename__ = "hourly_attendance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(50), ForeignKey("students.student_id"), nullable=False)
    date = Column(Date, nullable=False, default=date.today)
    slot_id = Column(String(50), ForeignKey("timetable_slots.slot_id"), nullable=False)
    
    # First 5 mins (Window A)
    window_a_status = Column(String(20), default="ABSENT")
    window_a_time = Column(String(20), nullable=True)
    window_a_confidence = Column(Float, default=0.0)

    # Middle 5 mins (Window B)
    window_b_status = Column(String(20), default="ABSENT")
    window_b_time = Column(String(20), nullable=True)
    window_b_confidence = Column(Float, default=0.0)

    # Last 5 mins (Window C)
    window_c_status = Column(String(20), default="ABSENT")
    window_c_time = Column(String(20), nullable=True)
    window_c_confidence = Column(Float, default=0.0)

    # Final Combined Status & Override
    final_status = Column(String(30), default="ABSENT")
    remarks = Column(String(255), default="Automated")

    student = relationship("Student", back_populates="hourly_attendance")


class UnknownFace(Base):
    __tablename__ = "unknown_faces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, default=date.today)
    slot_id = Column(String(50), nullable=False)
    window = Column(String(20), nullable=False)
    timestamp = Column(String(20), nullable=False)
    image_path = Column(String(255), nullable=False)
    reviewed = Column(String(10), default="NO")


class StaffMember(Base):
    __tablename__ = "staff_members"

    staff_id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    department = Column(String(100), nullable=False)
    role = Column(String(50), default="TEACHING") # TEACHING, NON_TEACHING, ADMIN
    pin_code = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class StaffFaceTemplate(Base):
    __tablename__ = "staff_face_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    staff_id = Column(String(50), ForeignKey("staff_members.staff_id"), nullable=False)
    encrypted_embedding = Column(LargeBinary, nullable=False)
    nonce = Column(LargeBinary, nullable=False)
    tag = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class StaffAttendance(Base):
    __tablename__ = "staff_attendance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False)
    staff_id = Column(String(50), ForeignKey("staff_members.staff_id"), nullable=False)
    check_in_time = Column(String(10), nullable=True)
    check_out_time = Column(String(10), nullable=True)
    status = Column(String(20), default="ABSENT")
    confidence = Column(Float, default=0.0)
    remarks = Column(String(200), default="Automated")


class StaffActivityLog(Base):
    __tablename__ = "staff_activity_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    staff_id = Column(String(50), nullable=False)
    staff_name = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False)
    details = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=datetime.now)


engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create tables and seed default timetable & staff PINs if empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(TimetableSlot).count() == 0:
            for start, end, label in DEFAULT_TIMETABLE_SLOTS:
                if "Skipped" in label:
                    continue
                slot_id = f"SLOT_{start.replace(':', '')}_{end.replace(':', '')}"
                slot = TimetableSlot(slot_id=slot_id, start_time=start, end_time=end, subject=label)
                db.add(slot)
            db.commit()

        if db.query(StaffMember).count() == 0:
            admin = StaffMember(staff_id="ADM01", name="System Administrator", department="Administration", pin_code="9999", role="ADMIN")
            staff1 = StaffMember(staff_id="STF01", name="Prof. Sharma", department="Computer Science", pin_code="1234", role="STAFF")
            staff2 = StaffMember(staff_id="STF02", name="Dr. Verma", department="Information Technology", pin_code="5678", role="STAFF")
            db.add_all([admin, staff1, staff2])
            db.commit()
    finally:
        db.close()


def authenticate_pin(pin_code: str) -> Optional[StaffMember]:
    """Validate 4-digit numerical PIN code."""
    db = SessionLocal()
    try:
        staff = db.query(StaffMember).filter(StaffMember.pin_code == pin_code).first()
        if staff:
            log_activity(staff.staff_id, staff.name, "PIN Login", "Logged into Web App")
        return staff
    finally:
        db.close()


def log_activity(staff_id: str, staff_name: str, action: str, details: str = ""):
    """Record staff action in activity log."""
    db = SessionLocal()
    try:
        log = StaffActivityLog(staff_id=staff_id, staff_name=staff_name, action=action, details=details)
        db.add(log)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error logging staff activity: {e}")
    finally:
        db.close()


def add_student_with_embedding(
    student_id: str,
    name: str,
    department: str,
    year: str,
    embedding: np.ndarray,
    aes_key: bytes
) -> bool:
    """Register student and save encrypted embedding template."""
    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.student_id == student_id).first()
        if not student:
            student = Student(student_id=student_id, name=name, department=department, year=year)
            db.add(student)
        
        ciphertext, nonce, tag = encrypt_embedding(embedding, aes_key)
        template = FaceTemplate(
            student_id=student_id,
            encrypted_embedding=ciphertext,
            nonce=nonce,
            tag=tag
        )
        db.add(template)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Database error while enrolling student: {e}")
        return False
    finally:
        db.close()


def add_staff_member_with_embedding(
    staff_id: str,
    name: str,
    department: str,
    role: str,
    pin_code: str,
    embedding: Optional[np.ndarray],
    aes_key: Optional[bytes],
    admin_name: str = "Admin"
) -> bool:
    """Enroll new staff member with credentials and optional encrypted face embedding."""
    db = SessionLocal()
    try:
        existing = db.query(StaffMember).filter(StaffMember.staff_id == staff_id).first()
        if existing:
            return False

        staff = StaffMember(
            staff_id=staff_id.strip(),
            name=name.strip(),
            department=department.strip(),
            role=role.strip().upper(),
            pin_code=pin_code.strip()
        )
        db.add(staff)

        if embedding is not None and aes_key is not None:
            ciphertext, nonce, tag = encrypt_embedding(embedding, aes_key)
            template = StaffFaceTemplate(
                staff_id=staff_id.strip(),
                encrypted_embedding=ciphertext,
                nonce=nonce,
                tag=tag
            )
            db.add(template)

        db.commit()
        log_activity(admin_name, admin_name, "Enroll Staff", f"Enrolled staff '{name}' ({staff_id}) with PIN {pin_code}")
        return True
    except Exception as e:
        db.rollback()
        print(f"Error adding staff member: {e}")
        return False
    finally:
        db.close()


def update_staff_member(
    staff_id: str,
    name: str,
    department: str,
    role: str,
    pin_code: str,
    new_embedding: Optional[np.ndarray] = None,
    aes_key: Optional[bytes] = None,
    admin_name: str = "Admin"
) -> bool:
    """Update staff member credentials, details, and optional face embedding."""
    db = SessionLocal()
    try:
        staff = db.query(StaffMember).filter(StaffMember.staff_id == staff_id).first()
        if not staff:
            return False

        staff.name = name.strip()
        staff.department = department.strip()
        staff.role = role.strip().upper()
        if pin_code:
            staff.pin_code = pin_code.strip()

        if new_embedding is not None and aes_key is not None:
            db.query(StaffFaceTemplate).filter(StaffFaceTemplate.staff_id == staff_id).delete()
            ciphertext, nonce, tag = encrypt_embedding(new_embedding, aes_key)
            template = StaffFaceTemplate(
                staff_id=staff_id,
                encrypted_embedding=ciphertext,
                nonce=nonce,
                tag=tag
            )
            db.add(template)

        db.commit()
        log_activity(admin_name, admin_name, "Update Staff Profile", f"Updated details for staff '{name}' ({staff_id})")
        return True
    except Exception as e:
        db.rollback()
        print(f"Error updating staff member: {e}")
        return False
    finally:
        db.close()


def delete_staff_member(staff_id: str, admin_name: str = "Admin") -> bool:
    """Delete staff member, encrypted face templates, and staff attendance logs."""
    db = SessionLocal()
    try:
        staff = db.query(StaffMember).filter(StaffMember.staff_id == staff_id).first()
        if not staff:
            return False

        s_name = staff.name
        db.query(StaffFaceTemplate).filter(StaffFaceTemplate.staff_id == staff_id).delete()
        db.query(StaffAttendance).filter(StaffAttendance.staff_id == staff_id).delete()
        db.delete(staff)
        db.commit()

        log_activity(admin_name, admin_name, "Delete Staff Member", f"Deleted staff member '{s_name}' ({staff_id})")
        return True
    except Exception as e:
        db.rollback()
        print(f"Error deleting staff member: {e}")
        return False
    finally:
        db.close()


def get_all_staff_members() -> List[dict]:
    """Retrieve list of all registered staff members."""
    db = SessionLocal()
    try:
        staff_list = db.query(StaffMember).order_by(StaffMember.name).all()
        return [
            {
                "staff_id": s.staff_id,
                "name": s.name,
                "department": s.department,
                "role": s.role,
                "pin_code": s.pin_code
            }
            for s in staff_list
        ]
    finally:
        db.close()


def get_staff_attendance_matrix(target_date: Optional[str] = None) -> dict:
    """Fetch staff attendance log records for a given date."""
    if target_date is None:
        target_date = date.today().strftime("%Y-%m-%d")

    db = SessionLocal()
    try:
        staff_members = db.query(StaffMember).order_by(StaffMember.name).all()
        records = []
        for s in staff_members:
            att = db.query(StaffAttendance).filter(
                StaffAttendance.staff_id == s.staff_id,
                StaffAttendance.date == target_date
            ).first()

            records.append({
                "staff_id": s.staff_id,
                "name": s.name,
                "department": s.department,
                "role": s.role,
                "check_in_time": att.check_in_time if (att and att.check_in_time) else "-",
                "check_out_time": att.check_out_time if (att and att.check_out_time) else "-",
                "status": att.status if att else "ABSENT",
                "confidence": round((att.confidence or 0.0) * 100, 1) if att else 0.0,
                "remarks": att.remarks if att else "Automated"
            })

        return {
            "date": target_date,
            "matrix": records
        }
    finally:
        db.close()


def delete_student(student_id: str, staff_name: str = "Staff") -> bool:
    """Delete student profile, encrypted face templates, and attendance records."""
    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.student_id == student_id).first()
        if not student:
            return False
        
        s_name = student.name
        db.delete(student)
        db.commit()

        log_activity(staff_name, staff_name, "Delete Student", f"Deleted student '{s_name}' ({student_id})")
        return True
    except Exception as e:
        db.rollback()
        print(f"Error deleting student: {e}")
        return False
    finally:
        db.close()


def update_student_profile(
    student_id: str,
    name: str,
    department: str,
    year: str,
    new_embedding: Optional[np.ndarray] = None,
    aes_key: Optional[bytes] = None,
    staff_name: str = "Staff"
) -> bool:
    """Update student metadata and optionally re-encrypt face embedding template."""
    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.student_id == student_id).first()
        if not student:
            return False

        student.name = name.strip()
        student.department = department.strip()
        student.year = year.strip()

        if new_embedding is not None and aes_key is not None:
            # Delete old face templates for this student and save new encrypted template
            db.query(FaceTemplate).filter(FaceTemplate.student_id == student_id).delete()
            ciphertext, nonce, tag = encrypt_embedding(new_embedding, aes_key)
            template = FaceTemplate(
                student_id=student_id,
                encrypted_embedding=ciphertext,
                nonce=nonce,
                tag=tag
            )
            db.add(template)

        db.commit()
        log_activity(staff_name, staff_name, "Update Student Profile", f"Updated details/embedding for '{name}' ({student_id})")
        return True
    except Exception as e:
        db.rollback()
        print(f"Error updating student profile: {e}")
        return False
    finally:
        db.close()


def update_timetable_slots(slots_data: List[dict], staff_name: str = "Staff") -> bool:
    """Clear existing timetable slots and insert new customized slots."""
    db = SessionLocal()
    try:
        db.query(TimetableSlot).delete()
        for idx, item in enumerate(slots_data):
            start = item.get("start_time", "09:00").strip()
            end = item.get("end_time", "10:00").strip()
            subj = item.get("subject", f"Lecture {idx+1}").strip()
            dept = item.get("department", "All").strip()
            yr = item.get("year", "All").strip()
            stf_id = item.get("staff_id", None)
            
            slot_id = f"SLOT_{start.replace(':', '')}_{end.replace(':', '')}"
            
            slot = TimetableSlot(
                slot_id=slot_id, start_time=start, end_time=end, subject=subj,
                department=dept, year=yr, staff_id=stf_id
            )
            db.add(slot)

        db.commit()
        log_activity(staff_name, staff_name, "Update Timetable", f"Configured {len(slots_data)} custom timetable slot(s)")
        return True
    except Exception as e:
        db.rollback()
        print(f"Error updating timetable slots: {e}")
        return False
    finally:
        db.close()


def get_all_decrypted_templates(aes_key: bytes) -> List[Tuple[str, str, np.ndarray]]:
    """Decrypts all stored embeddings in memory for matching."""
    db = SessionLocal()
    decrypted_list = []
    try:
        templates = db.query(FaceTemplate).all()
        for t in templates:
            student = db.query(Student).filter(Student.student_id == t.student_id).first()
            if student:
                try:
                    embedding = decrypt_embedding(t.encrypted_embedding, t.nonce, t.tag, aes_key)
                    decrypted_list.append((student.student_id, student.name, embedding))
                except Exception as err:
                    print(f"Warning: Failed to decrypt template ID {t.id}: {err}")
    finally:
        db.close()
    return decrypted_list


def record_window_attendance(student_id: str, slot_id: str, window: str, confidence: float) -> bool:
    """Record attendance for Window A (First 5m), Window B (Mid 5m), or Window C (Last 5m)."""
    db = SessionLocal()
    today = date.today()
    now_str = datetime.now().strftime("%H:%M:%S")
    try:
        record = db.query(HourlyAttendance).filter(
            HourlyAttendance.student_id == student_id,
            HourlyAttendance.date == today,
            HourlyAttendance.slot_id == slot_id
        ).first()

        if not record:
            record = HourlyAttendance(
                student_id=student_id,
                date=today,
                slot_id=slot_id,
                window_a_status="ABSENT",
                window_b_status="ABSENT",
                window_c_status="ABSENT",
                final_status="ABSENT",
                remarks="Automated"
            )
            db.add(record)

        if window == "WINDOW_A":
            record.window_a_status = "PRESENT"
            record.window_a_time = now_str
            record.window_a_confidence = max(record.window_a_confidence or 0.0, float(confidence))
        elif window == "WINDOW_B":
            record.window_b_status = "PRESENT"
            record.window_b_time = now_str
            record.window_b_confidence = max(record.window_b_confidence or 0.0, float(confidence))
        elif window == "WINDOW_C":
            record.window_c_status = "PRESENT"
            record.window_c_time = now_str
            record.window_c_confidence = max(record.window_c_confidence or 0.0, float(confidence))

        remarks_str = record.remarks or "Automated"
        if not remarks_str.startswith("Manual"):
            # Tri-Window 2-out-of-3 Majority Voting Decision Logic
            wins_present = 0
            if record.window_a_status == "PRESENT": wins_present += 1
            if record.window_b_status == "PRESENT": wins_present += 1
            if record.window_c_status == "PRESENT": wins_present += 1

            if wins_present >= 2:
                record.final_status = "PRESENT"
            elif wins_present == 1:
                record.final_status = "PARTIAL"
            else:
                record.final_status = "ABSENT"

        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Error recording window attendance: {e}")
        return False
    finally:
        db.close()


def add_unknown_face(slot_id: str, window: str, image_path: str):
    """Save record of unrecognized face."""
    db = SessionLocal()
    today = date.today()
    now_str = datetime.now().strftime("%H:%M:%S")
    try:
        uf = UnknownFace(
            date=today,
            slot_id=slot_id,
            window=window,
            timestamp=now_str,
            image_path=image_path
        )
        db.add(uf)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error logging unknown face: {e}")
    finally:
        db.close()


def manual_override_attendance(student_id: str, slot_id: str, new_status: str, remarks: str, staff_name: str = "Staff") -> bool:
    """Execute staff manual attendance override."""
    db = SessionLocal()
    today = date.today()
    try:
        record = db.query(HourlyAttendance).filter(
            HourlyAttendance.student_id == student_id,
            HourlyAttendance.date == today,
            HourlyAttendance.slot_id == slot_id
        ).first()

        if not record:
            record = HourlyAttendance(
                student_id=student_id,
                date=today,
                slot_id=slot_id,
                window_a_status="ABSENT",
                window_b_status="ABSENT"
            )
            db.add(record)

        record.final_status = new_status
        record.remarks = f"Manual Override by {staff_name} ({remarks})"
        db.commit()

        log_activity(staff_name, staff_name, "Manual Override", f"Updated {student_id} on {slot_id} to {new_status}")
        return True
    except Exception as e:
        db.rollback()
        print(f"Error executing manual override: {e}")
        return False
    finally:
        db.close()


def get_registered_students():
    """Fetch all registered students."""
    db = SessionLocal()
    try:
        return db.query(Student).all()
    finally:
        db.close()


def get_all_timetable_slots():
    """Fetch all configured timetable slots."""
    db = SessionLocal()
    try:
        return db.query(TimetableSlot).all()
    finally:
        db.close()
