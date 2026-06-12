/**
 * api.js
 * Módulo para comunicación con el backend de Flask
 */

const API = {
    // URL base del servidor (ajustar si es necesario)
    baseURL: 'http://localhost:5000/api/v1',
    token: localStorage.getItem('token'),

    // ----- MÉTODOS GENERALES -----

    /**
     * Realiza una petición HTTP genérica
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        // Agregar token si existe
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers,
            });

            if (response.status === 401) {
                // Token expirado
                localStorage.removeItem('token');
                window.location.href = 'index.html';
                return null;
            }

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Error en la petición');
            }

            return data;
        } catch (error) {
            console.error('Error de API:', error);
            throw error;
        }
    },

    /**
     * GET request
     */
    get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    },

    /**
     * POST request
     */
    post(endpoint, body) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(body),
        });
    },

    /**
     * PUT request
     */
    put(endpoint, body) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(body),
        });
    },

    /**
     * DELETE request
     */
    delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    },

    // ----- AUTENTICACIÓN -----

    /**
     * Login del usuario
     */
    async login(email, password) {
        return this.post('/auth/login', { email, password });
    },

    /**
     * Registro de nuevo usuario
     */
    async register(userData) {
        return this.post('/auth/registro', userData);
    },

    /**
     * Logout del usuario
     */
    async logout() {
        localStorage.removeItem('token');
        this.token = null;
    },

    // ----- USUARIOS -----

    /**
     * Obtener todos los usuarios
     */
    async getUsers() {
        return this.get('/usuarios');
    },

    /**
     * Obtener usuario por ID
     */
    async getUser(userId) {
        return this.get(`/usuarios/${userId}`);
    },

    /**
     * Obtener usuario actual (perfil)
     */
    async getCurrentUser() {
        return this.get('/usuarios/me');
    },

    /**
     * Crear nuevo usuario
     */
    async createUser(userData) {
        return this.post('/auth/registro', userData);
    },

    /**
     * Actualizar usuario
     */
    async updateUser(userId, userData) {
        return this.put(`/usuarios/${userId}`, userData);
    },

    /**
     * Eliminar usuario
     */
    async deleteUser(userId) {
        return this.delete(`/usuarios/${userId}`);
    },

    // ----- MEDICINAS -----

    /**
     * Obtener todas las medicinas
     */
    async getMedications() {
        return this.get('/medications');
    },

    /**
     * Obtener medicina por ID
     */
    async getMedication(medId) {
        return this.get(`/medications/${medId}`);
    },

    /**
     * Crear nueva medicina
     */
    async createMedication(medData) {
        return this.post('/medications', medData);
    },

    /**
     * Actualizar medicina
     */
    async updateMedication(medId, medData) {
        return this.put(`/medications/${medId}`, medData);
    },

    /**
     * Eliminar medicina
     */
    async deleteMedication(medId) {
        return this.delete(`/medications/${medId}`);
    },

    // ----- REGISTRO DE TOMAS (LOGS) -----

    /**
     * Obtener logs de tomas de medicinas
     */
    async getMedicationLogs(filters = {}) {
        const query = new URLSearchParams(filters).toString();
        return this.get(`/medication-logs${query ? '?' + query : ''}`);
    },

    /**
     * Crear log de toma
     */
    async createMedicationLog(logData) {
        return this.post('/medication-logs', logData);
    },

    /**
     * Actualizar log de toma
     */
    async updateMedicationLog(logId, logData) {
        return this.put(`/medication-logs/${logId}`, logData);
    },

    // ----- NOTIFICACIONES -----

    /**
     * Obtener notificaciones
     */
    async getNotifications(filters = {}) {
        const query = new URLSearchParams(filters).toString();
        return this.get(`/notifications${query ? '?' + query : ''}`);
    },

    /**
     * Marcar notificación como leída
     */
    async readNotification(notifId) {
        return this.put(`/notifications/${notifId}`, { leida: true });
    },

    /**
     * Eliminar notificación
     */
    async deleteNotification(notifId) {
        return this.delete(`/notifications/${notifId}`);
    },

    // ----- DISPOSITIVOS IoT -----

    /**
     * Obtener dispositivos IoT
     */
    async getIoTDevices() {
        return this.get('/iot/devices');
    },

    /**
     * Obtener lecturas de dispositivos
     */
    async getIoTReadings(filters = {}) {
        const query = new URLSearchParams(filters).toString();
        return this.get(`/iot/readings${query ? '?' + query : ''}`);
    },
};

// Establecer token si existe en localStorage
API.token = localStorage.getItem('token');

// Exportar para uso global
window.API = API;
