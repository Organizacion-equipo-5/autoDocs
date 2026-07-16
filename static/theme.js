// Botón de tema
const themeButton = document.getElementById('themeButton');
const themeIcon = document.getElementById('themeIcon');
const savedTheme = localStorage.getItem('theme') || 'dark';

function setThemeIcon(theme) {
  if (themeIcon) {
    themeIcon.textContent = theme === 'light' ? 'dark_mode' : 'light_mode';
  }
}

function applyTheme(theme) {
  // Para Tailwind CSS con darkMode: "class"
  if (theme === 'dark') {
    document.documentElement.classList.add('dark');
    document.documentElement.classList.remove('light');
  } else {
    document.documentElement.classList.remove('dark');
    document.documentElement.classList.add('light');
  }
  
  // Para compatibilidad con el sistema anterior
  document.body.setAttribute('data-theme', theme);
  document.documentElement.setAttribute('tema', theme);
  
  setThemeIcon(theme);
  localStorage.setItem('theme', theme);
}

// Aplicar tema guardado al cargar
applyTheme(savedTheme === 'light' ? 'light' : 'dark');

if (themeButton) {
  themeButton.addEventListener('click', () => {
    const currentTheme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    applyTheme(newTheme);
  });
}
