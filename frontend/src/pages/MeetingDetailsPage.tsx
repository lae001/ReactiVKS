import { useParams } from 'react-router-dom'
import { PagePlaceholder } from './PagePlaceholder'

export function MeetingDetailsPage() {
  const { id } = useParams()
  return (
    <PagePlaceholder
      title="Карточка встречи"
      description={`Ссылка, параметры; для завершённой встречи — отчёт. ID: ${id}`}
      access="организатор"
    />
  )
}
