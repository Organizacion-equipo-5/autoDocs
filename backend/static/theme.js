// Botón flotante de tema
const themeButton = document.getElementById('themeButton');
const themeIcon = document.getElementById('themeIcon');
const savedTheme = localStorage.getItem('theme') || 'dark';

function setThemeIcon(theme) {
  if (themeIcon) {
    themeIcon.textContent = theme === 'light' ? '🌙' : '☀️';
  }
}

function applyTheme(theme) {
  document.body.setAttribute('data-theme', theme);
  document.documentElement.setAttribute('tema', theme);
  setThemeIcon(theme);
  localStorage.setItem('theme', theme);
}

// Aplicar tema guardado al cargar
applyTheme(savedTheme === 'light' ? 'light' : 'dark');

if (themeButton) {
  themeButton.addEventListener('click', () => {
    const currentTheme = document.body.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    applyTheme(currentTheme);
  });
}
