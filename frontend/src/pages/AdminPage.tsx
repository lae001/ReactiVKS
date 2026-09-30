import { PagePlaceholder } from './PagePlaceholder'

export function AdminPage() {
  return (
    <PagePlaceholder
      title="Администрирование"
      description="Пользователи, активные встречи, состояние сервисов."
      access="администратор"
    />
  )
}
