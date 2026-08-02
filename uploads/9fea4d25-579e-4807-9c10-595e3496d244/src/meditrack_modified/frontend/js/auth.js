/**
 * auth.js
 * Módulo de autenticación
 */

const AUTH = {
    user: null,
    token: localStorage.getItem('token'),
    isAuthenticated: !!localStorage.getItem('token'),

    /**
     * Iniciar sesión
     */
    async login(email, password) {
        try {
            const response = await API.login(email, password);
            
            if (response.ok && response.token) {
                this.token = response.token;
                this.user = response.user;
                this.isAuthenticated = true;
                
                // Guardar token
                localStorage.setItem('token', response.token);
                localStorage.setItem('user', JSON.stringify(response.user));
                
                // Actualizar API
                API.token = response.token;
                
                return true;
            }
            
            return false;
        } catch (error) {
            console.error('Error de login:', error);
            throw error;
        }
    },

    /**
     * Cerrar sesión
     */
    logout() {
        this.token = null;
        this.user = null;
        this.isAuthenticated = false;
        
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        
        API.token = null;
    },

    /**
     * Obtener usuario actual
     */
    getCurrentUser() {
        if (!this.user) {
            const stored = localStorage.getItem('user');
            if (stored) {
                this.user = JSON.parse(stored);
            }
        }
        return this.user;
    },

    /**
     * Verificar si el usuario está autenticado
     */
    isLoggedIn() {
        return this.isAuthenticated && !!this.token;
    },

    /**
     * Verificar si el usuario tiene un rol específico
     */
    hasRole(role) {
        return this.user && this.user.rol === role;
    },

    /**
     * Verificar si el usuario tiene uno de varios roles
     */
    hasAnyRole(roles) {
        return this.user && roles.includes(this.user.rol);
    },
};

// Restaurar sesión si existe
if (AUTH.isAuthenticated) {
    const stored = localStorage.getItem('user');
    if (stored) {
        AUTH.user = JSON.parse(stored);
    }
}

// Exportar para uso global
window.AUTH = AUTH;
