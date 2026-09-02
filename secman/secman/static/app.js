/**
 * Secman Dashboard — frontend logic
 */

// ===================== State =====================
const API_BASE = '';
let currentPage = 1;
let currentSearch = '';
let auditPage = 1;
let currentTab = 'secrets';

// ===================== Auth =====================
function getAuthHeader() {
    const token = localStorage.getItem('secman_token');
    if (!token) { window.location.href = '/login'; return ''; }
    return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
}

function checkAuth() {
    const token = localStorage.getItem('secman_token');
    if (!token) { window.location.href = '/login'; return false; }
    return true;
}

// ===================== Toast =====================
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => { toast.remove(); }, 4000);
}

// ===================== Tabs =====================
function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById(`tab-${tab}`).classList.add('active');
    if (tab === 'audit') loadAuditLog();
}

// ===================== Stats =====================
async function loadStats() {
    try {
        const res = await fetch(`${API_BASE}/api/secrets`, { headers: getAuthHeader() });
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById('statTotal').textContent = data.total || 0;

        // Today count
        const today = new Date().toISOString().split('T')[0];
        let todayCount = 0;
        if (data.secrets) {
            todayCount = data.secrets.filter(s => s.created_at && s.created_at.startsWith(today)).length;
        }
        document.getElementById('statToday').textContent = todayCount;
    } catch (e) {
        console.error('Failed to load stats:', e);
    }

    // Audit count
    try {
        const res = await fetch(`${API_BASE}/api/audit?page=1&per_page=1`, { headers: getAuthHeader() });
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById('statAudit').textContent = data.total || 0;
    } catch (e) {
        console.error('Failed to load audit stats:', e);
    }
}

// ===================== Secrets CRUD =====================
async function loadSecrets(page = 1) {
    currentPage = page;
    const tbody = document.getElementById('secretsBody');
    tbody.innerHTML = '<tr><td colspan="5" class="loading"><div class="spinner"></div>Загрузка...</td></tr>';

    try {
        let url = `${API_BASE}/api/secrets?page=${page}&per_page=20`;
        if (currentSearch) url += `&search=${encodeURIComponent(currentSearch)}`;

        const res = await fetch(url, { headers: getAuthHeader() });
        if (!res.ok) {
            if (res.status === 401) { logout(); return; }
            throw new Error('Failed to load secrets');
        }
        const data = await res.json();

        if (!data.secrets || data.secrets.length === 0) {
            tbody.innerHTML = `
                <tr><td colspan="5">
                    <div class="empty-state">
                        <div class="icon">🔑</div>
                        <p>${currentSearch ? 'Ничего не найдено' : 'Нет секретов. Добавьте первый!'}</p>
                    </div>
                </td></tr>`;
            document.getElementById('pagination').innerHTML = '';
            return;
        }

        tbody.innerHTML = data.secrets.map(s => `
            <tr>
                <td><span class="secret-key">${escHtml(s.key_name)}</span></td>
                <td style="color:var(--text-secondary)">${escHtml(s.description || '—')}</td>
                <td>
                    <span class="secret-value value-masked" id="val-${s.id}" onclick="toggleValue('${s.id}')">••••••••</span>
                    <button class="copy-btn" onclick="copyValue('${s.id}', '${escAttr(s.key_name)}')" title="Копировать">📋</button>
                </td>
                <td style="color:var(--text-secondary);font-size:0.8rem">${formatDate(s.created_at)}</td>
                <td>
                    <div class="actions">
                        <button class="btn-icon" onclick="editSecret('${s.id}', '${escAttr(s.key_name)}', '${escAttr(s.description || '')}')" title="Редактировать">✏️</button>
                        <button class="btn-icon danger" onclick="deleteSecret('${s.id}')" title="Удалить">🗑️</button>
                    </div>
                </td>
            </tr>
        `).join('');

        renderPagination(data, 'pagination', loadSecrets);
        loadStats();
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--danger)">Ошибка: ${escHtml(e.message)}</td></tr>`;
    }
}

function renderPagination(data, containerId, callback) {
    const container = document.getElementById(containerId);
    if (!data.has_next && data.page <= 1) {
        container.innerHTML = '';
        return;
    }
    let html = '';
    html += `<button class="page-btn" ${data.page <= 1 ? 'disabled' : ''} onclick="loadSecrets(${data.page - 1})">←</button>`;
    html += `<span style="color:var(--text-secondary);font-size:0.85rem;padding:0 8px">Стр. ${data.page}</span>`;
    html += `<button class="page-btn" ${!data.has_next ? 'disabled' : ''} onclick="loadSecrets(${data.page + 1})">→</button>`;
    container.innerHTML = html;
}

async function toggleValue(id) {
    const el = document.getElementById(`val-${id}`);
    if (el.dataset.fetched === 'true') {
        // Already fetched, just toggle visibility
        const isMasked = el.classList.contains('value-masked');
        if (isMasked) {
            el.textContent = '••••••••';
            el.classList.remove('value-visible');
            el.classList.add('value-masked');
        } else {
            el.textContent = '••••••••';
            el.classList.remove('value-visible');
            el.classList.add('value-masked');
        }
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/secrets/${id}`, { headers: getAuthHeader() });
        if (!res.ok) throw new Error('Failed to fetch');
        const data = await res.json();
        el.textContent = data.value;
        el.dataset.fetched = 'true';
        el.classList.add('value-visible');
        el.classList.remove('value-masked');
    } catch (e) {
        el.textContent = 'Ошибка загрузки';
    }
}

async function copyValue(id, keyName) {
    try {
        const res = await fetch(`${API_BASE}/api/secrets/${id}`, { headers: getAuthHeader() });
        if (!res.ok) throw new Error('Failed to fetch');
        const data = await res.json();
        await navigator.clipboard.writeText(data.value);
        showToast(`Значение "${keyName}" скопировано`, 'success');
    } catch (e) {
        showToast('Не удалось скопировать', 'error');
    }
}

function searchSecrets() {
    currentSearch = document.getElementById('searchInput').value.trim();
    loadSecrets(1);
}

// ===================== Modal =====================
function openModal() {
    document.getElementById('modalTitle').textContent = 'Добавить секрет';
    document.getElementById('modalSubmitBtn').textContent = 'Сохранить';
    document.getElementById('editId').value = '';
    document.getElementById('secretKey').value = '';
    document.getElementById('secretValue').value = '';
    document.getElementById('secretDesc').value = '';
    document.getElementById('secretModal').classList.add('active');
}

function closeModal() {
    document.getElementById('secretModal').classList.remove('active');
}

async function editSecret(id, keyName, description) {
    document.getElementById('modalTitle').textContent = 'Редактировать секрет';
    document.getElementById('modalSubmitBtn').textContent = 'Обновить';
    document.getElementById('editId').value = id;
    document.getElementById('secretKey').value = keyName;
    document.getElementById('secretValue').value = '';
    document.getElementById('secretDesc').value = description;
    document.getElementById('secretModal').classList.add('active');

    // Load current value
    try {
        const res = await fetch(`${API_BASE}/api/secrets/${id}`, { headers: getAuthHeader() });
        if (res.ok) {
            const data = await res.json();
            document.getElementById('secretValue').value = data.value;
        }
    } catch (e) { /* ignore */ }
}

async function deleteSecret(id) {
    if (!confirm('Удалить этот секрет?')) return;
    try {
        const res = await fetch(`${API_BASE}/api/secrets/${id}`, {
            method: 'DELETE',
            headers: getAuthHeader()
        });
        if (res.status === 401) { logout(); return; }
        if (!res.ok) throw new Error('Failed to delete');
        showToast('Секрет удалён', 'success');
        loadSecrets(currentPage);
    } catch (e) {
        showToast('Ошибка удаления: ' + e.message, 'error');
    }
}

// ===================== Import =====================
function openImportModal() {
    document.getElementById('importModal').classList.add('active');
}

function closeImportModal() {
    document.getElementById('importModal').classList.remove('active');
}

async function importFromJenkins() {
    openImportModal();
}

// ===================== Audit =====================
async function loadAuditLog(page = 1) {
    auditPage = page;
    const container = document.getElementById('auditContainer');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Загрузка...</div>';

    try {
        const res = await fetch(`${API_BASE}/api/audit?page=${page}&per_page=50`, { headers: getAuthHeader() });
        if (!res.ok) {
            if (res.status === 401) { logout(); return; }
            throw new Error('Failed to load audit');
        }
        const data = await res.json();

        if (!data.audit_log || data.audit_log.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="icon">📋</div>
                    <p>Записей аудита пока нет</p>
                </div>`;
            document.getElementById('auditPagination').innerHTML = '';
            return;
        }

        container.innerHTML = data.audit_log.map(entry => `
            <div class="audit-entry">
                <span class="audit-action ${entry.action}">${entry.action}</span>
                <span class="audit-resource">${escHtml(entry.resource || '')} ${escHtml(entry.resource_id ? '(' + entry.resource_id.substring(0, 8) + ')' : '')}</span>
                <span class="audit-time">${formatDate(entry.created_at)}</span>
            </div>
        `).join('');

        renderAuditPagination(data, 'auditPagination', loadAuditLog);
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><p>Ошибка: ${escHtml(e.message)}</p></div>`;
    }
}

function renderAuditPagination(data, containerId, callback) {
    const container = document.getElementById(containerId);
    if (!data.has_next && data.page <= 1) { container.innerHTML = ''; return; }
    let html = '';
    html += `<button class="page-btn" ${data.page <= 1 ? 'disabled' : ''} onclick="loadAuditLog(${data.page - 1})">←</button>`;
    html += `<span style="color:var(--text-secondary);font-size:0.85rem;padding:0 8px">Стр. ${data.page}</span>`;
    html += `<button class="page-btn" ${!data.has_next ? 'disabled' : ''} onclick="loadAuditLog(${data.page + 1})">→</button>`;
    container.innerHTML = html;
}

// ===================== Logout =====================
function logout() {
    localStorage.removeItem('secman_token');
    localStorage.removeItem('secman_username');
    window.location.href = '/login';
}

// ===================== Helpers =====================
function escHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escAttr(str) {
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"').replace(/\n/g, '\\n');
}

function formatDate(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    return d.toLocaleDateString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
}

// ===================== Init =====================
document.addEventListener('DOMContentLoaded', () => {
    // User info
    const username = localStorage.getItem('secman_username') || '';
    document.getElementById('userName').textContent = username;
    document.getElementById('userAvatar').textContent = username.charAt(0).toUpperCase();

    // Load data
    loadSecrets(1);
    loadStats();

    // Secret form submit
    document.getElementById('secretForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const editId = document.getElementById('editId').value;
        const keyName = document.getElementById('secretKey').value.trim();
        const value = document.getElementById('secretValue').value.trim();
        const description = document.getElementById('secretDesc').value.trim();

        if (!keyName || !value) {
            showToast('Заполните название и значение', 'error');
            return;
        }

        const url = editId ? `${API_BASE}/api/secrets/${editId}` : `${API_BASE}/api/secrets`;
        const method = editId ? 'PUT' : 'POST';

        try {
            const res = await fetch(url, {
                method,
                headers: getAuthHeader(),
                body: JSON.stringify({ key_name: keyName, value, description })
            });
            if (res.status === 401) { logout(); return; }
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || 'Failed');
            }
            showToast(editId ? 'Секрет обновлён' : 'Секрет создан', 'success');
            closeModal();
            loadSecrets(currentPage);
        } catch (err) {
            showToast('Ошибка: ' + err.message, 'error');
        }
    });

    // Import form submit
    document.getElementById('importForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const dataStr = document.getElementById('importData').value.trim();
        try {
            const data = JSON.parse(dataStr);
            if (!data.credentials || !Array.isArray(data.credentials)) {
                throw new Error('Неверный формат: нужен {"credentials": [...]}');
            }
            const res = await fetch(`${API_BASE}/api/secrets/import`, {
                method: 'POST',
                headers: getAuthHeader(),
                body: JSON.stringify(data)
            });
            if (res.status === 401) { logout(); return; }
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || 'Failed');
            }
            const result = await res.json();
            showToast(`Импортировано: ${result.imported} секретов`, 'success');
            closeImportModal();
            loadSecrets(1);
        } catch (err) {
            showToast('Ошибка: ' + err.message, 'error');
        }
    });

    // Close modals on overlay click
    document.getElementById('secretModal').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeModal();
    });
    document.getElementById('importModal').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeImportModal();
    });

    // Escape key to close modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { closeModal(); closeImportModal(); }
    });
});
