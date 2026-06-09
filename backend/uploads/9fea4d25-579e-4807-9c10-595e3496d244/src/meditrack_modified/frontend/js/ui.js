/**
 * ui.js
 * Módulo para utilidades de UI - con Material Icons, sin emojis
 */

const UI = {
    /**
     * Mostrar notificación
     */
    notify(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;

        const iconMap = { success: 'check_circle', error: 'error', warning: 'warning', info: 'info' };
        notification.innerHTML = `<span class="material-icons notif-icon">${iconMap[type] || 'info'}</span> ${message}`;
        
        document.body.appendChild(notification);
        setTimeout(() => notification.classList.add('show'), 10);
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    },

    error(message)   { this.notify(message, 'error'); },
    success(message) { this.notify(message, 'success'); },
    info(message)    { this.notify(message, 'info'); },
    warning(message) { this.notify(message, 'warning'); },

    /**
     * Mostrar/ocultar loading
     */
    showLoading(show = true) {
        const loadingScreen = document.getElementById('loading-screen');
        if (show) loadingScreen?.classList.remove('hidden');
        else      loadingScreen?.classList.add('hidden');
    },

    /**
     * Mostrar modal
     */
    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        }
    },

    /**
     * Ocultar modal
     */
    hideModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('hidden');
            document.body.style.overflow = '';
        }
    },

    /**
     * Cambiar pestaña login/registro
     */
    switchAuthTab(tab) {
        document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.auth-panel').forEach(p => p.classList.add('hidden'));
        document.querySelectorAll('.alert').forEach(a => a.classList.add('hidden'));

        document.getElementById(`tab-${tab}`)?.classList.add('active');
        document.querySelector(`[data-panel="${tab}"]`)?.classList.remove('hidden');
    },

    /**
     * Mostrar/ocultar contraseña
     */
    togglePassword(inputId, btn) {
        const input = document.getElementById(inputId);
        if (!input) return;
        const icon = btn ? btn.querySelector('.material-icons') : null;
        if (input.type === 'password') {
            input.type = 'text';
            if (icon) icon.textContent = 'visibility_off';
        } else {
            input.type = 'password';
            if (icon) icon.textContent = 'visibility';
        }
    },

    /**
     * Cambiar página visible
     */
    showPage(pageName) {
        document.querySelectorAll('.page').forEach(page => page.classList.add('hidden'));

        const page = document.getElementById(`${pageName}-page`);
        if (page) page.classList.remove('hidden');

        const titleMap = {
            'dashboard':     'Dashboard',
            'medications':   'Gestión de Medicinas',
            'users':         'Gestión de Usuarios',
            'logs':          'Registro de Tomas',
            'notifications': 'Notificaciones',
        };
        document.getElementById('page-title').textContent = titleMap[pageName] || pageName;

        document.querySelectorAll('.nav-link').forEach(link => link.classList.remove('active'));
        document.querySelector(`[data-page="${pageName}"]`)?.classList.add('active');
    },

    showLoginPage() {
        document.getElementById('login-page').classList.remove('hidden');
        document.getElementById('main-app').classList.add('hidden');
    },

    showMainApp() {
        document.getElementById('login-page').classList.add('hidden');
        document.getElementById('main-app').classList.remove('hidden');
        this.showPage('dashboard');
    },

    /**
     * Mostrar/ocultar enlaces de admin en el sidebar
     */
    applyRoleVisibility(rol) {
        if (rol === 'admin') {
            document.querySelectorAll('.nav-admin-only').forEach(el => el.classList.remove('hidden'));
        } else {
            document.querySelectorAll('.nav-admin-only').forEach(el => el.classList.add('hidden'));
        }
    },

    formatTime(time)     { return time ? time.split(':').slice(0, 2).join(':') : ''; },
    formatDate(date) {
        if (!date) return '';
        return new Date(date).toLocaleDateString('es-ES', { year: 'numeric', month: 'long', day: 'numeric' });
    },
    formatDateTime(date) {
        if (!date) return '';
        return new Date(date).toLocaleString('es-ES', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    },

    /**
     * Icono de estado usando Material Icons
     */
    getStatusIcon(status) {
        const icons = {
            'tomado':   '<span class="material-icons status-icon status-tomado">check_circle</span>',
            'omitido':  '<span class="material-icons status-icon status-omitido">cancel</span>',
            'retrasado':'<span class="material-icons status-icon status-retrasado">alarm_on</span>',
            'pendiente':'<span class="material-icons status-icon status-pendiente">hourglass_empty</span>',
        };
        return icons[status] || '<span class="material-icons status-icon">help</span>';
    },

    /**
     * Tarjeta de medicina
     */
    createMedicationCard(medication) {
        const card = document.createElement('div');
        card.className = 'medication-card';
        card.innerHTML = `
            <div class="medication-header">
                <span class="material-icons med-card-icon">medication</span>
                <h4>${medication.nombre}</h4>
                <span class="badge badge-${medication.activo ? 'success' : 'danger'}">
                    ${medication.activo ? 'Activo' : 'Inactivo'}
                </span>
            </div>
            <div class="medication-info">
                <p><span class="material-icons info-icon">category</span><strong>Forma:</strong> ${medication.forma}</p>
                <p><span class="material-icons info-icon">colorize</span><strong>Dosis:</strong> ${medication.dosis}</p>
                <p><span class="material-icons info-icon">repeat</span><strong>Frecuencia:</strong> ${medication.frecuencia}</p>
                <p><span class="material-icons info-icon">schedule</span><strong>Horarios:</strong> ${medication.horarios.join(', ')}</p>
                ${medication.indicaciones ? `<p><span class="material-icons info-icon">notes</span><strong>Notas:</strong> ${medication.indicaciones}</p>` : ''}
            </div>
            <div class="medication-actions">
                <button class="btn btn-sm btn-primary edit-med-btn" data-id="${medication._id}">
                    <span class="material-icons">edit</span> Editar
                </button>
                <button class="btn btn-sm btn-danger delete-med-btn" data-id="${medication._id}">
                    <span class="material-icons">delete</span> Eliminar
                </button>
            </div>
        `;
        return card;
    },

    /**
     * Tarjeta de usuario (solo admin)
     */
    createUserCard(user) {
        const card = document.createElement('div');
        card.className = 'user-card';
        card.innerHTML = `
            <div class="user-avatar-lg">
                <span class="material-icons">account_circle</span>
            </div>
            <div class="user-info-block">
                <h4>${user.nombre} ${user.apellido}</h4>
                <p class="user-email"><span class="material-icons info-icon">email</span>${user.email}</p>
                <p class="user-role-badge"><span class="badge badge-blue">${user.rol}</span></p>
                ${user.telefono ? `<p class="user-phone"><span class="material-icons info-icon">phone</span>${user.telefono}</p>` : ''}
                <p><span class="badge badge-${user.activo ? 'success' : 'danger'}">${user.activo ? 'Activo' : 'Inactivo'}</span></p>
            </div>
            <div class="user-actions">
                <button class="btn btn-sm btn-primary edit-user-btn" data-id="${user._id}">
                    <span class="material-icons">edit</span> Editar
                </button>
                <button class="btn btn-sm btn-${user.activo ? 'danger' : 'success'} toggle-user-btn" data-id="${user._id}" data-activo="${user.activo}">
                    <span class="material-icons">${user.activo ? 'person_off' : 'person'}</span>
                    ${user.activo ? 'Desactivar' : 'Activar'}
                </button>
            </div>
        `;
        return card;
    },

    /**
     * Item de notificación
     */
    createNotificationItem(notification) {
        const item = document.createElement('div');
        item.className = `notification-item ${notification.leida ? 'read' : 'unread'}`;
        item.innerHTML = `
            <div class="notif-item-icon">
                <span class="material-icons">${notification.leida ? 'notifications_none' : 'notifications_active'}</span>
            </div>
            <div class="notification-content">
                <h4>${notification.titulo}</h4>
                <p>${notification.mensaje}</p>
                <small>${this.formatDateTime(notification.creado_en)}</small>
            </div>
            <button class="btn btn-sm btn-secondary delete-notif-btn" data-id="${notification._id}">
                <span class="material-icons">delete</span>
            </button>
        `;
        return item;
    },
};

window.UI = UI;
