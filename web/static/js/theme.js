(function () {
    var root = document.documentElement; // <html>
    var btn = document.getElementById('theme-toggle');
    var icon = document.getElementById('theme-icon');

    function applyTheme(dark) {
        if (dark) {
            root.classList.add('dark-mode');
            if (icon) { icon.classList.remove('fa-moon'); icon.classList.add('fa-sun'); }
            if (btn) btn.title = 'Cambiar a modo claro';
        } else {
            root.classList.remove('dark-mode');
            if (icon) { icon.classList.remove('fa-sun'); icon.classList.add('fa-moon'); }
            if (btn) btn.title = 'Cambiar a modo oscuro';
        }
    }

    // Sincronizar ícono con el estado actual (la clase ya fue aplicada en el <head>)
    applyTheme(root.classList.contains('dark-mode'));

    if (btn) {
        btn.addEventListener('click', function () {
            var isDark = root.classList.contains('dark-mode');
            applyTheme(!isDark);
            localStorage.setItem('lms-theme', isDark ? 'light' : 'dark');
        });
    }
})();
