import html

def get_theme_html_head(page_title="Dashboard", favicon_url="https://servercv.com/assets/icon.png", csrf_token=None):
    """
    Returns the HTML head section with Tailwind CSS and Google Fonts
    """
    description = "Build a verified portfolio of your server contributions. Perfect for staff applications and sharing your achievements in the Discord community."
    return f"""
    <head>
        <meta charset="UTF-8">
        {f'<meta name="csrf-token" content="{csrf_token}">' if csrf_token else ''}
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{page_title} | ServerCV</title>
        <meta name="description" content="{description}">
        <meta name="author" content="ServerCV">
        <meta name="keywords" content="Discord Resume, Discord Portfolio, Discord Staff, Server Contributions, Discord Experience, Verified History, Discord Community, Staff Application, ServerCV">
        <meta name="creator" content="ServerCV">
        <meta name="publisher" content="ServerCV">
        <meta name="robots" content="index, follow">
        <meta property="og:title" content="{page_title} | ServerCV">
        <meta property="og:description" content="{description}">
        <meta property="og:type" content="website">
        <meta property="og:site_name" content="ServerCV">
        <meta property="og:image" content="{favicon_url}">
        <meta name="theme-color" content="#5A4BEB">
        <meta name="twitter:card" content="summary">
        <meta name="twitter:title" content="{page_title} | ServerCV">
        <meta name="twitter:description" content="{description}">
        <meta name="twitter:image" content="{favicon_url}">
        <link rel="icon" type="image/png" sizes="32x32" href="{favicon_url}">
        <link rel="icon" type="image/png" sizes="16x16" href="{favicon_url}">
        <link rel="apple-touch-icon" sizes="180x180" href="{favicon_url}">
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Inter', sans-serif; }}
            .glass {{ background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); }}
        </style>
        <script>
            tailwind.config = {{
                darkMode: 'class',
                theme: {{
                    extend: {{
                        colors: {{
                            gray: {{
                                900: '#111827',
                                800: '#1f2937',
                                700: '#374151',
                            }}
                        }}
                    }}
                }}
            }}
        </script>
    </head>
    """


def get_navbar(title="ServerCV", nav_links=None):
    """
    Returns a complete mobile-responsive navbar
    """
    if nav_links is None:
        nav_links = []
    
    # Desktop links
    desktop_links_html = ""
    for url, text, classes in nav_links:
        desktop_links_html += f'<a href="{url}" class="text-gray-300 hover:text-white px-3 py-2 rounded-md text-sm font-medium transition-colors {classes}">{text}</a>'

    # Mobile links
    mobile_links_html = ""
    for url, text, classes in nav_links:
        mobile_links_html += f'<a href="{url}" class="text-gray-300 hover:text-white block px-3 py-2 rounded-md text-base font-medium {classes}">{text}</a>'

    return f"""
    <nav class="bg-gray-900 border-b border-gray-800 sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex items-center justify-between h-16">
                <div class="flex items-center">
                    <div class="flex-shrink-0">
                        <a href="/" class="text-xl font-bold text-white flex items-center gap-2">
                            <img src="https://servercv.com/assets/icon.png" alt="Logo" class="h-8 w-8 rounded-full">
                            <span>ServerCV</span>
                        </a>
                    </div>
                    <div class="hidden md:block">
                        <div class="ml-10 flex items-baseline space-x-4">
                            {desktop_links_html}
                        </div>
                    </div>
                </div>
                <div class="-mr-2 flex md:hidden">
                    <!-- Mobile menu button -->
                    <button type="button" onclick="document.getElementById('mobile-menu').classList.toggle('hidden')" class="bg-gray-800 inline-flex items-center justify-center p-2 rounded-md text-gray-400 hover:text-white hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-gray-800 focus:ring-white" aria-controls="mobile-menu" aria-expanded="false">
                        <span class="sr-only">Open main menu</span>
                        <svg class="block h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>

        <!-- Mobile menu, show/hide based on menu state. -->
        <div class="hidden md:hidden" id="mobile-menu">
            <div class="px-2 pt-2 pb-3 space-y-1 sm:px-3">
                {mobile_links_html}
            </div>
        </div>
    </nav>
    """


def wrap_page(title, content, nav_links=None, favicon_url=None, csrf_token=None):
    """
    Wraps content in a complete HTML page
    """
    if nav_links is None:
        nav_links = [("/dashboard", "Dashboard", "")]
        
    head = get_theme_html_head(title, favicon_url if favicon_url else "https://servercv.com/assets/icon.png", csrf_token=csrf_token)
    navbar = get_navbar("ServerCV", nav_links)
    
    return f"""
    <!DOCTYPE html>
    <html lang="en" class="dark">
    {head}
    <body class="bg-gray-950 text-gray-100 min-h-screen flex flex-col">
        {navbar}
        <main class="flex-grow">
            <div class="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
                {content}
            </div>
        </main>
        <footer class="bg-gray-900 border-t border-gray-800 mt-auto">
            <div class="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
                <p class="text-center text-gray-500 text-sm">
                    &copy; <script>document.write(new Date().getFullYear())</script> <a href="https://iancheung.dev">Ian Cheung</a>. All rights reserved.
                </p>
            </div>
        </footer>
    </body>
    </html>
    """


def error_page(message, status_code=400):
    content = f"""
    <div class="max-w-md mx-auto">
        <div class="glass p-8 rounded-2xl text-center">
            <h2 class="text-2xl font-semibold mb-4 text-red-500">Error {status_code}</h2>
            <p class="text-gray-400">{html.escape(message)}</p>
            <a href="/dashboard" class="mt-6 inline-block bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-lg font-semibold transition-all transform hover:scale-[1.02]">Return to Dashboard</a>
        </div>
    </div>
    """
    return wrap_page("Error", content), status_code