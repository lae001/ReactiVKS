import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/shared/lib/utils'

const links = [
  { to: '/meetings', label: 'Встречи' },
  { to: '/settings', label: 'Настройки' },
  { to: '/admin', label: 'Админ' },
]

export function Layout() {
  return (
    <div className="min-h-screen">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <NavLink to="/" className="text-lg font-semibold text-primary">
            ReactiVKS
          </NavLink>
          <nav aria-label="Основная навигация" className="flex gap-1">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-1.5 text-sm font-medium hover:bg-accent',
                    isActive && 'bg-accent text-accent-foreground',
                  )
                }
              >
                {l.label}
              </NavLink>
            ))}
            <NavLink
              to="/login"
              className="rounded-md px-3 py-1.5 text-sm font-medium hover:bg-accent"
            >
              Войти
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
