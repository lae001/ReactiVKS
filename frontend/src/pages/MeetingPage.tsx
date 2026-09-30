import { Link, useParams } from 'react-router';

import { paths } from '@/shared/config/routes';
import { Button } from '@/shared/ui/button';
import { PageStub } from '@/shared/ui/stub';

export function MeetingPage() {
  const { id = '' } = useParams();
  return (
    <PageStub
      title="Карточка встречи"
      lead={`Встреча ${id}: параметры, ссылка-приглашение, а после завершения – отчет по эмоциям.`}
      planned={[
        'Параметры встречи и ссылка-приглашение',
        'Кнопка «Начать встречу» для организатора',
        'Для завершенной встречи: графики эмоций, отметки моментов, таблица участников',
        'Экспорт отчета в PDF и CSV, удаление данных встречи',
      ]}
      tasks="UC-2, UC-5, UC-6 – спринты 4–6"
    >
      <div>
        <Button asChild>
          <Link to={paths.room(id)}>Открыть комнату</Link>
        </Button>
      </div>
    </PageStub>
  );
}
