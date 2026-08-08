/**
 * API Service Client for Smart Attendance System
 */

const API_BASE = '/api';

export const API = {
    async loginWithPin(pinCode) {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pin_code: pinCode })
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Authentication failed");
        return result;
    },

    async getStats() {
        const res = await fetch(`${API_BASE}/stats`);
        if (!res.ok) throw new Error("Failed to fetch stats");
        return await res.json();
    },

    async getStudents() {
        const res = await fetch(`${API_BASE}/students`);
        if (!res.ok) throw new Error("Failed to fetch students");
        return await res.json();
    },

    async getStaff() {
        const res = await fetch(`${API_BASE}/staff`);
        if (!res.ok) throw new Error("Failed to fetch staff members");
        return await res.json();
    },

    async enrollStaff(data) {
        const res = await fetch(`${API_BASE}/staff/enroll`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Staff enrollment failed");
        return result;
    },

    async updateStaff(staffId, data) {
        const res = await fetch(`${API_BASE}/staff/${encodeURIComponent(staffId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Staff update failed");
        return result;
    },

    async deleteStaff(staffId, adminName = 'Admin') {
        const res = await fetch(`${API_BASE}/staff/${encodeURIComponent(staffId)}?admin_name=${encodeURIComponent(adminName)}`, {
            method: 'DELETE'
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Failed to delete staff member");
        return result;
    },

    async getStaffAttendance() {
        const res = await fetch(`${API_BASE}/staff/attendance`);
        if (!res.ok) throw new Error("Failed to fetch staff attendance");
        return await res.json();
    },

    async deleteStudent(studentId, staffName = 'Staff') {
        const res = await fetch(`${API_BASE}/students/${encodeURIComponent(studentId)}?staff_name=${encodeURIComponent(staffName)}`, {
            method: 'DELETE'
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Failed to delete student");
        return result;
    },

    async updateStudent(studentId, data) {
        const res = await fetch(`${API_BASE}/students/${encodeURIComponent(studentId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Failed to update student profile");
        return result;
    },

    async getAttendanceMatrix() {
        const res = await fetch(`${API_BASE}/attendance/matrix`);
        if (!res.ok) throw new Error("Failed to fetch attendance matrix");
        return await res.json();
    },

    async getTimetable() {
        const res = await fetch(`${API_BASE}/timetable`);
        if (!res.ok) throw new Error("Failed to fetch timetable");
        return await res.json();
    },

    async saveTimetable(slots, staffName = 'Staff') {
        const res = await fetch(`${API_BASE}/timetable`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slots, staff_name: staffName })
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Failed to save timetable");
        return result;
    },

    async uploadTimetableOcr(file) {
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch(`${API_BASE}/timetable/ocr-upload`, {
            method: 'POST',
            body: formData
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Timetable OCR upload failed");
        return result;
    },

    async getUnknowns(slotId = null) {
        const url = slotId ? `${API_BASE}/unknowns?slot_id=${slotId}` : `${API_BASE}/unknowns`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("Failed to fetch unknown faces");
        return await res.json();
    },

    async getAdminActivity() {
        const res = await fetch(`${API_BASE}/admin/activity`);
        if (!res.ok) throw new Error("Failed to fetch admin activity logs");
        return await res.json();
    },

    async enrollStudent(data) {
        const res = await fetch(`${API_BASE}/students/enroll`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Enrollment failed");
        return result;
    },

    async submitOverride(data) {
        const res = await fetch(`${API_BASE}/attendance/override`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Override failed");
        return result;
    },

    async getAdminStats() {
        const res = await fetch(`${API_BASE}/admin/stats`);
        if (!res.ok) throw new Error("Failed to fetch system stats");
        return await res.json();
    },

    async startScheduler() {
        const res = await fetch(`${API_BASE}/admin/scheduler/start`, { method: 'POST' });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Failed to start scheduler");
        return result;
    },

    async stopScheduler() {
        const res = await fetch(`${API_BASE}/admin/scheduler/stop`, { method: 'POST' });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Failed to stop scheduler");
        return result;
    },

    async triggerTestBurst(data) {
        const res = await fetch(`${API_BASE}/admin/burst/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Failed to trigger burst");
        return result;
    },

    async clearTodayAttendance(adminName = 'Admin') {
        const res = await fetch(`${API_BASE}/admin/attendance/clear-today?admin_name=${encodeURIComponent(adminName)}`, {
            method: 'DELETE'
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Failed to clear attendance");
        return result;
    },

    async clearTodayUnknowns(adminName = 'Admin') {
        const res = await fetch(`${API_BASE}/admin/unknowns/clear-today?admin_name=${encodeURIComponent(adminName)}`, {
            method: 'DELETE'
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || "Failed to clear unknowns");
        return result;
    }
};
