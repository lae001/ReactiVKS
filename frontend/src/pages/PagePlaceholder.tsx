import type { ReactNode } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Badge } from '@/shared/ui/badge'

interface Props {
  title: string
  description: string
  /** Кто видит страницу по docs/frontend/README.md */
  access: string
  children?: ReactNode
}

/** Заглушка страницы спринта 1: реальное содержимое появится в следующих спринтах. */
export function PagePlaceholder({ title, description, access, children }: Props) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle>{title}</CardTitle>
          <Badge>{access}</Badge>
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      {children && <CardContent>{children}</CardContent>}
    </Card>
  )
}
