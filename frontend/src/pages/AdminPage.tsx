import { UsersSection } from '@/features/admin/UsersSection';
import { ServiceSections } from '@/features/admin/ServiceSections';
import { resolveApiMode } from '@/shared/api/meetings';

/** Администрирование: пользователи auth-service, встречи и состояние meeting-service. */
export function AdminPage() {
  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">Администрирование</h1>
        <p className="text-muted-foreground">Пользователи, встречи и состояние сервисов Системы.</p>
        {resolveApiMode(import.meta.env.VITE_API_MODE) === 'mock' && (
          <p role="status">Демонстрационный режим: тестовые пользователи и состояние сервисов.</p>
        )}
      </header>
      <UsersSection />
      <ServiceSections />
    </div>
  );
}
