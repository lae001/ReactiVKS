import { screen, within } from '@testing-library/react';

import { organizer } from '@/test/api-mocks';
import { renderApp } from '@/test/render';

describe('карточка встречи', () => {
  it('запланированная: ссылка и кнопка «Начать встречу»', async () => {
    renderApp('/meetings/m-later', { user: organizer });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Интервью: frontend-разработчик' }),
    ).toBeInTheDocument();
    expect(screen.getByText('https://vks.example.ru/j/demolater2')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Начать встречу' })).toHaveAttribute(
      'href',
      '/room/m-later',
    );
  });

  it('завершенная с анализом: отчет с графиками, отметками и таблицей участников', async () => {
    renderApp('/meetings/m-ended', { user: organizer });
    expect(await screen.findByRole('heading', { name: 'Отчет по эмоциям' })).toBeInTheDocument();
    expect(
      screen.getByRole('img', { name: /График вероятностей эмоций за 47:00/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('list', { name: 'Распределение эмоций за встречу' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Вопрос о сроках')).toBeInTheDocument();

    const table = screen.getByRole('table', { name: /Участники встречи/ });
    expect(within(table).getByText('Анна Смирнова')).toBeInTheDocument();
    // отказавшийся от анализа не получает эмоций, только пометку
    expect(within(table).getByText('Отказался')).toBeInTheDocument();
    expect(screen.getByText(/рекомендательный характер/)).toBeInTheDocument();
  });

  it('цвет эмоции не единственный признак: у легенды есть подписи всех семи классов', async () => {
    renderApp('/meetings/m-ended', { user: organizer });
    const legend = await screen.findByRole('list', { name: /Легенда/ });
    expect(within(legend).getAllByRole('listitem')).toHaveLength(7);
    expect(legend).toHaveTextContent('Радость');
    expect(legend).toHaveTextContent('Нейтральное');
  });

  it('завершенная без анализа: объясняет, почему отчета нет', async () => {
    renderApp('/meetings/m-ended-2', { user: organizer });
    expect(
      await screen.findByText(/Анализ эмоций в этой встрече был выключен/),
    ).toBeInTheDocument();
  });

  it('неизвестная встреча: понятное сообщение и возврат к списку', async () => {
    renderApp('/meetings/42', { user: organizer });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Встреча не найдена' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'К встречам' })).toHaveAttribute('href', '/meetings');
  });
});
