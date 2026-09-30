import { useParams } from 'react-router-dom'
import { PagePlaceholder } from './PagePlaceholder'

export function RoomPage() {
  const { meetingId } = useParams()
  return (
    <PagePlaceholder
      title="Комната встречи"
      description={`Видео, панель эмоций, модерация. Встреча: ${meetingId}`}
      access="организатор"
    />
  )
}
