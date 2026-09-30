import { Link } from 'react-router-dom'
import { PagePlaceholder } from './PagePlaceholder'

export function NotFoundPage() {
  return (
    <PagePlaceholder
      title="Страница не найдена"
      description="Проверьте адрес или вернитесь к встречам."
      access="все"
    >
      <Link className="text-primary underline" to="/meetings">
        К списку встреч
      </Link>
    </PagePlaceholder>
  )
}
