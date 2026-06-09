/**
 * app.js - Lógica principal de MediTrack
 * - Registro de usuarios (formulario en login)
 * - CRUD de usuarios solo para admin
 * - Sin emojis, con Material Icons
 */

const App = {
    currentUser: null,
    medications: [],
    users: [],
    logs: [],
    notifications: [],

    async init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.start());
        } else {
            this.start();
        }
    },

    async start() {
        this.setupEventListeners();

        if (AUTH.isLoggedIn()) {
            this.currentUser = AUTH.getCurrentUser();
            UI.showMainApp();
            UI.applyRoleVisibility(this.currentUser.rol);
            await this.loadDashboard();
        } else {
            UI.showLoginPage();
            UI.showLoading(false);
        }
    },

    setupEventListeners() {
        // Login
        document.getElementById('login-form')?.addEventListener('submit', (e) => this.handleLogin(e));

        // Registro
        document.getElementById('register-form')?.addEventListener('submit', (e) => this.handleRegister(e));

        // Logout
        document.getElementById('logout-btn')?.addEventListener('click', () => this.handleLogout());

        // Navegación
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = link.dataset.page;

                // Solo admin puede ver usuarios
                if (page === 'users' && this.currentUser?.rol !== 'admin') {
                    UI.warning('Solo los administradores pueden gestionar usuarios');
                    return;
                }
                this.navigateTo(page);
            });
        });

        // Medicamentos
        document.getElementById('add-medication-btn')?.addEventListener('click', () => this.showMedicationModal());
        document.getElementById('medication-form')?.addEventListener('submit', (e) => this.handleSaveMedication(e));

        // Cerrar modal medicamento
        document.querySelectorAll('.modal-close, .modal-close-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                UI.hideModal('medication-modal');
            });
        });

        // Usuarios (admin)
        document.getElementById('add-user-btn')?.addEventListener('click', () => this.showUserModal());
        document.getElementById('user-form')?.addEventListener('submit', (e) => this.handleSaveUser(e));

        // Cerrar modal usuario
        document.querySelectorAll('.user-modal-close, .user-modal-close-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                UI.hideModal('user-modal');
            });
        });

        // Notificaciones
        document.getElementById('notif-btn')?.addEventListener('click', () => this.navigateTo('notifications'));

        // Búsqueda
        document.getElementById('search-input')?.addEventListener('input', (e) => this.handleSearch(e.target.value));

        // Sidebar toggle
        document.querySelector('.sidebar-toggle')?.addEventListener('click', () => {
            document.querySelector('.sidebar').classList.toggle('hidden');
        });
    },

    // ─── LOGIN ───────────────────────────────────────────
    async handleLogin(e) {
        e.preventDefault();
        const email    = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const errorDiv = document.getElementById('login-error');

        try {
            errorDiv.classList.add('hidden');
            UI.showLoading(true);
            const success = await AUTH.login(email, password);
            if (success) {
                this.currentUser = AUTH.getCurrentUser();
                UI.showMainApp();
                UI.applyRoleVisibility(this.currentUser.rol);
                await this.loadDashboard();
                UI.success('Bienvenido a MediTrack');
            } else {
                errorDiv.textContent = 'Email o contraseña incorrectos';
                errorDiv.classList.remove('hidden');
            }
        } catch (err) {
            errorDiv.textContent = 'Error al iniciar sesion: ' + err.message;
            errorDiv.classList.remove('hidden');
        } finally {
            UI.showLoading(false);
        }
    },

    // ─── REGISTRO ────────────────────────────────────────
    async handleRegister(e) {
        e.preventDefault();
        const errorDiv   = document.getElementById('register-error');
        const successDiv = document.getElementById('register-success');
        errorDiv.classList.add('hidden');
        successDiv.classList.add('hidden');

        const nombre    = document.getElementById('reg-nombre').value.trim();
        const apellido  = document.getElementById('reg-apellido').value.trim();
        const email     = document.getElementById('reg-email').value.trim();
        const telefono  = document.getElementById('reg-telefono').value.trim();
        const rol       = document.getElementById('reg-rol').value;
        const password  = document.getElementById('reg-password').value;
        const password2 = document.getElementById('reg-password2').value;

        if (password !== password2) {
            errorDiv.textContent = 'Las contraseñas no coinciden';
            errorDiv.classList.remove('hidden');
            return;
        }

        try {
            UI.showLoading(true);
            await API.register({ nombre, apellido, email, password, rol, telefono });

            successDiv.textContent = '¡Cuenta creada! Ya puedes iniciar sesion.';
            successDiv.classList.remove('hidden');
            document.getElementById('register-form').reset();

            // Cambiar a tab de login después de 1.5s
            setTimeout(() => UI.switchAuthTab('login'), 1500);
        } catch (err) {
            errorDiv.textContent = err.message || 'Error al crear la cuenta';
            errorDiv.classList.remove('hidden');
        } finally {
            UI.showLoading(false);
        }
    },

    // ─── LOGOUT ──────────────────────────────────────────
    handleLogout() {
        if (confirm('¿Deseas cerrar sesion?')) {
            AUTH.logout();
            UI.showLoginPage();
            document.getElementById('email').value    = '';
            document.getElementById('password').value = '';
            UI.info('Sesion cerrada');
        }
    },

    // ─── NAVEGACIÓN ──────────────────────────────────────
    async navigateTo(page) {
        UI.showPage(page);
        switch (page) {
            case 'dashboard':     await this.loadDashboard();     break;
            case 'medications':   await this.loadMedications();   break;
            case 'users':         await this.loadUsers();         break;
            case 'logs':          await this.loadLogs();          break;
            case 'notifications': await this.loadNotifications(); break;
        }
    },

    // ─── DASHBOARD ───────────────────────────────────────
    async loadDashboard() {
        try {
            document.getElementById('user-name').textContent =
                `${this.currentUser.nombre} ${this.currentUser.apellido}`;
            document.getElementById('user-role').textContent = this.currentUser.rol;

            const [usersRes, medsRes, logsRes] = await Promise.all([
                API.getUsers().catch(() => ({ data: [] })),
                API.getMedications().catch(() => ({ data: [] })),
                API.getMedicationLogs().catch(() => ({ data: [] })),
            ]);

            this.users       = usersRes.data  || [];
            this.medications = medsRes.data   || [];
            this.logs        = logsRes.data   || [];

            document.getElementById('stat-users').textContent       = this.users.length;
            document.getElementById('stat-medications').textContent = this.medications.length;

            const today = new Date().toDateString();
            const todayLogs = this.logs.filter(l => new Date(l.creado_en).toDateString() === today);
            document.getElementById('stat-completed').textContent = todayLogs.filter(l => l.estado === 'tomado').length;
            document.getElementById('stat-pending').textContent   = todayLogs.filter(l => l.estado === 'pendiente').length;

            this.displayUpcomingMedications();
        } catch (err) {
            console.error('Error cargando dashboard:', err);
            UI.error('Error al cargar el dashboard');
        }
    },

    displayUpcomingMedications() {
        const container = document.getElementById('upcoming-medications');
        container.innerHTML = '';

        const active = this.medications.filter(m => m.activo).slice(0, 5);
        if (!active.length) {
            container.innerHTML = '<p class="empty-state">No hay medicinas registradas</p>';
            return;
        }
        active.forEach(med => {
            const item = document.createElement('div');
            item.className = 'medication-item';
            item.innerHTML = `
                <span class="material-icons med-item-icon">medication</span>
                <div class="medication-time">
                    <strong>${med.nombre}</strong>
                    <span class="badge">${med.dosis}</span>
                </div>
                <div class="medication-schedule">
                    ${med.horarios.map(h => `<span class="time-badge">${h}</span>`).join('')}
                </div>
            `;
            container.appendChild(item);
        });
    },

    // ─── MEDICAMENTOS ────────────────────────────────────
    async loadMedications() {
        try {
            const response = await API.getMedications();
            this.medications = response.data || [];

            const container = document.getElementById('medications-container');
            container.innerHTML = '';

            if (!this.medications.length) {
                container.innerHTML = '<p class="empty-state">No hay medicinas registradas</p>';
                return;
            }

            this.medications.forEach(med => container.appendChild(UI.createMedicationCard(med)));
            this.setupMedicationActions();
        } catch (err) {
            console.error('Error cargando medicinas:', err);
            UI.error('Error al cargar medicinas');
        }
    },

    setupMedicationActions() {
        document.querySelectorAll('.edit-med-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const medId = e.currentTarget.dataset.id;
                const med   = this.medications.find(m => m._id === medId);
                if (med) this.showMedicationModal(med);
            });
        });
        document.querySelectorAll('.delete-med-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const medId = e.currentTarget.dataset.id;
                if (confirm('¿Eliminar esta medicina?')) this.deleteMedication(medId);
            });
        });
    },

    showMedicationModal(medication = null) {
        const form  = document.getElementById('medication-form');
        const title = document.getElementById('modal-title');
        if (medication) {
            title.textContent = 'Editar Medicina';
            document.getElementById('med-name').value      = medication.nombre;
            document.getElementById('med-form').value      = medication.forma;
            document.getElementById('med-dose').value      = medication.dosis;
            document.getElementById('med-frequency').value = medication.frecuencia;
            document.getElementById('med-schedule').value  = medication.horarios.join(', ');
            document.getElementById('med-notes').value     = medication.indicaciones || '';
            form.dataset.medId = medication._id;
        } else {
            title.textContent = 'Agregar Medicina';
            form.reset();
            delete form.dataset.medId;
        }
        UI.showModal('medication-modal');
    },

    async handleSaveMedication(e) {
        e.preventDefault();
        try {
            const form  = document.getElementById('medication-form');
            const medId = form.dataset.medId;
            const data  = {
                nombre:       document.getElementById('med-name').value,
                forma:        document.getElementById('med-form').value,
                dosis:        document.getElementById('med-dose').value,
                frecuencia:   document.getElementById('med-frequency').value,
                horarios:     document.getElementById('med-schedule').value.split(',').map(h => h.trim()),
                indicaciones: document.getElementById('med-notes').value,
            };
            if (medId) {
                await API.updateMedication(medId, data);
                UI.success('Medicina actualizada');
            } else {
                await API.createMedication(data);
                UI.success('Medicina creada');
            }
            UI.hideModal('medication-modal');
            await this.loadMedications();
        } catch (err) {
            console.error('Error guardando medicina:', err);
            UI.error('Error al guardar medicina');
        }
    },

    async deleteMedication(medId) {
        try {
            await API.deleteMedication(medId);
            UI.success('Medicina eliminada');
            await this.loadMedications();
        } catch (err) {
            UI.error('Error al eliminar medicina');
        }
    },

    // ─── USUARIOS (solo admin) ───────────────────────────
    async loadUsers() {
        if (this.currentUser?.rol !== 'admin') {
            UI.warning('Acceso restringido: solo administradores');
            this.navigateTo('dashboard');
            return;
        }

        try {
            const response = await API.getUsers();
            this.users = response.data || [];

            const container = document.getElementById('users-container');
            container.innerHTML = '';

            if (!this.users.length) {
                container.innerHTML = '<p class="empty-state">No hay usuarios registrados</p>';
                return;
            }
            this.users.forEach(user => container.appendChild(UI.createUserCard(user)));
            this.setupUserActions();
        } catch (err) {
            console.error('Error cargando usuarios:', err);
            UI.error('Error al cargar usuarios');
        }
    },

    setupUserActions() {
        document.querySelectorAll('.edit-user-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const userId = e.currentTarget.dataset.id;
                const user   = this.users.find(u => u._id === userId);
                if (user) this.showUserModal(user);
            });
        });

        document.querySelectorAll('.toggle-user-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const userId = e.currentTarget.dataset.id;
                const activo = e.currentTarget.dataset.activo === 'true';
                const action = activo ? 'desactivar' : 'activar';
                if (confirm(`¿Deseas ${action} este usuario?`)) {
                    await this.toggleUserStatus(userId, activo);
                }
            });
        });
    },

    showUserModal(user = null) {
        const form  = document.getElementById('user-form');
        const title = document.getElementById('user-modal-title');

        if (user) {
            title.textContent = 'Editar Usuario';
            document.getElementById('user-nombre').value   = user.nombre;
            document.getElementById('user-apellido').value = user.apellido;
            document.getElementById('user-email').value    = user.email;
            document.getElementById('user-telefono').value = user.telefono || '';
            document.getElementById('user-rol').value      = user.rol;
            document.getElementById('user-activo').checked = user.activo;
            document.getElementById('user-password').value = '';
            form.dataset.userId = user._id;
        } else {
            title.textContent = 'Agregar Usuario';
            form.reset();
            document.getElementById('user-activo').checked = true;
            delete form.dataset.userId;
        }
        UI.showModal('user-modal');
    },

    async handleSaveUser(e) {
        e.preventDefault();
        const form   = document.getElementById('user-form');
        const userId = form.dataset.userId;

        const data = {
            nombre:   document.getElementById('user-nombre').value.trim(),
            apellido: document.getElementById('user-apellido').value.trim(),
            email:    document.getElementById('user-email').value.trim(),
            telefono: document.getElementById('user-telefono').value.trim(),
            rol:      document.getElementById('user-rol').value,
            activo:   document.getElementById('user-activo').checked,
        };

        const password = document.getElementById('user-password').value;
        if (password) data.password = password;

        try {
            if (userId) {
                // Editar usuario existente
                await API.updateUser(userId, data);
                UI.success('Usuario actualizado');
            } else {
                // Crear nuevo usuario (requiere contraseña)
                if (!password) {
                    UI.error('La contraseña es obligatoria al crear un usuario');
                    return;
                }
                await API.createUser(data);
                UI.success('Usuario creado');
            }
            UI.hideModal('user-modal');
            await this.loadUsers();
        } catch (err) {
            console.error('Error guardando usuario:', err);
            UI.error(err.message || 'Error al guardar usuario');
        }
    },

    async toggleUserStatus(userId, currentlyActive) {
        try {
            if (currentlyActive) {
                await API.deleteUser(userId);   // desactiva
                UI.success('Usuario desactivado');
            } else {
                await API.activateUser(userId); // reactiva
                UI.success('Usuario activado');
            }
            await this.loadUsers();
        } catch (err) {
            UI.error('Error al cambiar estado del usuario');
        }
    },

    // ─── LOGS ────────────────────────────────────────────
    async loadLogs() {
        try {
            const response = await API.getMedicationLogs();
            this.logs = response.data || [];

            const container = document.getElementById('logs-container');
            container.innerHTML = '';

            if (!this.logs.length) {
                container.innerHTML = '<p class="empty-state">No hay registros de tomas</p>';
                return;
            }

            this.logs.forEach(log => {
                const item = document.createElement('div');
                item.className = 'log-item';
                item.innerHTML = `
                    <div class="log-status">${UI.getStatusIcon(log.estado)}</div>
                    <div class="log-info">
                        <strong>${log.medicamento_id}</strong>
                        <p class="log-time">${UI.formatDateTime(log.hora_programada)}</p>
                        ${log.notas ? `<p class="log-notes">${log.notas}</p>` : ''}
                    </div>
                    <div class="log-state">
                        <span class="badge badge-${log.estado}">${log.estado}</span>
                    </div>
                `;
                container.appendChild(item);
            });
        } catch (err) {
            console.error('Error cargando logs:', err);
            UI.error('Error al cargar logs');
        }
    },

    // ─── NOTIFICACIONES ──────────────────────────────────
    async loadNotifications() {
        try {
            const response = await API.getNotifications();
            this.notifications = response.data || [];

            const container = document.getElementById('notifications-container');
            container.innerHTML = '';

            if (!this.notifications.length) {
                container.innerHTML = '<p class="empty-state">No hay notificaciones</p>';
                return;
            }

            this.notifications.forEach(notif => container.appendChild(UI.createNotificationItem(notif)));
            this.setupNotificationActions();

            const unreadCount = this.notifications.filter(n => !n.leida).length;
            const badge = document.getElementById('notif-count');
            if (unreadCount > 0) {
                badge.textContent = unreadCount;
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        } catch (err) {
            console.error('Error cargando notificaciones:', err);
            UI.error('Error al cargar notificaciones');
        }
    },

    setupNotificationActions() {
        document.querySelectorAll('.delete-notif-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const notifId = e.currentTarget.dataset.id;
                this.deleteNotification(notifId);
            });
        });
    },

    async deleteNotification(notifId) {
        try {
            await API.deleteNotification(notifId);
            await this.loadNotifications();
        } catch (err) {
            console.error('Error eliminando notificación:', err);
        }
    },

    handleSearch(query) {
        console.log('Búsqueda:', query);
    },
};

App.init();
