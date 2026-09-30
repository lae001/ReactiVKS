import { PageStub } from '@/shared/ui/stub';

export function AdminPage() {
  return (
    <PageStub
      title="Администрирование"
      lead="Пользователи, идущие встречи и состояние сервисов Системы."
      planned={[
        'Список пользователей, блокировка',
        'Активные встречи и число участников',
        'Состояние сервисов: auth, meeting, realtime, analytics, ML, LiveKit',
      ]}
      tasks="UC-7, спринт 6"
    />
  );
}
