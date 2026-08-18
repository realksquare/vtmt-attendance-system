import { API } from './api.js';

/* Site-Native Notification & Modal Helpers */
function showToast(message, type = 'success', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const iconMap = {
        success: 'fa-circle-check',
        error: 'fa-circle-xmark',
        info: 'fa-circle-info'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="fa-solid ${iconMap[type] || 'fa-circle-info'}"></i>
        <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-10px)';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function showConfirmDialog(title, text, actionText = 'Delete', onConfirm = () => {}) {
    const modal = document.getElementById('modal-confirm');
    const titleEl = document.getElementById('confirm-modal-title');
    const textEl = document.getElementById('confirm-modal-text');
    const btnAction = document.getElementById('confirm-btn-action');
    const btnCancel = document.getElementById('confirm-btn-cancel');

    if (!modal) return;

    if (titleEl) titleEl.textContent = title;
    if (textEl) textEl.textContent = text;
    if (btnAction) btnAction.textContent = actionText;

    modal.style.display = 'flex';

    const handleAction = () => {
        modal.style.display = 'none';
        btnAction.removeEventListener('click', handleAction);
        btnCancel.removeEventListener('click', handleCancel);
        onConfirm();
    };

    const handleCancel = () => {
        modal.style.display = 'none';
        btnAction.removeEventListener('click', handleAction);
        btnCancel.removeEventListener('click', handleCancel);
    };

    btnAction.addEventListener('click', handleAction);
    btnCancel.addEventListener('click', handleCancel);
}

window.showToast = showToast;
window.showConfirmDialog = showConfirmDialog;

let currentPin = '';
let currentUser = null;
let allStudentsList = [];
let allStaffList = [];
let studentSortColumn = 'student_id';
let studentSortAsc = true;
let staffSortColumn = 'staff_id';
let staffSortAsc = true;

// Expose functions to global window scope for inline HTML events
window.pressPin = pressPin;
window.clearPin = clearPin;
window.submitPin = submitPin;
window.logout = logout;
window.renderStaffHourView = renderStaffHourView;
window.submitStaffOverride = submitStaffOverride;
window.exportExcel = exportExcel;
window.exportStaffExcel = exportStaffExcel;
window.openEnrollModal = openEnrollModal;
window.closeEnrollModal = closeEnrollModal;
window.captureEnrollFrame = captureEnrollFrame;
window.submitEnrollment = submitEnrollment;
window.openEditStudentModal = openEditStudentModal;
window.closeEditStudentModal = closeEditStudentModal;
window.captureEditFrame = captureEditFrame;
window.submitStudentUpdate = submitStudentUpdate;
window.filterStudentsTable = filterStudentsTable;
window.sortStudentsTable = sortStudentsTable;
window.confirmDeleteStudent = confirmDeleteStudent;
window.openEnrollStaffModal = openEnrollStaffModal;
window.closeEnrollStaffModal = closeEnrollStaffModal;
window.captureEnrollStaffFrame = captureEnrollStaffFrame;
window.submitStaffEnrollment = submitStaffEnrollment;
window.openEditStaffModal = openEditStaffModal;
window.closeEditStaffModal = closeEditStaffModal;
window.submitStaffUpdate = submitStaffUpdate;
window.filterStaffTable = filterStaffTable;
window.sortStaffTable = sortStaffTable;
window.confirmDeleteStaff = confirmDeleteStaff;
window.addTimetableSlotRow = addTimetableSlotRow;
window.removeTimetableSlotRow = removeTimetableSlotRow;
window.saveTimetableSchedule = saveTimetableSchedule;
window.processTimetableOcr = processTimetableOcr;

document.addEventListener('DOMContentLoaded', () => {
    checkSavedSession();
    initNavigation();
});

/* PIN Auth Handlers */
function pressPin(num) {
    if (currentPin.length < 4) {
        currentPin += num;
        updatePinDots();
    }
    if (currentPin.length === 4) {
        setTimeout(submitPin, 100);
    }
}

function clearPin() {
    currentPin = '';
    updatePinDots();
    const err = document.getElementById('pin-error');
    if (err) err.style.display = 'none';
}

function updatePinDots() {
    for (let i = 0; i < 4; i++) {
        const dot = document.getElementById(`dot-${i}`);
        if (dot) {
            if (i < currentPin.length) dot.classList.add('filled');
            else dot.classList.remove('filled');
        }
    }
}

async function submitPin() {
    if (currentPin.length !== 4) return;
    const err = document.getElementById('pin-error');

    try {
        const user = await API.loginWithPin(currentPin);
        sessionStorage.setItem('auth_user', JSON.stringify(user));
        applyAuthenticatedUser(user);
    } catch (error) {
        if (err) {
            err.textContent = error.message;
            err.style.display = 'block';
        }
        clearPin();
    }
}

function checkSavedSession() {
    const saved = sessionStorage.getItem('auth_user');
    if (saved) {
        try {
            const user = JSON.parse(saved);
            applyAuthenticatedUser(user);
        } catch (e) {
            sessionStorage.removeItem('auth_user');
        }
    }
}

function applyAuthenticatedUser(user) {
    currentUser = user;
    document.getElementById('auth-screen').style.display = 'none';
    const shell = document.getElementById('app-shell');
    shell.style.display = 'flex';

    document.getElementById('user-name').textContent = user.name;
    const badge = document.getElementById('user-role-badge');
    badge.textContent = user.role;
    
    // Show/hide admin-only tab buttons
    const adminBtns = document.querySelectorAll('.tab-btn.admin-only');
    if (user.role === 'ADMIN') {
        badge.className = 'role-badge role-admin';
        adminBtns.forEach(el => el.style.display = 'inline-block');
        renderAdminPanel();
    } else {
        badge.className = 'role-badge role-staff';
        adminBtns.forEach(el => el.style.display = 'none');
    }

    loadInitialData();
}

function logout() {
    sessionStorage.removeItem('auth_user');
    currentUser = null;
    currentPin = '';
    updatePinDots();
    document.getElementById('app-shell').style.display = 'none';
    document.getElementById('auth-screen').style.display = 'flex';
}

/* Navigation Tabs */
function initNavigation() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabViews = document.querySelectorAll('.tab-view');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');

            tabBtns.forEach(b => b.classList.remove('active'));
            tabViews.forEach(v => v.style.display = 'none');

            btn.classList.add('active');
            const target = document.getElementById(tabId);
            if (target) target.style.display = 'block';

            if (tabId === 'tab-hourly-view') renderStaffHourView();
            if (tabId === 'tab-full-matrix') renderFullMatrix();
            if (tabId === 'tab-students-directory') renderStudentsDirectory();
            if (tabId === 'tab-staff-directory') renderStaffDirectory();
            if (tabId === 'tab-staff-attendance') renderStaffAttendance();
            if (tabId === 'tab-timetable-setup') renderTimetableSetup();
            if (tabId === 'tab-unknowns-view') renderUnknowns();
            if (tabId === 'tab-admin-view') renderAdminPanel();
        });
    });
}

/* Initial Data Load */
async function loadInitialData() {
    try {
        const matrixData = await API.getAttendanceMatrix();
        const slotSelect = document.getElementById('staff-slot-select');

        if (slotSelect && matrixData.slots) {
            slotSelect.innerHTML = matrixData.slots.map(s => `<option value="${s.slot_id}">${s.subject} (${s.start_time} - ${s.end_time})</option>`).join('');
        }

        renderStaffHourView();
        populateStudentSelect();
    } catch (e) {
        console.error("Error loading initial data:", e);
    }
}

async function populateStudentSelect() {
    const studentSelect = document.getElementById('override-student-select');
    if (!studentSelect) return;
    try {
        const students = await API.getStudents();
        studentSelect.innerHTML = students.map(s => `<option value="${s.student_id}">${s.name} (${s.student_id})</option>`).join('');
    } catch (e) {
        console.error("Error fetching student list:", e);
    }
}

/* Staff Hour View */
async function renderStaffHourView() {
    const tableBody = document.getElementById('staff-hour-table-body');
    const slotSelect = document.getElementById('staff-slot-select');
    if (!tableBody || !slotSelect) return;

    const selectedSlotId = slotSelect.value;
    if (!selectedSlotId) return;

    try {
        const data = await API.getAttendanceMatrix();
        const students = data.matrix || [];

        if (students.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">No students registered in database.</td></tr>`;
            return;
        }

        let html = '';
        students.forEach(s => {
            const slotData = s.slots[selectedSlotId] || {
                window_a_status: 'ABSENT', window_a_conf: 0.0,
                window_b_status: 'ABSENT', window_b_conf: 0.0,
                window_c_status: 'ABSENT', window_c_conf: 0.0,
                final_status: 'ABSENT', remarks: 'Automated'
            };

            const winABadge = slotData.window_a_status === 'PRESENT' ? 
                `<span class="badge badge-present">PRESENT (${slotData.window_a_conf}%)</span>` : 
                `<span class="badge badge-absent">ABSENT</span>`;

            const winBBadge = slotData.window_b_status === 'PRESENT' ? 
                `<span class="badge badge-present">PRESENT (${slotData.window_b_conf}%)</span>` : 
                `<span class="badge badge-absent">ABSENT</span>`;

            const winCBadge = slotData.window_c_status === 'PRESENT' ? 
                `<span class="badge badge-present">PRESENT (${slotData.window_c_conf}%)</span>` : 
                `<span class="badge badge-absent">ABSENT</span>`;

            let finalBadgeClass = 'badge-absent';
            if (slotData.final_status === 'PRESENT') finalBadgeClass = 'badge-present';
            if (slotData.final_status.includes('PARTIAL')) finalBadgeClass = 'badge-partial';
            if (slotData.final_status.includes('EXCUSED') || slotData.final_status.includes('MANUAL')) finalBadgeClass = 'badge-excused';

            html += `<tr>
                <td><strong>${s.name}</strong><br><span style="font-size:11px; color:var(--text-muted);">${s.student_id}</span></td>
                <td>${winABadge}</td>
                <td>${winBBadge}</td>
                <td>${winCBadge}</td>
                <td><span class="badge ${finalBadgeClass}">${slotData.final_status}</span></td>
                <td style="font-size:11px; color:var(--text-muted);">${slotData.remarks}</td>
            </tr>`;
        });

        tableBody.innerHTML = html;
    } catch (e) {
        console.error("Error rendering staff hour view:", e);
    }
}

/* Full Matrix */
async function renderFullMatrix() {
    const header = document.getElementById('full-matrix-header');
    const body = document.getElementById('full-matrix-body');
    if (!header || !body) return;

    try {
        const data = await API.getAttendanceMatrix();
        let headerHTML = `<th>Student</th>`;
        data.slots.forEach((s, idx) => {
            headerHTML += `<th>L${idx+1} (${s.start_time})</th>`;
        });
        header.innerHTML = headerHTML;

        let bodyHTML = '';
        data.matrix.forEach(r => {
            bodyHTML += `<tr><td><strong>${r.name}</strong></td>`;
            data.slots.forEach(slot => {
                const st = r.slots[slot.slot_id]?.final_status || 'ABSENT';
                let bClass = 'badge-absent';
                if (st === 'PRESENT') bClass = 'badge-present';
                if (st.includes('PARTIAL')) bClass = 'badge-partial';
                if (st.includes('EXCUSED') || st.includes('MANUAL')) bClass = 'badge-excused';
                bodyHTML += `<td><span class="badge ${bClass}">${st}</span></td>`;
            });
            bodyHTML += `</tr>`;
        });
        body.innerHTML = bodyHTML;
    } catch (e) {
        console.error("Error rendering full matrix:", e);
    }
}

/* Student Directory with Search, Sort, Delete */
async function renderStudentsDirectory() {
    try {
        allStudentsList = await API.getStudents();
        filterStudentsTable();
    } catch (e) {
        console.error("Error loading students directory:", e);
    }
}

/* Staff Directory with Search, Sort, Delete, Edit */
async function renderStaffDirectory() {
    try {
        allStaffList = await API.getStaff();
        filterStaffTable();
    } catch (e) {
        console.error("Error loading staff directory:", e);
    }
}

function filterStaffTable() {
    const tbody = document.getElementById('staff-table-body');
    const searchVal = (document.getElementById('staff-search-input')?.value || '').toLowerCase().trim();
    if (!tbody) return;

    let filtered = allStaffList.filter(s => {
        return (s.staff_id || '').toLowerCase().includes(searchVal) ||
               (s.name || '').toLowerCase().includes(searchVal) ||
               (s.department || '').toLowerCase().includes(searchVal) ||
               (s.role || '').toLowerCase().includes(searchVal);
    });

    filtered.sort((a, b) => {
        let valA = (a[staffSortColumn] || '').toString().toLowerCase();
        let valB = (b[staffSortColumn] || '').toString().toLowerCase();
        if (valA < valB) return staffSortAsc ? -1 : 1;
        if (valA > valB) return staffSortAsc ? 1 : -1;
        return 0;
    });

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">No matching staff members found.</td></tr>`;
        return;
    }

    let html = '';
    filtered.forEach(s => {
        html += `<tr>
            <td><strong>${s.staff_id}</strong></td>
            <td>${s.name}</td>
            <td>${s.department}</td>
            <td><span class="badge badge-excused">${s.role}</span></td>
            <td><code>${s.pin_code}</code></td>
            <td style="text-align:center;">
                <button class="btn btn-secondary" style="padding:4px 10px; font-size:11px; margin-right:4px;" onclick="openEditStaffModal('${s.staff_id}')">
                    <i class="fa-solid fa-pen"></i> Edit
                </button>
                <button class="btn btn-danger" style="padding:4px 10px; font-size:11px;" onclick="confirmDeleteStaff('${s.staff_id}', '${s.name.replace(/'/g, "\\'")}')">
                    <i class="fa-solid fa-trash"></i> Delete
                </button>
            </td>
        </tr>`;
    });
    tbody.innerHTML = html;
}

function sortStaffTable(column) {
    if (staffSortColumn === column) {
        staffSortAsc = !staffSortAsc;
    } else {
        staffSortColumn = column;
        staffSortAsc = true;
    }
    filterStaffTable();
}

function confirmDeleteStaff(staffId, name) {
    showConfirmDialog(
        "Delete Staff Member?",
        `Are you sure you want to delete staff member '${name}' (${staffId})? This will remove their credentials and biometric template.`,
        "Delete",
        async () => {
            try {
                const adminName = currentUser ? currentUser.name : "Admin";
                const res = await API.deleteStaff(staffId, adminName);
                showToast(res.message, "success");
                renderStaffDirectory();
            } catch (err) {
                showToast("Delete Error: " + err.message, "error");
            }
        }
    );
}

/* Staff Attendance Matrix */
async function renderStaffAttendance() {
    const tbody = document.getElementById('staff-attendance-body');
    if (!tbody) return;

    try {
        const data = await API.getStaffAttendance();
        const records = data.matrix || [];

        if (records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">No staff attendance records logged for today.</td></tr>`;
            return;
        }

        let html = '';
        records.forEach(r => {
            let bClass = 'badge-absent';
            if (r.status === 'PRESENT') bClass = 'badge-present';
            if (r.status === 'LATE') bClass = 'badge-partial';

            html += `<tr>
                <td><strong>${r.name}</strong><br><span style="font-size:11px; color:var(--text-muted);">${r.staff_id}</span></td>
                <td>${r.department} <br><span style="font-size:10px; color:var(--text-muted);">${r.role}</span></td>
                <td>${r.check_in_time}</td>
                <td>${r.check_out_time}</td>
                <td><span class="badge ${bClass}">${r.status}</span></td>
                <td style="font-size:11px; color:var(--text-muted);">${r.remarks}</td>
            </tr>`;
        });
        tbody.innerHTML = html;
    } catch (e) {
        console.error("Error rendering staff attendance:", e);
    }
}

function exportStaffExcel() {
    window.location.href = '/api/export/excel/staff';
}

/* Staff Enrollment & Edit Modal Handlers */
let staffWebcamStream = null;

async function openEnrollStaffModal() {
    const modal = document.getElementById('modal-enroll-staff');
    const video = document.getElementById('staff-enroll-video');
    if (modal) modal.style.display = 'flex';
    try {
        staffWebcamStream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (video) video.srcObject = staffWebcamStream;
    } catch (err) {
        console.warn("Webcam optional for staff enrollment:", err.message);
    }
}

function closeEnrollStaffModal() {
    const modal = document.getElementById('modal-enroll-staff');
    if (modal) modal.style.display = 'none';
    if (staffWebcamStream) {
        staffWebcamStream.getTracks().forEach(t => t.stop());
        staffWebcamStream = null;
    }
}

async function captureEnrollStaffFrame() {
    const video = document.getElementById('staff-enroll-video');
    const preview = document.getElementById('staff-captured-preview');
    const base64Input = document.getElementById('staff_image_base64');

    if (!video || !preview) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d');

    // 1. Frame A
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imgDataA = ctx.getImageData(0, 0, canvas.width, canvas.height).data;

    showToast("Analyzing live face micro-motion...", "info");
    await new Promise(r => setTimeout(r, 350));

    // 2. Frame B
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imgDataB = ctx.getImageData(0, 0, canvas.width, canvas.height).data;

    let totalDiff = 0;
    let sampleCount = 0;
    for (let i = 0; i < imgDataA.length; i += 16) {
        totalDiff += Math.abs(imgDataA[i] - imgDataB[i]);
        sampleCount++;
    }
    const avgMotion = totalDiff / sampleCount;

    if (avgMotion < 0.50) {
        showToast("Anti-Spoofing Alert: Static photo / phone image detected! Please use a live face.", "error");
        if (base64Input) base64Input.value = '';
        if (preview) preview.style.display = 'none';
        return;
    }

    const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
    if (base64Input) base64Input.value = dataUrl;
    if (preview) {
        preview.src = dataUrl;
        preview.style.display = 'block';
    }
    showToast("Live staff face frame verified & captured!", "info");
}

async function submitStaffEnrollment(e) {
    e.preventDefault();
    const base64Input = document.getElementById('staff_image_base64');
    const data = {
        staff_id: document.getElementById('staff_enroll_id').value,
        pin_code: document.getElementById('staff_enroll_pin').value,
        name: document.getElementById('staff_enroll_name').value,
        department: document.getElementById('staff_enroll_dept').value,
        role: document.getElementById('staff_enroll_role').value,
        image_base64: (base64Input && base64Input.value) ? base64Input.value : null,
        admin_name: currentUser ? currentUser.name : "Admin"
    };

    try {
        const res = await API.enrollStaff(data);
        showToast(res.message, "success");
        closeEnrollStaffModal();
        renderStaffDirectory();
    } catch (err) {
        showToast("Staff Enrollment Error: " + err.message, "error");
    }
}

function openEditStaffModal(staffId) {
    const staff = allStaffList.find(s => s.staff_id === staffId);
    if (!staff) {
        showToast("Staff details not found.", "error");
        return;
    }

    document.getElementById('staff_edit_id').value = staff.staff_id;
    document.getElementById('staff_edit_name').value = staff.name;
    document.getElementById('staff_edit_dept').value = staff.department;
    document.getElementById('staff_edit_role').value = staff.role;
    document.getElementById('staff_edit_pin').value = '';

    const modal = document.getElementById('modal-edit-staff');
    if (modal) modal.style.display = 'flex';
}

function closeEditStaffModal() {
    const modal = document.getElementById('modal-edit-staff');
    if (modal) modal.style.display = 'none';
}

async function submitStaffUpdate(e) {
    e.preventDefault();
    const staffId = document.getElementById('staff_edit_id').value;
    const data = {
        name: document.getElementById('staff_edit_name').value,
        department: document.getElementById('staff_edit_dept').value,
        role: document.getElementById('staff_edit_role').value,
        pin_code: document.getElementById('staff_edit_pin').value || null,
        admin_name: currentUser ? currentUser.name : "Admin"
    };

    try {
        const res = await API.updateStaff(staffId, data);
        showToast(res.message, "success");
        closeEditStaffModal();
        renderStaffDirectory();
    } catch (err) {
        showToast("Staff Update Error: " + err.message, "error");
    }
}

function filterStudentsTable() {
    const tbody = document.getElementById('students-table-body');
    const searchVal = (document.getElementById('student-search-input')?.value || '').toLowerCase().trim();

    if (!tbody) return;

    let filtered = allStudentsList.filter(s => {
        return s.student_id.toLowerCase().includes(searchVal) ||
               s.name.toLowerCase().includes(searchVal) ||
               s.department.toLowerCase().includes(searchVal) ||
               s.year.toLowerCase().includes(searchVal);
    });

    // Apply Sorting
    filtered.sort((a, b) => {
        let valA = (a[studentSortColumn] || '').toString().toLowerCase();
        let valB = (b[studentSortColumn] || '').toString().toLowerCase();
        if (valA < valB) return studentSortAsc ? -1 : 1;
        if (valA > valB) return studentSortAsc ? 1 : -1;
        return 0;
    });

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">No matching students found.</td></tr>`;
        return;
    }

    let html = '';
    filtered.forEach(s => {
        html += `<tr>
            <td><strong>${s.student_id}</strong></td>
            <td>${s.name}</td>
            <td>${s.department}</td>
            <td>${s.year}</td>
            <td style="text-align:center;">
                <button class="btn btn-secondary" style="padding:4px 10px; font-size:11px; margin-right:4px;" onclick="openEditStudentModal('${s.student_id}')">
                    <i class="fa-solid fa-pen"></i> Edit
                </button>
                <button class="btn btn-danger" style="padding:4px 10px; font-size:11px;" onclick="confirmDeleteStudent('${s.student_id}', '${s.name.replace(/'/g, "\\'")}')">
                    <i class="fa-solid fa-trash"></i> Delete
                </button>
            </td>
        </tr>`;
    });
    tbody.innerHTML = html;
}

function sortStudentsTable(column) {
    if (studentSortColumn === column) {
        studentSortAsc = !studentSortAsc;
    } else {
        studentSortColumn = column;
        studentSortAsc = true;
    }
    filterStudentsTable();
}

async function confirmDeleteStudent(studentId, name) {
    showConfirmDialog(
        "Delete Student Profile?",
        `Are you sure you want to delete student '${name}' (${studentId})? This will remove their profile, encrypted face template, and attendance records.`,
        "Delete",
        async () => {
            try {
                const staffName = currentUser ? currentUser.name : "Staff";
                const res = await API.deleteStudent(studentId, staffName);
                showToast(res.message, "success");
                renderStudentsDirectory();
                loadInitialData();
            } catch (err) {
                showToast("Delete Error: " + err.message, "error");
            }
        }
    );
}

/* Timetable Builder & OCR Upload */
async function renderTimetableSetup() {
    try {
        const slots = await API.getTimetable();
        const container = document.getElementById('timetable-slots-container');
        if (!container) return;

        container.innerHTML = '';
        slots.forEach((s, idx) => {
            addTimetableSlotRow(s.start_time, s.end_time, s.subject);
        });

        if (slots.length === 0) {
            addTimetableSlotRow('09:00', '10:00', 'Lecture 1');
        }
    } catch (e) {
        console.error("Error loading timetable setup:", e);
    }
}

function addTimetableSlotRow(start = '09:00', end = '10:00', subject = '') {
    const container = document.getElementById('timetable-slots-container');
    if (!container) return;

    const rowId = 'slot-row-' + Date.now() + '-' + Math.random().toString(36).substr(2, 4);
    const rowHTML = `
    <div id="${rowId}" style="display:grid; grid-template-columns: 1fr 1fr 2fr auto; gap:10px; align-items:center; margin-bottom:10px;">
        <input type="text" class="form-control slot-start" value="${start}" placeholder="Start (HH:MM)" required>
        <input type="text" class="form-control slot-end" value="${end}" placeholder="End (HH:MM)" required>
        <input type="text" class="form-control slot-subject" value="${subject}" placeholder="Subject / Lecture Title" required>
        <button type="button" class="btn btn-danger" style="padding:8px 12px;" onclick="removeTimetableSlotRow('${rowId}')">
            <i class="fa-solid fa-xmark"></i>
        </button>
    </div>`;

    container.insertAdjacentHTML('beforeend', rowHTML);
}

function removeTimetableSlotRow(rowId) {
    const row = document.getElementById(rowId);
    if (row) row.remove();
}

async function saveTimetableSchedule(e) {
    e.preventDefault();
    const container = document.getElementById('timetable-slots-container');
    const rows = container.querySelectorAll('div[id^="slot-row-"]');

    const slots = [];
    rows.forEach(r => {
        const start = r.querySelector('.slot-start').value.trim();
        const end = r.querySelector('.slot-end').value.trim();
        const subject = r.querySelector('.slot-subject').value.trim();
        if (start && end && subject) {
            slots.push({ start_time: start, end_time: end, subject: subject });
        }
    });

    if (slots.length === 0) {
        showToast("Please add at least one timetable slot!", "error");
        return;
    }

    try {
        const staffName = currentUser ? currentUser.name : "Staff";
        const res = await API.saveTimetable(slots, staffName);
        showToast(res.message, "success");
        loadInitialData();
    } catch (err) {
        showToast("Timetable Save Error: " + err.message, "error");
    }
}

async function processTimetableOcr() {
    const fileInput = document.getElementById('timetable-ocr-file');
    if (!fileInput || !fileInput.files[0]) {
        showToast("Please select a timetable image file (.jpg, .png) first!", "info");
        return;
    }

    try {
        const res = await API.uploadTimetableOcr(fileInput.files[0]);
        showToast(res.message, "success");
        
        const container = document.getElementById('timetable-slots-container');
        if (container && res.slots) {
            container.innerHTML = '';
            res.slots.forEach(s => {
                addTimetableSlotRow(s.start_time, s.end_time, s.subject);
            });
        }
    } catch (err) {
        showToast("OCR Processing Error: " + err.message, "error");
    }
}

/* Unknowns & Admin Panel */
async function renderUnknowns() {
    const grid = document.getElementById('unknowns-grid');
    if (!grid) return;
    try {
        const unknowns = await API.getUnknowns();
        if (unknowns.length === 0) {
            grid.innerHTML = `<p style="color:var(--text-muted);">No unknown face alerts logged for today.</p>`;
            return;
        }

        let html = '';
        unknowns.forEach(u => {
            html += `
            <div class="photo-card">
                <img src="${u.image_url}" alt="Unknown Face" onerror="this.src='https://via.placeholder.com/140x120?text=No+Photo'">
                <div class="photo-info">
                    <strong>${u.slot_id}</strong><br>
                    <span>${u.window} @ ${u.timestamp}</span>
                </div>
            </div>`;
        });
        grid.innerHTML = html;
    } catch (e) {
        console.error("Error rendering unknowns:", e);
    }
}

async function renderAdminPanel() {
    const body = document.getElementById('admin-activity-body');
    if (!body) return;
    // Load stats and burst slot options in parallel
    refreshAdminStats();
    _populateBurstSlotSelect();
    populateInspectStudentDropdown();
    try {
        const logs = await API.getAdminActivity();
        if (logs.length === 0) {
            body.innerHTML = `<tr><td colspan="4" style="text-align:center;">No activity logged yet.</td></tr>`;
            return;
        }

        let html = '';
        logs.forEach(l => {
            html += `<tr>
                <td><strong>${l.staff_name}</strong> (${l.staff_id})</td>
                <td><span class="badge badge-excused">${l.action}</span></td>
                <td>${l.details || '-'}</td>
                <td style="font-size:11px; color:var(--text-muted);">${l.timestamp}</td>
            </tr>`;
        });
        body.innerHTML = html;
    } catch (e) {
        console.error("Error rendering admin panel:", e);
    }
}

// ----------------------------------------------------
// BIOMETRIC EMBEDDING INSPECTOR & MATCH LABORATORY
// ----------------------------------------------------
let inspectProbeBase64 = null;
let inspectLoadedProbeImage = null;
let currentEnrolledTemplateData = null;
let isEnrolledPointsExpanded = false;

async function populateInspectStudentDropdown() {
    const select = document.getElementById('inspect-student-select');
    if (!select) return;

    try {
        const students = await API.getStudents();
        const currentVal = select.value;
        let html = '<option value="">-- Choose Student --</option>';
        students.forEach(s => {
            html += `<option value="${s.student_id}">${s.name} (${s.student_id}) - ${s.department}</option>`;
        });
        select.innerHTML = html;
        if (currentVal) select.value = currentVal;
    } catch (err) {
        console.error("Failed to populate inspect student select:", err);
    }
}

async function loadEnrolledEmbeddingDetails() {
    const select = document.getElementById('inspect-student-select');
    const previewDiv = document.getElementById('inspect-enrolled-preview');
    if (!select || !previewDiv) return;

    const studentId = select.value;
    if (!studentId) {
        currentEnrolledTemplateData = null;
        previewDiv.innerHTML = '<em>Select an enrolled student to view their decrypted 512-D embedding blueprint.</em>';
        return;
    }

    previewDiv.innerHTML = '<span style="color:var(--text-muted);"><i class="fa-solid fa-spinner fa-spin"></i> Decrypting 512-D template with AES-256...</span>';

    try {
        const data = await API.getEnrolledEmbedding(studentId);
        currentEnrolledTemplateData = data;
        isEnrolledPointsExpanded = false;
        renderEnrolledEmbeddingView();
    } catch (err) {
        currentEnrolledTemplateData = null;
        previewDiv.innerHTML = `<span style="color:var(--rose);"><i class="fa-solid fa-triangle-exclamation"></i> ${err.message}</span>`;
    }
}

function toggleAllEnrolledEmbeddingPoints() {
    isEnrolledPointsExpanded = !isEnrolledPointsExpanded;
    renderEnrolledEmbeddingView();
}

function renderEnrolledEmbeddingView() {
    const previewDiv = document.getElementById('inspect-enrolled-preview');
    if (!previewDiv || !currentEnrolledTemplateData) return;

    const data = currentEnrolledTemplateData;
    const fullPoints = data.vector_full || data.vector_sample;

    let pointsHtml = '';
    if (!isEnrolledPointsExpanded) {
        // Show first 16 points + clickable expand button / dots
        const sample16 = fullPoints.slice(0, 16);
        pointsHtml = sample16.map((v, i) => {
            const isPos = v >= 0;
            const bg = isPos ? 'rgba(16, 185, 129, 0.15)' : 'rgba(59, 130, 246, 0.15)';
            const border = isPos ? 'rgba(16, 185, 129, 0.3)' : 'rgba(59, 130, 246, 0.3)';
            const textCol = isPos ? '#34d399' : '#60a5fa';
            return `<span title="Dimension [${i}]: ${v.toFixed(5)}" style="display:inline-block; padding:2px 5px; margin:2px; background:${bg}; border:1px solid ${border}; color:${textCol}; border-radius:3px; font-family:monospace; font-size:10px;">${isPos ? '+' : ''}${v.toFixed(3)}</span>`;
        }).join(' ');

        pointsHtml += ` <button onclick="toggleAllEnrolledEmbeddingPoints()" style="background:rgba(99,102,241,0.2); border:1px solid var(--primary-light); color:var(--primary-light); border-radius:4px; padding:2px 8px; font-size:10px; cursor:pointer; font-weight:600;" title="Click to expand all 512 dimensions">
            ... Show All 512 Points <i class="fa-solid fa-chevron-down"></i>
        </button>`;
    } else {
        // Expanded: Render all 512 points in a sleek scrollable matrix
        pointsHtml = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span style="font-size:10px; color:var(--text-muted); font-weight:600;">Complete 512-Dimensional Vector (Dimensions D₀ to D₅₁₁):</span>
                <button onclick="toggleAllEnrolledEmbeddingPoints()" style="background:rgba(255,255,255,0.08); border:1px solid var(--border); color:var(--text-muted); border-radius:4px; padding:1px 6px; font-size:10px; cursor:pointer;">
                    <i class="fa-solid fa-chevron-up"></i> Collapse
                </button>
            </div>
            <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(68px, 1fr)); gap:3px; max-height:180px; overflow-y:auto; padding:6px; background:rgba(0,0,0,0.3); border-radius:6px; border:1px solid var(--border);">
                ${fullPoints.map((v, i) => {
                    const isPos = v >= 0;
                    const bg = isPos ? 'rgba(16, 185, 129, 0.12)' : 'rgba(59, 130, 246, 0.12)';
                    const textCol = isPos ? '#34d399' : '#60a5fa';
                    return `<div title="Point #${i}: ${v.toFixed(5)}" style="padding:2px 4px; background:${bg}; color:${textCol}; border-radius:3px; font-family:monospace; font-size:9px; text-align:center;">
                        <span style="opacity:0.6; font-size:8px;">#${i}:</span> ${isPos ? '+' : ''}${v.toFixed(3)}
                    </div>`;
                }).join('')}
            </div>
        `;
    }

    previewDiv.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <strong style="color:var(--text); font-size:13px;">${data.name} (${data.student_id})</strong>
            <span class="badge badge-present" style="font-size:10px;">L2 Norm: ${data.l2_norm.toFixed(3)}</span>
        </div>
        <div style="font-size:11px; color:var(--text-muted); margin-bottom:8px;">
            Dimensions: <strong>${data.dimensions}</strong> | Mean: <code>${data.stats.mean}</code> | Std: <code>${data.stats.std}</code>
        </div>
        <div style="font-size:10px; color:var(--text-muted); margin-bottom:4px;">Decrypted Vector Blueprint:</div>
        <div style="line-height:1.6;">${pointsHtml}</div>
    `;
}

function handleInspectFileSelected(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        const fullBase64 = e.target.result;
        inspectProbeBase64 = fullBase64.split(',')[1];
        
        inspectLoadedProbeImage = new Image();
        inspectLoadedProbeImage.onload = function() {
            const previewDiv = document.getElementById('inspect-probe-preview');
            if (previewDiv) {
                previewDiv.innerHTML = `
                    <div style="display:flex; align-items:center; gap:10px;">
                        <img src="${fullBase64}" style="width:50px; height:50px; object-fit:cover; border-radius:4px; border:1px solid var(--border);" />
                        <div style="text-align:left; font-size:11px;">
                            <strong style="color:var(--text);">${file.name}</strong><br>
                            <span style="color:var(--emerald);"><i class="fa-solid fa-check"></i> ${inspectLoadedProbeImage.width}x${inspectLoadedProbeImage.height} px | Uploaded</span>
                        </div>
                    </div>
                `;
            }
            const btn = document.getElementById('btn-run-biometric-inspect');
            if (btn) btn.disabled = false;

            // Auto run comparison if student is selected
            runBiometricInspection();
        };
        inspectLoadedProbeImage.src = fullBase64;
    };
    reader.readAsDataURL(file);
}

let inspectCameraStream = null;

async function openInspectCameraModal() {
    const modal = document.getElementById('modal-inspect-camera');
    const video = document.getElementById('inspect-camera-video');
    const previewImg = document.getElementById('inspect-captured-preview-img');

    if (modal) modal.style.display = 'flex';
    if (previewImg) previewImg.style.display = 'none';
    if (video) video.style.display = 'block';

    try {
        inspectCameraStream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
        });
        if (video) video.srcObject = inspectCameraStream;
    } catch (err) {
        showToast("Webcam Access Error: " + err.message, "error");
    }
}

function closeInspectCameraModal() {
    const modal = document.getElementById('modal-inspect-camera');
    if (modal) modal.style.display = 'none';

    if (inspectCameraStream) {
        inspectCameraStream.getTracks().forEach(track => track.stop());
        inspectCameraStream = null;
    }
}

function captureInspectCameraFrame() {
    const video = document.getElementById('inspect-camera-video');
    if (!video || !video.videoWidth) {
        showToast("Camera is not ready yet.", "error");
        return;
    }

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const fullBase64 = canvas.toDataURL('image/jpeg', 0.92);
    inspectProbeBase64 = fullBase64.split(',')[1];

    inspectLoadedProbeImage = new Image();
    inspectLoadedProbeImage.onload = function() {
        const previewDiv = document.getElementById('inspect-probe-preview');
        if (previewDiv) {
            previewDiv.innerHTML = `
                <div style="display:flex; align-items:center; gap:10px;">
                    <img src="${fullBase64}" style="width:50px; height:50px; object-fit:cover; border-radius:4px; border:1px solid var(--border);" />
                    <div style="text-align:left; font-size:11px;">
                        <strong style="color:var(--text);">Webcam Snapshot</strong><br>
                        <span style="color:var(--emerald);"><i class="fa-solid fa-check"></i> ${canvas.width}x${canvas.height} px | Ready to Inspect</span>
                    </div>
                </div>
            `;
        }
        const btn = document.getElementById('btn-run-biometric-inspect');
        if (btn) btn.disabled = false;
        closeInspectCameraModal();
        showToast("Probe face snapshot captured!", "success");

        // Auto run comparison
        runBiometricInspection();
    };
    inspectLoadedProbeImage.src = fullBase64;
}

let inspectMode = 'multi';
let currentSelectedFaceIndex = null;
let lastInspectionResult = null;

function switchInspectMode(mode) {
    inspectMode = mode;
    const btnSingle = document.getElementById('btn-mode-single');
    const btnMulti = document.getElementById('btn-mode-multi');

    if (btnSingle && btnMulti) {
        if (mode === 'single') {
            btnSingle.className = 'btn btn-primary';
            btnMulti.className = 'btn btn-secondary';
        } else {
            btnSingle.className = 'btn btn-secondary';
            btnMulti.className = 'btn btn-primary';
        }
    }

    if (inspectProbeBase64) {
        runBiometricInspection();
    }
}

function selectMultiProbeFace(faceIdx) {
    currentSelectedFaceIndex = faceIdx;
    runBiometricInspection(faceIdx);
}

async function runBiometricInspection(selectedFaceIdx = null) {
    if (!inspectProbeBase64) {
        showToast("Please upload or capture a probe face image first.", "error");
        return;
    }

    const select = document.getElementById('inspect-student-select');
    const targetStudentId = select ? select.value : null;

    const btn = document.getElementById('btn-run-biometric-inspect');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Scanning Faces & Extracting 512-D Embeddings...';
    }

    try {
        const res = await API.inspectBiometrics({
            image_base64: inspectProbeBase64,
            target_student_id: targetStudentId || null,
            selected_face_index: selectedFaceIdx !== null ? selectedFaceIdx : (inspectMode === 'single' ? 0 : null)
        });

        lastInspectionResult = res;
        renderBiometricInspectionResults(res);
        showToast(`Processed ${res.total_faces_detected} face(s) in ${inspectMode === 'multi' ? 'Multi-Probe' : 'Single-Probe'} mode!`, "success");
    } catch (err) {
        showToast("Inspection Failed: " + err.message, "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-chart-line"></i> Extract Embeddings & Compute Match Comparison';
        }
    }
}

function renderBiometricInspectionResults(data) {
    const container = document.getElementById('inspect-results-container');
    if (!container) return;
    container.style.display = 'block';

    const probe = data.probe_face;
    const target = data.target_comparison;
    const ranked = data.ranked_matches || [];
    const allFaces = data.all_faces || [];
    const activeIdx = data.active_face_index || 0;

    // 0. Multi-Face Chips Toolbar
    const multiBar = document.getElementById('inspect-multi-faces-bar');
    if (multiBar) {
        if (data.total_faces_detected > 1 || inspectMode === 'multi') {
            multiBar.style.display = 'block';
            let chipsHtml = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <strong style="font-size:12px; color:var(--text);"><i class="fa-solid fa-users-viewfinder" style="color:var(--primary-light);"></i> Detected ${data.total_faces_detected} Face(s) in Probe Image:</strong>
                    <span style="font-size:10px; color:var(--text-muted);">Click any detected face to map & inspect its 512-D vector:</span>
                </div>
                <div style="display:flex; flex-wrap:wrap; gap:8px;">
            `;

            allFaces.forEach(f => {
                const isActive = (f.face_index === activeIdx);
                const isTargetMatch = f.is_target_match;
                const topCand = f.top_candidate;
                
                let borderCol = isActive ? 'var(--emerald)' : 'var(--border)';
                let bgCol = isActive ? 'rgba(16,185,129,0.18)' : 'rgba(255,255,255,0.04)';
                let tagBadge = isTargetMatch ? `<span class="badge badge-present" style="font-size:9px;">TARGET MATCH (${f.target_match_percent}%)</span>` : `<span style="font-size:10px; color:var(--text-muted);">${f.target_match_percent}% match</span>`;

                chipsHtml += `
                    <button type="button" onclick="selectMultiProbeFace(${f.face_index})" style="background:${bgCol}; border:1px solid ${borderCol}; border-radius:6px; padding:5px 10px; display:flex; align-items:center; gap:8px; cursor:pointer; color:var(--text); font-size:11px;">
                        <strong>Face #${f.face_index + 1}</strong>
                        ${tagBadge}
                        ${isActive ? '<i class="fa-solid fa-check" style="color:var(--emerald);"></i>' : ''}
                    </button>
                `;
            });
            chipsHtml += `</div>`;
            multiBar.innerHTML = chipsHtml;
        } else {
            multiBar.style.display = 'none';
        }
    }

    // 1. Top Comparison Metric Banners with Attendance Confidence Score
    const banner = document.getElementById('inspect-metrics-banner');
    if (banner) {
        let matchStatusHtml = '';
        if (target) {
            const isMatch = target.is_match;
            const simScore = target.cosine_similarity;
            const attendanceVerdict = isMatch ? 'PRESENT' : 'UNRESOLVED';
            const verdictColor = isMatch ? 'var(--emerald)' : 'var(--rose)';

            matchStatusHtml = `
                <div class="stat-card" style="border-left:4px solid ${verdictColor};">
                    <div class="stat-label">Attendance Match Verdict</div>
                    <div class="stat-value" style="font-size:18px; color:${verdictColor};">
                        ${isMatch ? '<i class="fa-solid fa-circle-check"></i> ' + attendanceVerdict : '<i class="fa-solid fa-circle-xmark"></i> ' + attendanceVerdict}
                    </div>
                    <div style="font-size:10px; color:var(--text-muted);">${isMatch ? 'Mapped to Enrolled Profile' : 'Below 0.50 Match Threshold'}</div>
                </div>
                <div class="stat-card" style="border-left:4px solid var(--primary-light);">
                    <div class="stat-label">Match Confidence Score</div>
                    <div class="stat-value" style="font-size:22px; color:var(--primary-light);">${target.match_percent}% <span style="font-size:14px; opacity:0.8;">(${simScore.toFixed(4)})</span></div>
                    <div style="font-size:10px; color:var(--text-muted);">Threshold: &ge; 50.0% (0.5000)</div>
                </div>
                <div class="stat-card" style="border-left:4px solid var(--amber);">
                    <div class="stat-label">Angular Separation (θ)</div>
                    <div class="stat-value" style="font-size:20px; color:var(--amber);">${target.angular_separation_deg}&deg;</div>
                    <div style="font-size:10px; color:var(--text-muted);">Active Face: #${activeIdx + 1} of ${data.total_faces_detected}</div>
                </div>
            `;
        } else {
            const topMatch = ranked[0];
            matchStatusHtml = `
                <div class="stat-card" style="border-left:4px solid var(--primary-light);">
                    <div class="stat-label">Top Candidate</div>
                    <div class="stat-value" style="font-size:16px;">${topMatch ? topMatch.student_name : 'None'}</div>
                    <div style="font-size:10px; color:var(--text-muted);">${topMatch ? topMatch.student_id : ''}</div>
                </div>
                <div class="stat-card" style="border-left:4px solid ${topMatch && topMatch.is_match ? 'var(--emerald)' : 'var(--text-muted)'};">
                    <div class="stat-label">Match Confidence Score</div>
                    <div class="stat-value" style="font-size:22px; color:${topMatch && topMatch.is_match ? 'var(--emerald)' : 'var(--text-muted)'};">${topMatch ? topMatch.match_percent : 0}% (${topMatch ? topMatch.similarity.toFixed(4) : '0.0000'})</div>
                    <div style="font-size:10px; color:var(--text-muted);">Threshold: &ge; 50.0% (0.5000)</div>
                </div>
                <div class="stat-card" style="border-left:4px solid var(--amber);">
                    <div class="stat-label">Candidate Match State</div>
                    <div class="stat-value" style="font-size:16px;">${topMatch && topMatch.is_match ? 'MATCH FOUND (PRESENT)' : 'UNKNOWN FACE (UNRESOLVED)'}</div>
                </div>
            `;
        }

        const padBadge = probe.pad.passed ? '<span style="color:var(--emerald);"><i class="fa-solid fa-shield-check"></i> LIVE GENUINE</span>' : '<span style="color:var(--rose);"><i class="fa-solid fa-shield-halved"></i> SPOOF SUSPECTED</span>';

        banner.innerHTML = `
            ${matchStatusHtml}
            <div class="stat-card" style="border-left:4px solid ${probe.pad.passed ? 'var(--emerald)' : 'var(--rose)'};">
                <div class="stat-label">Anti-Spoofing (PAD)</div>
                <div class="stat-value" style="font-size:16px;">${padBadge}</div>
                <div style="font-size:10px; color:var(--text-muted);">Score: ${probe.pad.score} (MiniFASNet)</div>
            </div>
        `;
    }

    // 2. Draw Multi-Face Bounding Boxes & Landmarks on Canvas
    const canvas = document.getElementById('inspect-landmarks-canvas');
    if (canvas && inspectLoadedProbeImage) {
        canvas.width = inspectLoadedProbeImage.width;
        canvas.height = inspectLoadedProbeImage.height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(inspectLoadedProbeImage, 0, 0);

        const strokeScale = Math.max(2, Math.floor(canvas.width / 220));
        const fontSize = Math.max(12, Math.floor(canvas.width / 40));
        ctx.font = `bold ${fontSize}px sans-serif`;

        // In Multi-Probe mode, draw bounding boxes for ALL detected faces
        if (inspectMode === 'multi' && allFaces.length > 1) {
            allFaces.forEach(f => {
                const [fx1, fy1, fx2, fy2] = f.bbox;
                const isThisActive = (f.face_index === activeIdx);
                const isMatch = f.is_target_match;

                if (!isThisActive) {
                    // Non-active face: Draw yellow/cyan box
                    ctx.strokeStyle = isMatch ? 'rgba(34, 197, 94, 0.7)' : 'rgba(234, 179, 8, 0.7)';
                    ctx.lineWidth = strokeScale;
                    ctx.strokeRect(fx1, fy1, fx2 - fx1, fy2 - fy1);

                    // Label tag
                    const labelText = `Face #${f.face_index + 1} (${f.target_match_percent}%)`;
                    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
                    ctx.fillRect(fx1, Math.max(0, fy1 - fontSize - 6), ctx.measureText(labelText).width + 8, fontSize + 6);
                    ctx.fillStyle = isMatch ? '#34d399' : '#fde047';
                    ctx.fillText(labelText, fx1 + 4, Math.max(fontSize, fy1 - 4));
                }
            });
        }

        // Draw ACTIVE Selected Face with bright green box and 106 landmark dots
        if (probe.bbox && probe.bbox.length === 4) {
            const [x1, y1, x2, y2] = probe.bbox;
            ctx.strokeStyle = '#22c55e';
            ctx.lineWidth = strokeScale + 1;
            ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

            // Active Banner Label
            const targetName = target ? target.student_name : `Face #${activeIdx + 1}`;
            const activeLabel = target && target.is_match ? `✔ ACTIVE MATCH: ${targetName} (${target.match_percent}%)` : `ACTIVE: ${targetName} (${target ? target.match_percent + '%' : 'Inspecting'})`;
            ctx.fillStyle = 'rgba(16, 185, 129, 0.9)';
            ctx.fillRect(x1, Math.max(0, y1 - fontSize - 8), ctx.measureText(activeLabel).width + 12, fontSize + 8);
            ctx.fillStyle = '#ffffff';
            ctx.fillText(activeLabel, x1 + 6, Math.max(fontSize, y1 - 4));
        }

        // Draw 106 Landmark Dots on Active Face
        if (probe.landmarks_106 && probe.landmarks_106.length > 0) {
            ctx.fillStyle = '#06b6d4';
            const radius = Math.max(1.5, canvas.width / 240);
            probe.landmarks_106.forEach(([lx, ly]) => {
                ctx.beginPath();
                ctx.arc(lx, ly, radius, 0, 2 * Math.PI);
                ctx.fill();
            });
        }
    }

    // Quality Stats
    const qDiv = document.getElementById('inspect-quality-stats');
    if (qDiv) {
        qDiv.innerHTML = `
            <span>Quality Tier: <strong>${probe.quality.tier}</strong></span>
            <span>Sharpness: <strong>${probe.quality.blur_score}</strong></span>
            <span>Brightness: <strong>${probe.quality.brightness_mean}</strong></span>
        `;
    }

    // PAD Badge
    const padBadgeElem = document.getElementById('inspect-pad-badge');
    if (padBadgeElem) {
        padBadgeElem.className = probe.pad.passed ? 'badge badge-present' : 'badge badge-absent';
        padBadgeElem.textContent = probe.pad.passed ? `LIVE (${probe.pad.score})` : `SPOOF (${probe.pad.score})`;
    }

    // 3. Vector Heatmap for Active Face
    const heatmapDiv = document.getElementById('inspect-vector-heatmap');
    if (heatmapDiv) {
        const samplePoints = probe.vector_full ? probe.vector_full.slice(0, 128) : probe.vector_sample;
        let cellsHtml = '';
        samplePoints.forEach((val, idx) => {
            let bg = 'rgba(255,255,255,0.05)';
            if (val > 0.05) bg = `rgba(16, 185, 129, ${Math.min(1.0, val * 8)})`;
            else if (val < -0.05) bg = `rgba(59, 130, 246, ${Math.min(1.0, Math.abs(val) * 8)})`;

            cellsHtml += `<div title="Point #${idx}: ${val.toFixed(4)}" style="width:14px; height:14px; background:${bg}; border-radius:2px; font-size:7px; display:flex; align-items:center; justify-content:center; color:#fff; cursor:default;"></div>`;
        });
        heatmapDiv.innerHTML = cellsHtml;
    }

    const vStatsDiv = document.getElementById('inspect-vector-stats');
    if (vStatsDiv) {
        vStatsDiv.innerHTML = `
            <strong>Active Face Vector (Face #${activeIdx + 1}):</strong> 512 float32 | <strong>L2 Norm:</strong> ${probe.l2_norm.toFixed(4)}<br>
            <strong>Mean:</strong> ${probe.stats.mean} | <strong>Std Dev:</strong> ${probe.stats.std} | <strong>Min:</strong> ${probe.stats.min} | <strong>Max:</strong> ${probe.stats.max}
        `;
    }

    // 4. Point-by-Point Vector Comparison Matrix (if target selected)
    const matrixContainer = document.getElementById('inspect-point-comparison-container');
    if (matrixContainer) {
        if (target && target.enrolled_vector_full && probe.vector_full) {
            matrixContainer.style.display = 'block';
            const ePoints = target.enrolled_vector_full;
            const pPoints = probe.vector_full;
            const diffs = target.diff_vector_full || [];

            let rowsHtml = '';
            for (let i = 0; i < Math.min(64, ePoints.length); i++) {
                const ep = ePoints[i];
                const pp = pPoints[i];
                const delta = diffs[i] !== undefined ? diffs[i] : Math.abs(ep - pp);
                const prod = ep * pp;
                const isClose = delta < 0.8;

                rowsHtml += `
                    <tr>
                        <td><strong>#${i}</strong></td>
                        <td style="font-family:monospace; color:${ep >= 0 ? '#34d399' : '#60a5fa'};">${ep >= 0 ? '+' : ''}${ep.toFixed(4)}</td>
                        <td style="font-family:monospace; color:${pp >= 0 ? '#34d399' : '#60a5fa'};">${pp >= 0 ? '+' : ''}${pp.toFixed(4)}</td>
                        <td style="font-family:monospace; color:${isClose ? 'var(--emerald)' : 'var(--amber)'};">${delta.toFixed(4)}</td>
                        <td style="font-family:monospace; color:${prod > 0 ? 'var(--emerald)' : 'var(--rose)'};">${prod >= 0 ? '+' : ''}${prod.toFixed(4)}</td>
                    </tr>
                `;
            }

            matrixContainer.innerHTML = `
                <div class="card" style="background:var(--bg-card); padding:12px; margin-bottom:16px;">
                    <div style="font-size:12px; font-weight:600; color:var(--text); margin-bottom:8px; display:flex; justify-content:space-between;">
                        <span><i class="fa-solid fa-code-compare" style="color:var(--primary-light);"></i> Point-by-Point 512-D Embedding Comparison (${target.student_name} vs Active Face #${activeIdx + 1})</span>
                        <span class="badge ${target.is_match ? 'badge-present' : 'badge-absent'}">Match: ${target.match_percent}%</span>
                    </div>
                    <p style="font-size:11px; color:var(--text-muted); margin-bottom:10px;">
                        Showing first 64 dimensions. A[i] = Enrolled Template (${target.student_name}), B[i] = Active Face #${activeIdx + 1}. Normalized Dot Product Contribution Σ(A · B) determines the Cosine Match Score (${target.cosine_similarity.toFixed(4)}).
                    </p>
                    <div class="table-responsive" style="max-height:220px; overflow-y:auto;">
                        <table>
                            <thead>
                                <tr>
                                    <th>Dimension</th>
                                    <th>Enrolled (A[i])</th>
                                    <th>Probe (B[i])</th>
                                    <th>Delta (|A - B|)</th>
                                    <th>Contribution (A · B)</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${rowsHtml}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        } else {
            matrixContainer.style.display = 'none';
        }
    }

    // 5. Ranked Matches Table
    const tbody = document.getElementById('inspect-ranked-tbody');
    if (tbody) {
        if (ranked.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No enrolled students found to compare against.</td></tr>';
            return;
        }

        let rHtml = '';
        ranked.forEach((r, index) => {
            const isMatch = r.is_match;
            rHtml += `
                <tr style="${index === 0 && isMatch ? 'background:rgba(16,185,129,0.08); font-weight:600;' : ''}">
                    <td><strong>#${index + 1}</strong></td>
                    <td><code>${r.student_id}</code></td>
                    <td>${r.student_name}</td>
                    <td><strong>${r.similarity.toFixed(4)}</strong></td>
                    <td>
                        <div style="display:flex; align-items:center; gap:6px;">
                            <div style="flex:1; background:var(--border); height:6px; border-radius:3px; overflow:hidden; width:60px;">
                                <div style="width:${Math.max(0, r.match_percent)}%; background:${isMatch ? 'var(--emerald)' : 'var(--primary-light)'}; height:100%;"></div>
                            </div>
                            <span>${r.match_percent}%</span>
                        </div>
                    </td>
                    <td>
                        <span class="badge ${isMatch ? 'badge-present' : 'badge-absent'}">
                            ${isMatch ? 'PRESENT' : 'UNRESOLVED'}
                        </span>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = rHtml;
    }
}


async function submitStaffOverride(e) {
    e.preventDefault();
    const student_id = document.getElementById('override-student-select').value;
    const slot_id = document.getElementById('staff-slot-select').value;
    const new_status = document.getElementById('override-status-select').value;
    const remarks = document.getElementById('override-reason').value;

    if (!remarks) {
        showToast("Please enter a reason note for the manual override.", "error");
        return;
    }

    try {
        const res = await API.submitOverride({
            student_id, slot_id, new_status, remarks,
            staff_name: currentUser ? currentUser.name : "Staff"
        });
        showToast(res.message, "success");
        document.getElementById('override-reason').value = '';
        renderStaffHourView();
    } catch (err) {
        showToast("Override Error: " + err.message, "error");
    }
}

function exportExcel() {
    window.location.href = '/api/export/excel';
}

/* Webcam Student Enrollment & Edit Modals */
let webcamStream = null;
let editWebcamStream = null;

async function openEnrollModal() {
    const modal = document.getElementById('modal-enroll');
    const enrollVideo = document.getElementById('enroll-video');
    if (modal) modal.style.display = 'flex';
    try {
        webcamStream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (enrollVideo) enrollVideo.srcObject = webcamStream;
    } catch (err) {
        showToast("Could not access webcam: " + err.message, "error");
    }
}

function closeEnrollModal() {
    const modal = document.getElementById('modal-enroll');
    if (modal) modal.style.display = 'none';
    if (webcamStream) {
        webcamStream.getTracks().forEach(t => t.stop());
        webcamStream = null;
    }
}

async function captureEnrollFrame() {
    const enrollVideo = document.getElementById('enroll-video');
    const capturedPreview = document.getElementById('captured-preview');
    const base64Input = document.getElementById('image_base64');
    
    if (!enrollVideo || !capturedPreview) return;
    const canvas = document.createElement('canvas');
    canvas.width = enrollVideo.videoWidth || 640;
    canvas.height = enrollVideo.videoHeight || 480;
    const ctx = canvas.getContext('2d');

    // 1. Capture Frame A (0ms)
    ctx.drawImage(enrollVideo, 0, 0, canvas.width, canvas.height);
    const imgDataA = ctx.getImageData(0, 0, canvas.width, canvas.height).data;

    showToast("Analyzing live face micro-motion...", "info");
    await new Promise(r => setTimeout(r, 350));

    // 2. Capture Frame B (350ms)
    ctx.drawImage(enrollVideo, 0, 0, canvas.width, canvas.height);
    const imgDataB = ctx.getImageData(0, 0, canvas.width, canvas.height).data;

    // Calculate motion delta across sub-sampled pixels
    let totalDiff = 0;
    let sampleCount = 0;
    for (let i = 0; i < imgDataA.length; i += 16) {
        totalDiff += Math.abs(imgDataA[i] - imgDataB[i]);
        sampleCount++;
    }
    const avgMotion = totalDiff / sampleCount;

    // Static Photo Rejection: If avgMotion < 0.60, it's a completely static phone photo held still
    if (avgMotion < 0.50) {
        showToast("Anti-Spoofing Alert: Static photo / phone image detected! Please use a live face.", "error");
        if (base64Input) base64Input.value = '';
        if (capturedPreview) capturedPreview.style.display = 'none';
        return;
    }

    const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
    if (base64Input) base64Input.value = dataUrl;
    if (capturedPreview) {
        capturedPreview.src = dataUrl;
        capturedPreview.style.display = 'block';
    }
    showToast("Live face frame verified & captured!", "info");
}

async function submitEnrollment(e) {
    e.preventDefault();
    const base64Input = document.getElementById('image_base64');
    const data = {
        student_id: document.getElementById('enroll_student_id').value,
        name: document.getElementById('enroll_name').value,
        department: document.getElementById('enroll_dept').value,
        year: document.getElementById('enroll_year').value,
        image_base64: base64Input ? base64Input.value : ''
    };

    if (!data.image_base64) {
        showToast("Click 'Capture Frame' first!", "error");
        return;
    }

    try {
        const res = await API.enrollStudent(data);
        showToast(res.message, "success");
        closeEnrollModal();
        renderStaffHourView();
        renderStudentsDirectory();
    } catch (err) {
        showToast("Enrollment Error: " + err.message, "error");
    }
}

async function openEditStudentModal(studentId) {
    const student = allStudentsList.find(s => s.student_id === studentId);
    if (!student) {
        showToast("Student details not found.", "error");
        return;
    }

    const editBase64Input = document.getElementById('edit_image_base64');
    const editCapturedPreview = document.getElementById('edit-captured-preview');
    const editVideo = document.getElementById('edit-video');

    document.getElementById('edit_student_id').value = student.student_id;
    document.getElementById('edit_name').value = student.name;
    document.getElementById('edit_dept').value = student.department;
    document.getElementById('edit_year').value = student.year;
    if (editBase64Input) editBase64Input.value = '';
    if (editCapturedPreview) editCapturedPreview.style.display = 'none';

    const modal = document.getElementById('modal-edit-student');
    if (modal) modal.style.display = 'flex';

    try {
        editWebcamStream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (editVideo) editVideo.srcObject = editWebcamStream;
    } catch (err) {
        console.warn("Webcam access optional for editing metadata:", err.message);
    }
}

function closeEditStudentModal() {
    const modal = document.getElementById('modal-edit-student');
    if (modal) modal.style.display = 'none';
    if (editWebcamStream) {
        editWebcamStream.getTracks().forEach(t => t.stop());
        editWebcamStream = null;
    }
}

function captureEditFrame() {
    const editVideo = document.getElementById('edit-video');
    const editCapturedPreview = document.getElementById('edit-captured-preview');
    const editBase64Input = document.getElementById('edit_image_base64');

    if (!editVideo || !editCapturedPreview) return;
    const canvas = document.createElement('canvas');
    canvas.width = editVideo.videoWidth || 640;
    canvas.height = editVideo.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(editVideo, 0, 0, canvas.width, canvas.height);

    const dataUrl = canvas.toDataURL('image/jpeg');
    if (editBase64Input) editBase64Input.value = dataUrl;
    if (editCapturedPreview) {
        editCapturedPreview.src = dataUrl;
        editCapturedPreview.style.display = 'block';
    }
    showToast("New face frame captured! Click 'Update Profile & Embedding' to save.", "info");
}

async function submitStudentUpdate(e) {
    e.preventDefault();
    const editBase64Input = document.getElementById('edit_image_base64');
    const studentId = document.getElementById('edit_student_id').value;
    const data = {
        name: document.getElementById('edit_name').value,
        department: document.getElementById('edit_dept').value,
        year: document.getElementById('edit_year').value,
        image_base64: (editBase64Input && editBase64Input.value) ? editBase64Input.value : null,
        staff_name: currentUser ? currentUser.name : "Staff"
    };

    try {
        const res = await API.updateStudent(studentId, data);
        showToast(res.message, "success");
        closeEditStudentModal();
        renderStudentsDirectory();
        renderStaffHourView();
    } catch (err) {
        showToast("Update Error: " + err.message, "error");
    }
}

/* switchTab helper (used by admin quick actions) */
function switchTab(tabId) {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabViews = document.querySelectorAll('.tab-view');
    tabBtns.forEach(b => b.classList.remove('active'));
    tabViews.forEach(v => v.style.display = 'none');
    const target = document.getElementById(tabId);
    if (target) target.style.display = 'block';
    const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
    if (btn) btn.classList.add('active');
}

/* ── Admin Control Center ──────────────────────────────────────────── */

async function refreshAdminStats() {
    const btn = document.getElementById('btn-refresh-stats');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>'; }
    try {
        const s = await API.getAdminStats();

        const set = (id, val) => {
            const el = document.querySelector(`#${id} .stat-val`);
            if (el) el.textContent = val;
        };
        set('stat-students', s.total_students);
        set('stat-staff', s.total_staff);
        set('stat-slots', s.total_slots);
        set('stat-present', s.present_today);
        set('stat-unknowns', s.unknown_alerts_today);
        const timeEl = document.querySelector('#stat-time .stat-val');
        if (timeEl) timeEl.textContent = s.server_time ? s.server_time.slice(11, 16) : '—';

        // Update scheduler badge
        const badge = document.getElementById('sched-status-label');
        const startTime = document.getElementById('sched-start-time');
        const btnStart = document.getElementById('btn-start-scheduler');
        const btnStop = document.getElementById('btn-stop-scheduler');

        if (s.scheduler_running) {
            if (badge) { badge.className = 'badge badge-present'; badge.innerHTML = '<i class="fa-solid fa-circle-check"></i> Running'; }
            if (startTime) startTime.textContent = s.scheduler_started_at ? `Started at ${s.scheduler_started_at}` : '';
            if (btnStart) btnStart.disabled = true;
            if (btnStop) btnStop.disabled = false;
        } else {
            if (badge) { badge.className = 'badge badge-absent'; badge.innerHTML = '<i class="fa-solid fa-circle-xmark"></i> Not Running'; }
            if (startTime) startTime.textContent = '';
            if (btnStart) btnStart.disabled = false;
            if (btnStop) btnStop.disabled = true;
        }
    } catch (e) {
        console.error('Admin stats error:', e);
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-rotate-right"></i> Refresh'; }
    }
}

async function adminStartScheduler() {
    try {
        const res = await API.startScheduler();
        showToast(res.message, 'success');
        await refreshAdminStats();
    } catch (err) {
        showToast('Scheduler Error: ' + err.message, 'error');
    }
}

async function adminStopScheduler() {
    try {
        const res = await API.stopScheduler();
        showToast(res.message, 'info');
        await refreshAdminStats();
    } catch (err) {
        showToast('Scheduler Error: ' + err.message, 'error');
    }
}

async function adminTriggerBurst() {
    const slotId = document.getElementById('burst-slot-select')?.value;
    const window = document.getElementById('burst-window-select')?.value || 'WINDOW_A';
    const duration = parseInt(document.getElementById('burst-duration-select')?.value || '15');

    if (!slotId) { showToast('Please select a timetable slot first.', 'error'); return; }

    try {
        const res = await API.triggerTestBurst({ slot_id: slotId, window, duration_seconds: duration });
        showToast(res.message, 'success');
    } catch (err) {
        showToast('Burst Error: ' + err.message, 'error');
    }
}

async function adminClearTodayAttendance() {
    showConfirmDialog(
        'Clear Today\'s Attendance?',
        'This will permanently delete ALL attendance records for today. This action cannot be undone.',
        'Clear All',
        async () => {
            try {
                const adminName = currentUser ? currentUser.name : 'Admin';
                const res = await API.clearTodayAttendance(adminName);
                showToast(res.message, 'success');
                renderStaffHourView();
                refreshAdminStats();
            } catch (err) {
                showToast('Error: ' + err.message, 'error');
            }
        }
    );
}

async function adminClearTodayUnknowns() {
    showConfirmDialog(
        'Clear Unknown Face Alerts?',
        'This will delete all unknown face records and their saved images for today.',
        'Clear All',
        async () => {
            try {
                const adminName = currentUser ? currentUser.name : 'Admin';
                const res = await API.clearTodayUnknowns(adminName);
                showToast(res.message, 'success');
                renderUnknowns();
                refreshAdminStats();
            } catch (err) {
                showToast('Error: ' + err.message, 'error');
            }
        }
    );
}

async function _populateBurstSlotSelect() {
    try {
        const slots = await API.getTimetable();
        const select = document.getElementById('burst-slot-select');
        if (!select) return;
        select.innerHTML = slots.map(s => `<option value="${s.slot_id}">${s.slot_id} (${s.subject})</option>`).join('');
    } catch (e) { /* ignore */ }
}

/* Explicit Global Window Bindings for ES Module Compatibility */
window.pressPin = pressPin;
window.clearPin = clearPin;
window.submitPin = submitPin;
window.logout = logout;
window.openEnrollModal = openEnrollModal;
window.closeEnrollModal = closeEnrollModal;
window.captureEnrollFrame = captureEnrollFrame;
window.submitEnrollment = submitEnrollment;
window.openEnrollStaffModal = openEnrollStaffModal;
window.closeEnrollStaffModal = closeEnrollStaffModal;
window.captureEnrollStaffFrame = captureEnrollStaffFrame;
window.submitStaffEnrollment = submitStaffEnrollment;
window.openEditStaffModal = openEditStaffModal;
window.closeEditStaffModal = closeEditStaffModal;
window.submitStaffUpdate = submitStaffUpdate;
window.confirmDeleteStaff = confirmDeleteStaff;
window.sortStaffTable = sortStaffTable;
window.filterStaffTable = filterStaffTable;
window.exportStaffExcel = exportStaffExcel;
window.openEditStudentModal = openEditStudentModal;
window.closeEditStudentModal = closeEditStudentModal;
window.captureEditFrame = captureEditFrame;
window.submitStudentUpdate = submitStudentUpdate;
window.confirmDeleteStudent = confirmDeleteStudent;
window.sortStudentsTable = sortStudentsTable;
window.filterStudentsTable = filterStudentsTable;
window.addTimetableSlotRow = addTimetableSlotRow;
window.removeTimetableSlotRow = removeTimetableSlotRow;
window.saveTimetableSchedule = saveTimetableSchedule;
window.processTimetableOcr = processTimetableOcr;
window.submitStaffOverride = submitStaffOverride;
window.exportExcel = exportExcel;
window.refreshAdminStats = refreshAdminStats;
window.adminStartScheduler = adminStartScheduler;
window.adminStopScheduler = adminStopScheduler;
window.adminTriggerBurst = adminTriggerBurst;
window.adminClearTodayAttendance = adminClearTodayAttendance;
window.adminClearTodayUnknowns = adminClearTodayUnknowns;
window.switchTab = switchTab;
window.renderStaffHourView = renderStaffHourView;
window.renderFullMatrix = renderFullMatrix;
window.renderStudentsDirectory = renderStudentsDirectory;
window.renderStaffDirectory = renderStaffDirectory;
window.renderStaffAttendance = renderStaffAttendance;
window.renderTimetableSetup = renderTimetableSetup;
window.renderUnknowns = renderUnknowns;
window.renderAdminPanel = renderAdminPanel;
window.populateInspectStudentDropdown = populateInspectStudentDropdown;
window.loadEnrolledEmbeddingDetails = loadEnrolledEmbeddingDetails;
window.toggleAllEnrolledEmbeddingPoints = toggleAllEnrolledEmbeddingPoints;
window.handleInspectFileSelected = handleInspectFileSelected;
window.openInspectCameraModal = openInspectCameraModal;
window.closeInspectCameraModal = closeInspectCameraModal;
window.captureInspectCameraFrame = captureInspectCameraFrame;
window.runBiometricInspection = runBiometricInspection;
window.switchInspectMode = switchInspectMode;
window.selectMultiProbeFace = selectMultiProbeFace;








