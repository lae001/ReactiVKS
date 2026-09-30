import { Link } from 'react-router-dom'
import { PagePlaceholder } from './PagePlaceholder'
import { Button } from '@/shared/ui/button'

export function MeetingsPage() {
  return (
    <PagePlaceholder
      title="Встречи"
      description="История и запланированные встречи, поиск, фильтры."
      access="организатор"
    >
      <Button asChild>
        <Link to="/meetings/new">Создать встречу</Link>
      </Button>
    </PagePlaceholder>
  )
}
