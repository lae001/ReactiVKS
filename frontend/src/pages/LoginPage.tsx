import { Link } from 'react-router-dom'
import { PagePlaceholder } from './PagePlaceholder'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'

export function LoginPage() {
  return (
    <PagePlaceholder title="Вход" description="Вход организатора в систему." access="все">
      <form className="flex max-w-sm flex-col gap-4" onSubmit={(e) => e.preventDefault()}>
        <div className="flex flex-col gap-2">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" placeholder="you@example.com" />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="password">Пароль</Label>
          <Input id="password" type="password" autoComplete="current-password" />
        </div>
        <Button type="submit">Войти</Button>
        <p className="text-sm text-muted-foreground">
          Нет аккаунта?{' '}
          <Link className="text-primary underline" to="/register">
            Зарегистрироваться
          </Link>
        </p>
      </form>
    </PagePlaceholder>
  )
}
