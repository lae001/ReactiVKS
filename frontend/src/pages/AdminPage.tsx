import { UsersSection } from '@/features/admin/UsersSection';
import { Badge } from '@/shared/ui/badge';

/**
 * Администрирование (UC-7). Пользователи – настоящие данные auth-service (в режиме mock – тестовые).
 * Идущие встречи и состояние сервисов остаются заглушками: GET /admin/meetings и /admin/health в
 * meeting-service пока не реализованы.
 */
export function AdminPage() {
  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">Администрирование</h1>
        <p className="text-muted-foreground">
          Пользователи, идущие встречи и состояние сервисов Системы.
        </p>
      </header>

      <UsersSection />

      <section aria-labelledby="admin-meetings" className="flex flex-col gap-2">
        <h2 id="admin-meetings" className="flex items-center gap-2 text-lg font-semibold">
          Активные встречи <Badge variant="outline">Скоро</Badge>
        </h2>
        <p className="text-sm text-muted-foreground">
          Список появится, когда сервер начнет отдавать встречи для администратора.
        </p>
      </section>

      <section aria-labelledby="admin-health" className="flex flex-col gap-2">
        <h2 id="admin-health" className="flex items-center gap-2 text-lg font-semibold">
          Состояние сервисов <Badge variant="outline">Скоро</Badge>
        </h2>
        <p className="text-sm text-muted-foreground">
          Auth, meeting, realtime, analytics, ML и LiveKit – после появления проверки состояния на
          сервере.
        </p>
      </section>
    </div>
  );
}
