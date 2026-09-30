import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { routes } from './routes'

function renderAt(path: string) {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />)
}

describe('маршруты (docs/frontend/README.md)', () => {
  it.each([
    ['/login', 'Вход'],
    ['/register', 'Регистрация'],
    ['/meetings', 'Встречи'],
    ['/meetings/new', 'Новая встреча'],
    ['/meetings/42', 'Карточка встречи'],
    ['/room/42', 'Комната встречи'],
    ['/j/abc123', 'Лобби'],
    ['/settings', 'Настройки'],
    ['/admin', 'Администрирование'],
    ['/unknown', 'Страница не найдена'],
  ])('%s открывает страницу «%s»', (path, title) => {
    renderAt(path)
    expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
  })

  it('корень перенаправляет на /meetings', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { name: 'Встречи' })).toBeInTheDocument()
  })

  it('параметры маршрута попадают на страницу', () => {
    renderAt('/j/abc123')
    expect(screen.getByText(/abc123/)).toBeInTheDocument()
  })
})
