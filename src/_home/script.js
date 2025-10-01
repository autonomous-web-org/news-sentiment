// import "/src/globals/header.js";

function toggleTheme() {
            document.documentElement.classList.toggle('dark');
        }

            // This is a simplified theme toggle for demonstration purposes.
    // In a real app, you would likely use localStorage to remember the user's preference.
    const themeToggleButton = document.querySelector('#toggle-theme-btn');
    themeToggleButton.addEventListener("click", (e) => {
    	console.log(1)
    	toggleTheme();
    })
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches && !document.documentElement.classList.contains('dark')) {
        // If system preference is dark and not manually overridden, set dark mode.
        toggleTheme();
    }