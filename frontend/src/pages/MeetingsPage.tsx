import { Plus } from 'lucide-react';
import { Link } from 'react-router';

import { paths } from '@/shared/config/routes';
import { Button } from '@/shared/ui/button';
import { PageStub } from '@/shared/ui/stub';

export function MeetingsPage() {
  return (
    <PageStub
      title="Встречи"
      lead="Здесь будут запланированные и прошедшие встречи. Пока встреч нет — создайте первую."
      planned={[
        'Список запланированных, идущих и завершенных встреч',
        'Поиск по названию и фильтр по дате и статусу',
        'Переход к карточке встречи и отчету',
      ]}
      tasks="UC-2 – спринт 4, история и поиск – спринт 6"
    >
      <div className="flex flex-wrap gap-3">
        <Button asChild>
          <Link to={paths.meetingNew}>
            <Plus aria-hidden />
            Создать встречу
          </Link>
        </Button>
        <Button variant="outline" asChild>
          <Link to={paths.meeting('demo')}>Открыть пример карточки</Link>
        </Button>
      </div>
    </PageStub>
  );
}
