import { Settings, Shield, Video } from 'lucide-react';
import { NavLink, Outlet } from 'react-router';

import { paths } from '@/shared/config/routes';
import { cn } from '@/shared/lib/utils';
import { Wordmark } from '@/shared/ui/brand';
import { Button } from '@/shared/ui/button';

const nav = [
  { to: paths.meetings, label: 'Встречи', icon: Video, end: false },
  { to: paths.settings, label: 'Настройки', icon: Settings, end: true },
  // Пункт виден только администратору – появится вместе с ролями (EMO-40)
  { to: paths.admin, label: 'Администрирование', icon: Shield, end: true },
];

/** Каркас страниц организатора и администратора: шапка с навигацией и область контента. */
export function AppLayout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b bg-card">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-8 px-4 md:px-6">
          <NavLink to={paths.meetings} aria-label="ReactiVKS – к списку встреч">
            <Wordmark />
          </NavLink>
          <nav className="flex flex-1 items-center gap-1" aria-label="Основная навигация">
            {nav.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    'inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground',
                    isActive && 'bg-accent text-accent-foreground',
                  )
                }
              >
                <Icon className="size-4" aria-hidden />
                <span className="hidden sm:inline">{label}</span>
              </NavLink>
            ))}
          </nav>
          {/* Имя пользователя и выход – после подключения auth-service (EMO-40) */}
          <Button variant="ghost" size="sm" asChild>
            <NavLink to={paths.login}>Выйти</NavLink>
          </Button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:px-6 md:py-10">
        <Outlet />
      </main>
    </div>
  );
}
